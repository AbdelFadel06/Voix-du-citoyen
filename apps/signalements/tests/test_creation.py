from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.core.references import prochaine_reference
from apps.medias.models import Media
from apps.medias.services import attacher
from apps.signalements.models import Signalement, SuiviSignalement

pytestmark = pytest.mark.django_db

URL = reverse("signalements:signalement-list")
ANNEE = timezone.localdate().year


@pytest.fixture
def client(citoyen, client_connecte):
    return client_connecte(citoyen)


def envoyer(client, corps):
    return client.post(URL, corps, format="json")


def cree(reponse):
    assert reponse.status_code == 201, reponse.json()
    return reponse.json()["donnees"]


def erreur(reponse, code, statut=400):
    assert reponse.status_code == statut, reponse.json()
    assert reponse.json()["erreur"]["code"] == code, reponse.json()
    return reponse.json()["erreur"]


class TestCreationGPS:
    def test_cree_un_signalement_soumis(self, client, donnees_gps, citoyen, voirie):
        corps = donnees_gps()
        reponse = envoyer(client, corps)
        donnees = cree(reponse)

        assert reponse.json()["message"] == f"Signalement envoyé. Votre référence : SIG-{ANNEE}-00001."
        signalement = Signalement.objects.get()
        assert signalement.reference == f"SIG-{ANNEE}-00001" == donnees["reference"]
        assert signalement.statut == Signalement.Statut.SOUMIS
        assert signalement.auteur == citoyen
        assert signalement.service_assigne == voirie
        assert (signalement.latitude, signalement.longitude) == (Decimal("6.401235"), Decimal("2.341235"))
        assert not signalement.titre_genere
        assert donnees["avertissements"] == []
        assert donnees["est_auteur"] is True

    def test_les_medias_sont_attaches(self, client, donnees_gps):
        corps = donnees_gps()
        cree(envoyer(client, corps))
        media = Media.objects.get(pk=corps["medias"][0])
        assert media.statut == Media.Statut.ATTACHE
        assert list(Signalement.objects.get().medias.all()) == [media]

    def test_historique_initial(self, client, donnees_gps, citoyen):
        donnees = cree(envoyer(client, donnees_gps()))
        suivi = SuiviSignalement.objects.get()
        assert (suivi.type_evenement, suivi.nouveau_statut, suivi.auteur) == ("CHANGEMENT_STATUT", "SOUMIS", citoyen)
        assert [e["nouveau_statut"] for e in donnees["historique"]] == ["SOUMIS"]

    def test_references_successives(self, client, donnees_gps):
        refs = [cree(envoyer(client, donnees_gps()))["reference"] for _ in range(3)]
        assert refs == [f"SIG-{ANNEE}-0000{i}" for i in (1, 2, 3)]

    def test_avertissement_gps_imprecis(self, client, donnees_gps):
        donnees = cree(envoyer(client, donnees_gps(precision_gps=150)))
        assert [a["code"] for a in donnees["avertissements"]] == ["GPS_IMPRECIS"]
        assert "± 150 m" in donnees["avertissements"][0]["message"]

    def test_precision_de_100_m_sans_avertissement(self, client, donnees_gps):
        assert cree(envoyer(client, donnees_gps(precision_gps=100)))["avertissements"] == []

    def test_position_hors_commune_et_medias_non_consommes(self, client, donnees_gps):
        corps = donnees_gps(latitude=6.36, longitude=2.42)  # Cotonou
        erreur(envoyer(client, corps), CodeErreur.COORDONNEES_HORS_COMMUNE)
        assert not Signalement.objects.exists()
        assert Media.objects.get(pk=corps["medias"][0]).statut == Media.Statut.TEMPORAIRE

    @pytest.mark.parametrize("champ", ["latitude", "longitude", "precision_gps"])
    def test_coordonnees_obligatoires(self, client, donnees_gps, champ):
        corps = donnees_gps()
        del corps[champ]
        assert champ in erreur(envoyer(client, corps), CodeErreur.VALIDATION_ERREUR)["details"]


class TestCreationManuelle:
    def test_repere_obligatoire(self, client, donnees_gps):
        corps = donnees_gps(mode_localisation="MANUEL")
        assert "repere" in erreur(envoyer(client, corps), CodeErreur.VALIDATION_ERREUR)["details"]

    def test_coordonnees_ignorees(self, client, donnees_gps):
        cree(envoyer(client, donnees_gps(mode_localisation="MANUEL", repere="Derrière le marché")))
        signalement = Signalement.objects.get()
        assert (signalement.latitude, signalement.longitude, signalement.precision_gps) == (None, None, None)
        assert signalement.repere == "Derrière le marché"

    def test_quartier_toujours_obligatoire(self, client, donnees_gps):
        corps = donnees_gps(mode_localisation="MANUEL", repere="Marché")
        del corps["quartier"]
        assert "quartier" in erreur(envoyer(client, corps), CodeErreur.VALIDATION_ERREUR)["details"]


