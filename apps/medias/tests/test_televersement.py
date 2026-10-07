from pathlib import Path

import pytest
from django.urls import reverse
from PIL import Image
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.medias.models import Media

from . import fichiers
from .fichiers import TAG_GPS, TAG_MODELE

pytestmark = pytest.mark.django_db

URL = reverse("medias:televersement")


@pytest.fixture
def citoyen(creer_utilisateur):
    return creer_utilisateur()


@pytest.fixture
def client(citoyen, client_connecte):
    return client_connecte(citoyen)


def envoyer(client, type_, fichier, **champs):
    return client.post(URL, {"type": type_, "fichier": fichier, **champs}, format="multipart")


def donnees(reponse):
    assert reponse.status_code == 201, reponse.json()
    return reponse.json()["donnees"]


def erreur(reponse, code, statut=400):
    assert reponse.status_code == statut, reponse.json()
    corps = reponse.json()["erreur"]
    assert corps["code"] == code
    return corps


def chemin_disque(media, champ="fichier"):
    return Path(getattr(media, champ).path)


class TestPhotos:
    def test_photo_enregistree_en_temporaire(self, client, citoyen):
        corps = donnees(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif()))
        media = Media.objects.get(pk=corps["id"])

        assert media.auteur == citoyen
        assert (media.type, media.statut, media.mime_type) == ("IMAGE", "TEMPORAIRE", "image/jpeg")
        assert (media.largeur, media.hauteur) == (40, 20)
        assert media.duree_secondes is None
        assert media.taille_octets == chemin_disque(media).stat().st_size
        assert corps["fichier"].startswith("http://testserver/media/medias/image/")
        assert corps["miniature"].startswith("http://testserver/media/medias/miniatures/")

    def test_metadonnees_exif_et_gps_supprimees(self, client):
        source = fichiers.jpeg_avec_exif()
        source.seek(0)
        assert Image.open(source).getexif().get(TAG_MODELE) == "Tecno Spark 10"
        source.seek(0)

        media = Media.objects.get(pk=donnees(envoyer(client, "IMAGE", source))["id"])
        for champ in ("fichier", "miniature"):
            exif = Image.open(chemin_disque(media, champ)).getexif()
            assert TAG_MODELE not in exif
            assert not exif.get_ifd(TAG_GPS)
            assert len(exif) == 0

    def test_orientation_appliquee_avant_suppression(self, client):
        # Orientation 6 = rotation de 90° : la photo 40×20 doit être enregistrée en 20×40.
        corps = donnees(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif(orientation=6)))
        assert (corps["largeur"], corps["hauteur"]) == (20, 40)
        assert Image.open(chemin_disque(Media.objects.get(pk=corps["id"]))).size == (20, 40)

    def test_miniature_reduite_en_jpeg(self, client):
        corps = donnees(envoyer(client, "IMAGE", fichiers.image("JPEG", "RGB", taille=(1200, 600))))
        miniature = Image.open(chemin_disque(Media.objects.get(pk=corps["id"]), "miniature"))
        assert miniature.format == "JPEG"
        assert miniature.size == (480, 240)

    def test_png_transparent(self, client):
        corps = donnees(envoyer(client, "IMAGE", fichiers.image("PNG", "RGBA")))
        media = Media.objects.get(pk=corps["id"])
        assert media.fichier.name.endswith(".png")
        assert Image.open(chemin_disque(media)).mode == "RGBA"
        assert Image.open(chemin_disque(media, "miniature")).mode == "RGB"

    def test_webp(self, client):
        corps = donnees(envoyer(client, "IMAGE", fichiers.image("WEBP", "RGB")))
        assert corps["mime_type"] == "image/webp"

    def test_nom_du_fichier_non_repris_du_client(self, client):
        corps = donnees(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif(nom="../../etc/passwd.jpg")))
        media = Media.objects.get(pk=corps["id"])
        assert Path(media.fichier.name).name == f"{media.id}.jpg"

    def test_miniature_refusee_pour_une_photo(self, client):
        reponse = envoyer(client, "IMAGE", fichiers.jpeg_avec_exif(), miniature=fichiers.image())
        assert "miniature" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]


class TestControlesDuFichier:
    def test_type_reel_et_non_extension(self, client):
        corps = erreur(envoyer(client, "IMAGE", fichiers.pdf(nom="photo.jpg")), CodeErreur.MEDIA_FORMAT_NON_AUTORISE)
        assert corps["details"]["type_detecte"] == "application/pdf"
        assert "JPEG, PNG ou WebP" in corps["message"]
        assert not Media.objects.exists()

    def test_gif_refuse(self, client):
        erreur(envoyer(client, "IMAGE", fichiers.image("GIF", "P")), CodeErreur.MEDIA_FORMAT_NON_AUTORISE)

    def test_photo_declaree_comme_audio(self, client):
        erreur(
            envoyer(client, "AUDIO", fichiers.jpeg_avec_exif(), duree_secondes=10),
            CodeErreur.MEDIA_FORMAT_NON_AUTORISE,
        )

    def test_photo_trop_volumineuse(self, client):
        corps = erreur(
            envoyer(client, "IMAGE", fichiers.trop_gros(5 * 1024 * 1024 + 1)), CodeErreur.MEDIA_TROP_VOLUMINEUX
        )
        assert corps["details"]["taille_max_octets"] == 5 * 1024 * 1024
        assert "5 Mo" in corps["message"]

    def test_image_corrompue(self, client):
        erreur(envoyer(client, "IMAGE", fichiers.jpeg_corrompu()), CodeErreur.MEDIA_ILLISIBLE)
        assert not Media.objects.exists()

    def test_type_obligatoire(self, client):
        reponse = client.post(URL, {"fichier": fichiers.jpeg_avec_exif()}, format="multipart")
        assert "type" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_fichier_obligatoire(self, client):
        reponse = client.post(URL, {"type": "IMAGE"}, format="multipart")
        assert "fichier" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]


