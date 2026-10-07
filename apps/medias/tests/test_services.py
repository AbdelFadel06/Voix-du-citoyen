import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.medias import services
from apps.medias.models import Media
from apps.medias.regles import (
    RATTACHEMENT_REALISATION,
    RATTACHEMENT_SIGNALEMENT,
    RATTACHEMENT_SUGGESTION,
)

from . import fichiers

pytestmark = pytest.mark.django_db


@pytest.fixture
def citoyen(creer_utilisateur):
    return creer_utilisateur()


@pytest.fixture
def creer(citoyen):
    def _creer(type_=Media.Type.IMAGE, auteur=None, **kwargs):
        auteur = auteur or citoyen
        if type_ == Media.Type.IMAGE:
            return services.televerser_media(auteur=auteur, type=type_, fichier=fichiers.image("JPEG", "RGB"))
        if type_ == Media.Type.VIDEO:
            return services.televerser_media(
                auteur=auteur, type=type_, fichier=fichiers.video_mp4(),
                miniature=fichiers.image(), duree_secondes=20,
            )
        return services.televerser_media(auteur=auteur, type=type_, fichier=fichiers.audio_m4a(), duree_secondes=30)

    return _creer


def code_erreur(fonction, *args):
    with pytest.raises(ErreurMetier) as exc:
        fonction(*args)
    return exc.value


class TestVerifierMedias:
    def test_signalement_valide(self, citoyen, creer):
        medias = [creer(), creer(), creer(Media.Type.VIDEO)]
        resultat = services.verifier_medias(citoyen, [m.id for m in medias], RATTACHEMENT_SIGNALEMENT)
        assert [m.id for m in resultat] == [m.id for m in medias]

    def test_doublons_ignores(self, citoyen, creer):
        photo = creer()
        assert len(services.verifier_medias(citoyen, [photo.id, str(photo.id)], RATTACHEMENT_SIGNALEMENT)) == 1

    def test_media_d_un_autre_utilisateur(self, citoyen, creer, creer_utilisateur):
        autre = creer(auteur=creer_utilisateur())
        exc = code_erreur(services.verifier_medias, citoyen, [autre.id], RATTACHEMENT_SIGNALEMENT)
        assert exc.code_erreur == CodeErreur.MEDIA_INTROUVABLE

    @pytest.mark.parametrize("identifiant", [uuid.uuid4(), "pas-un-uuid", 42])
    def test_media_inconnu(self, citoyen, identifiant):
        exc = code_erreur(services.verifier_medias, citoyen, [identifiant], RATTACHEMENT_SUGGESTION)
        assert exc.code_erreur == CodeErreur.MEDIA_INTROUVABLE

    def test_media_deja_attache(self, citoyen, creer):
        photo = creer()
        services.attacher([photo])
        exc = code_erreur(services.verifier_medias, citoyen, [photo.id], RATTACHEMENT_SIGNALEMENT)
        assert (exc.code_erreur, exc.status_code) == (CodeErreur.MEDIA_DEJA_UTILISE, 409)

    @pytest.mark.parametrize(
        "contenu, regle, attendu",
        [
            ([], RATTACHEMENT_SIGNALEMENT, "Au moins 1 photo ou vidéo"),
            ([Media.Type.IMAGE] * 5, RATTACHEMENT_SIGNALEMENT, "4 photo(s) au maximum"),
            ([Media.Type.VIDEO] * 2, RATTACHEMENT_SIGNALEMENT, "1 vidéo(s) au maximum"),
            ([Media.Type.IMAGE, Media.Type.AUDIO], RATTACHEMENT_SIGNALEMENT, "enregistrements vocaux"),
            ([Media.Type.IMAGE] * 4, RATTACHEMENT_SUGGESTION, "3 photo(s) au maximum"),
            ([Media.Type.VIDEO], RATTACHEMENT_SUGGESTION, "vidéos ne sont pas acceptées"),
            ([Media.Type.VIDEO] * 3, RATTACHEMENT_REALISATION, "2 vidéo(s) au maximum"),
        ],
    )
    def test_regles_de_nombre_et_de_type(self, citoyen, creer, contenu, regle, attendu):
        ids = [creer(type_).id for type_ in contenu]
        exc = code_erreur(services.verifier_medias, citoyen, ids, regle)
        assert exc.code_erreur == CodeErreur.MEDIAS_NON_CONFORMES
        assert any(attendu in probleme for probleme in exc.details["medias"]), exc.details

    def test_suggestion_sans_media_acceptee(self, citoyen):
        assert services.verifier_medias(citoyen, [], RATTACHEMENT_SUGGESTION) == []

    def test_realisation_dix_photos_et_deux_videos(self, citoyen, creer):
        ids = [creer().id for _ in range(10)] + [creer(Media.Type.VIDEO).id for _ in range(2)]
        assert len(services.verifier_medias(citoyen, ids, RATTACHEMENT_REALISATION)) == 12