class TestDescriptionEtTitre:
    def test_description_obligatoire(self, client, donnees_gps):
        corps = donnees_gps(description_texte="  ")
        assert "description_texte" in erreur(envoyer(client, corps), CodeErreur.VALIDATION_ERREUR)["details"]

    def test_titre_obligatoire_sans_audio(self, client, donnees_gps):
        corps = donnees_gps(titre="")
        assert "titre" in erreur(envoyer(client, corps), CodeErreur.VALIDATION_ERREUR)["details"]

    def test_audio_seul_genere_le_titre(self, client, donnees_gps, citoyen, televerser):
        audio = televerser(citoyen, Media.Type.AUDIO)
        donnees = cree(envoyer(client, donnees_gps(titre="", description_texte="", description_audio=str(audio.id))))
        assert donnees["titre"] == "Voirie – Togoudo"
        assert donnees["titre_genere"] is True
        assert donnees["description_audio"]["id"] == str(audio.id)
        audio.refresh_from_db()
        assert audio.statut == Media.Statut.ATTACHE

    def test_texte_et_audio_ensemble(self, client, donnees_gps, citoyen, televerser):
        audio = televerser(citoyen, Media.Type.AUDIO)
        donnees = cree(envoyer(client, donnees_gps(description_audio=str(audio.id))))
        assert donnees["titre"] == "Nid-de-poule devant l'école" and donnees["a_description_audio"] is True

    def test_une_photo_ne_peut_pas_servir_de_description_audio(self, client, donnees_gps, citoyen, televerser):
        corps = donnees_gps(description_audio=str(televerser(citoyen).id))
        assert "description_audio" in erreur(envoyer(client, corps), CodeErreur.MEDIAS_NON_CONFORMES)["details"]


class TestMediasJoints:
    def test_au_moins_un_media(self, client, donnees_gps):
        erreur(envoyer(client, donnees_gps(medias=[])), CodeErreur.MEDIAS_NON_CONFORMES)

    def test_media_d_un_autre_citoyen(self, client, donnees_gps, creer_utilisateur, televerser):
        autre = televerser(creer_utilisateur())
        erreur(envoyer(client, donnees_gps(medias=[str(autre.id)])), CodeErreur.MEDIA_INTROUVABLE)

    def test_media_deja_utilise(self, client, donnees_gps, citoyen, televerser):
        photo = televerser(citoyen)
        attacher([photo])
        erreur(envoyer(client, donnees_gps(medias=[str(photo.id)])), CodeErreur.MEDIA_DEJA_UTILISE, 409)

    def test_audio_dans_les_medias(self, client, donnees_gps, citoyen, televerser):
        corps = donnees_gps()
        corps["medias"].append(str(televerser(citoyen, Media.Type.AUDIO).id))
        erreur(envoyer(client, corps), CodeErreur.MEDIAS_NON_CONFORMES)

    def test_identifiant_mal_forme(self, client, donnees_gps):
        assert "medias" in erreur(envoyer(client, donnees_gps(medias=["abc"])), CodeErreur.VALIDATION_ERREUR)["details"]


class TestReferentiels:
    def test_secteur_non_propose_pour_signalement(self, client, donnees_gps, secteur):
        secteur.pour_signalement = False
        secteur.save()
        assert "secteur" in erreur(envoyer(client, donnees_gps()), CodeErreur.VALIDATION_ERREUR)["details"]

    def test_quartier_inactif(self, client, donnees_gps, quartier):
        quartier.actif = False
        quartier.save()
        assert "quartier" in erreur(envoyer(client, donnees_gps()), CodeErreur.VALIDATION_ERREUR)["details"]


class TestAcces:
    def test_non_authentifie(self, api_client, donnees_gps):
        erreur(envoyer(api_client, donnees_gps()), CodeErreur.NON_AUTHENTIFIE, 401)

    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE, Utilisateur.Role.ORGANISATION])
    def test_reserve_aux_citoyens(self, creer_utilisateur, client_connecte, donnees_gps, role):
        client = client_connecte(creer_utilisateur(role=role))
        erreur(envoyer(client, donnees_gps()), CodeErreur.PERMISSION_REFUSEE, 403)

    def test_limitation_par_citoyen(self, client, donnees_gps, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "creation_signalement", "2/day")
        for _ in range(2):
            cree(envoyer(client, donnees_gps()))
        erreur(envoyer(client, donnees_gps()), CodeErreur.TROP_DE_REQUETES, 429)


class TestContraintesEnBase:
    def test_description_obligatoire(self, citoyen, secteur, quartier):
        with pytest.raises(IntegrityError), transaction.atomic():
            Signalement.objects.create(
                reference="SIG-X-1", secteur=secteur, auteur=citoyen, quartier=quartier, mode_localisation="MANUEL"
            )

    def test_gps_complet(self, citoyen, secteur, quartier):
        with pytest.raises(IntegrityError), transaction.atomic():
            Signalement.objects.create(
                reference="SIG-X-2", secteur=secteur, auteur=citoyen, quartier=quartier,
                mode_localisation="GPS", description_texte="x", latitude=Decimal("6.4"),
            )

    def test_note_interne_jamais_visible(self, creer_signalement, citoyen, agent):
        signalement = creer_signalement(citoyen)
        with pytest.raises(IntegrityError), transaction.atomic():
            SuiviSignalement.objects.create(
                signalement=signalement, type_evenement="NOTE_INTERNE", visible_citoyen=True, auteur=agent
            )


@pytest.mark.django_db(transaction=True)
def test_reference_hors_transaction_refusee():
    with pytest.raises(RuntimeError):
        prochaine_reference(Signalement, "SIG")


def test_reference_apres_99999(creer_signalement, citoyen):
    signalement = creer_signalement(citoyen)
    Signalement.objects.filter(pk=signalement.pk).update(reference=f"SIG-{ANNEE}-99999")
    with transaction.atomic():
        assert prochaine_reference(Signalement, "SIG") == f"SIG-{ANNEE}-100000"