class TestVideos:
    def test_video_avec_miniature_et_duree(self, client):
        corps = donnees(
            envoyer(
                client, "VIDEO", fichiers.video_mp4(),
                miniature=fichiers.jpeg_avec_exif(), duree_secondes=37.2, largeur=1280, hauteur=720,
            )
        )
        media = Media.objects.get(pk=corps["id"])
        assert (media.mime_type, media.duree_secondes) == ("video/mp4", 38)
        assert (media.largeur, media.hauteur) == (1280, 720)
        assert media.fichier.name.endswith(".mp4")
        assert len(Image.open(chemin_disque(media, "miniature")).getexif()) == 0

    def test_duree_et_miniature_obligatoires(self, client):
        details = erreur(envoyer(client, "VIDEO", fichiers.video_mp4()), CodeErreur.VALIDATION_ERREUR)["details"]
        assert {"duree_secondes", "miniature"} <= details.keys()

    def test_video_trop_longue(self, client):
        corps = erreur(
            envoyer(client, "VIDEO", fichiers.video_mp4(), miniature=fichiers.image(), duree_secondes=61),
            CodeErreur.MEDIA_TROP_LONG,
        )
        assert corps["details"]["duree_max_secondes"] == 60

    def test_miniature_dans_un_mauvais_format(self, client):
        corps = erreur(
            envoyer(client, "VIDEO", fichiers.video_mp4(), miniature=fichiers.pdf(), duree_secondes=10),
            CodeErreur.MEDIA_FORMAT_NON_AUTORISE,
        )
        assert "miniature" in corps["details"]


class TestAudios:
    @pytest.mark.parametrize(
        "fabrique, mime, extension",
        [
            (fichiers.audio_m4a, "audio/x-m4a", ".m4a"),
            (fichiers.audio_android, "video/mp4", ".m4a"),
            (fichiers.audio_mp3, "audio/mpeg", ".mp3"),
        ],
    )
    def test_formats_acceptes(self, client, fabrique, mime, extension):
        corps = donnees(envoyer(client, "AUDIO", fabrique(), duree_secondes=45))
        media = Media.objects.get(pk=corps["id"])
        assert (media.mime_type, media.duree_secondes) == (mime, 45)
        assert not media.miniature
        assert media.fichier.name.endswith(extension)
        assert corps["miniature"] is None

    def test_deux_minutes_acceptees(self, client):
        donnees(envoyer(client, "AUDIO", fichiers.audio_m4a(), duree_secondes=120))

    def test_audio_trop_long(self, client):
        corps = erreur(envoyer(client, "AUDIO", fichiers.audio_m4a(), duree_secondes=120.5), CodeErreur.MEDIA_TROP_LONG)
        assert "2 minutes" in corps["message"]

    def test_audio_trop_volumineux(self, client):
        gros = fichiers.trop_gros(3 * 1024 * 1024 + 1, nom="vocal.m4a")
        erreur(envoyer(client, "AUDIO", gros, duree_secondes=30), CodeErreur.MEDIA_TROP_VOLUMINEUX)

    def test_duree_obligatoire(self, client):
        reponse = envoyer(client, "AUDIO", fichiers.audio_m4a())
        assert "duree_secondes" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]


class TestAcces:
    def test_non_authentifie(self, api_client):
        erreur(envoyer(api_client, "IMAGE", fichiers.jpeg_avec_exif()), CodeErreur.NON_AUTHENTIFIE, 401)

    def test_organisation_en_lecture_seule(self, creer_utilisateur, client_connecte):
        client = client_connecte(creer_utilisateur(role=Utilisateur.Role.ORGANISATION))
        erreur(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif()), CodeErreur.PERMISSION_REFUSEE, 403)

    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE])
    def test_agents_et_admins_peuvent_envoyer(self, creer_utilisateur, client_connecte, role):
        donnees(envoyer(client_connecte(creer_utilisateur(role=role)), "IMAGE", fichiers.jpeg_avec_exif()))

    def test_json_refuse(self, client):
        reponse = client.post(URL, {"type": "IMAGE"}, format="json")
        assert reponse.status_code == 415
        assert reponse.json()["succes"] is False

    def test_limitation_par_utilisateur(self, client, creer_utilisateur, client_connecte, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "televersement", "2/hour")
        for _ in range(2):
            donnees(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif()))
        corps = erreur(envoyer(client, "IMAGE", fichiers.jpeg_avec_exif()), CodeErreur.TROP_DE_REQUETES, 429)
        assert corps["details"]["attente_secondes"] > 0
        # Un autre utilisateur n'est pas concerné.
        donnees(envoyer(client_connecte(creer_utilisateur()), "IMAGE", fichiers.jpeg_avec_exif()))