class TestAudioEtAttachement:
    def test_verifier_audio(self, citoyen, creer):
        audio = creer(Media.Type.AUDIO)
        assert services.verifier_audio(citoyen, audio.id) == audio

    def test_audio_qui_n_en_est_pas_un(self, citoyen, creer):
        exc = code_erreur(services.verifier_audio, citoyen, creer().id)
        assert exc.code_erreur == CodeErreur.MEDIAS_NON_CONFORMES
        assert "description_audio" in exc.details

    def test_attacher(self, citoyen, creer):
        medias = [creer(), creer()]
        services.attacher(medias)
        assert set(Media.objects.values_list("statut", flat=True)) == {Media.Statut.ATTACHE}
        assert all(m.statut == Media.Statut.ATTACHE for m in medias)


class TestPurge:
    def vieillir(self, media, heures):
        Media.objects.filter(pk=media.pk).update(cree_le=timezone.now() - timedelta(hours=heures))

    def test_supprime_les_temporaires_anciens_et_leurs_fichiers(
        self, creer, django_capture_on_commit_callbacks
    ):
        ancien, recent, attache = creer(), creer(), creer()
        services.attacher([attache])
        for media in (ancien, attache):
            self.vieillir(media, 25)
        chemins = [Path(ancien.fichier.path), Path(ancien.miniature.path)]

        with django_capture_on_commit_callbacks(execute=True):
            nombre = services.purger_medias_temporaires(timezone.now() - timedelta(hours=24))

        assert nombre == 1
        assert set(Media.objects.values_list("pk", flat=True)) == {recent.pk, attache.pk}
        assert not any(chemin.exists() for chemin in chemins)
        assert Path(recent.fichier.path).exists()

    def test_commande_simulation_puis_purge(self, creer, django_capture_on_commit_callbacks):
        self.vieillir(creer(), 30)
        sortie = StringIO()
        call_command("purger_medias", "--simulation", stdout=sortie)
        assert "1 média(s)" in sortie.getvalue() and Media.objects.count() == 1

        with django_capture_on_commit_callbacks(execute=True):
            call_command("purger_medias", stdout=sortie)
        assert Media.objects.count() == 0

    def test_option_heures(self, creer):
        self.vieillir(creer(), 3)
        sortie = StringIO()
        call_command("purger_medias", "--heures", "2", "--simulation", stdout=sortie)
        assert "1 média(s)" in sortie.getvalue()


class TestAdmin:
    def test_suppression_depuis_l_admin_efface_les_fichiers(self, creer, client, creer_utilisateur, django_capture_on_commit_callbacks):
        from django.urls import reverse

        admin = creer_utilisateur(role="ADMIN_MAIRIE", is_staff=True, is_superuser=True)
        client.force_login(admin)
        media = creer()
        chemin = Path(media.fichier.path)
        with django_capture_on_commit_callbacks(execute=True):
            reponse = client.post(reverse("admin:medias_media_delete", args=[media.pk]), {"post": "yes"})
        assert reponse.status_code == 302
        assert not Media.objects.exists() and not chemin.exists()

    def test_liste_avec_apercu(self, creer, client, creer_utilisateur):
        from django.urls import reverse

        client.force_login(creer_utilisateur(role="ADMIN_MAIRIE", is_staff=True, is_superuser=True))
        creer()
        assert "<img" in client.get(reverse("admin:medias_media_changelist")).content.decode()
