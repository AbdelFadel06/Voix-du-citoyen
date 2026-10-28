"""Institutions IBDC : clé d'API, compte technique et cloisonnement par commune."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.interop import services
from apps.interop.models import Institution
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL_SIGNALEMENTS = reverse("signalements:signalement-list")


def creer_commune(nom, code):
    commune = Commune.objects.create(
        nom=nom, code=code, departement="Test",
        lat_min=Decimal("6"), lat_max=Decimal("10"), lng_min=Decimal("1"), lng_max=Decimal("4"),
    )
    arrondissement = Arrondissement.objects.create(commune=commune, nom=f"Centre {nom}")
    Quartier.objects.create(arrondissement=arrondissement, nom=f"Quartier {nom}")
    return commune


@pytest.fixture
def parakou():
    return creer_commune("Parakou", "PKO")


@pytest.fixture
def cotonou():
    return creer_commune("Cotonou", "COT")


@pytest.fixture
def institution(parakou):
    institution, cle = services.creer_institution(
        id_externe="IBDC-12", nom="Mairie de Parakou", commune=parakou,
        email="ibdc-parakou@mairie.bj", telephone="+2290196000101",
    )
    institution.cle = cle
    return institution


def client_cle(cle):
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=cle)
    return client


@pytest.fixture
def signaler(creer_utilisateur, televerser):
    secteur = Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_signalement=True)

    def _signaler(commune):
        auteur = creer_utilisateur(commune=commune)
        dossier, _ = signalements.creer_signalement(
            auteur=auteur, secteur=secteur, quartier=Quartier.objects.get(arrondissement__commune=commune),
            mode_localisation="MANUEL", medias_ids=[televerser(auteur).id], titre="Trou",
            description_texte="Gros trou", repere="Marché",
        )
        return dossier

    return _signaler


class TestCreation:
    def test_institution_et_compte_technique(self, institution, parakou):
        assert institution.cle.startswith(f"vdc_{institution.cle_prefixe}_")
        compte = institution.compte
        assert (compte.role, compte.commune, compte.email) == (Utilisateur.Role.ADMIN_MAIRIE, parakou, "ibdc-parakou@mairie.bj")
        # La clé n'est pas stockée en clair.
        assert institution.cle not in (institution.cle_empreinte, institution.cle_prefixe)
        # Le compte technique ne peut pas se connecter avec un mot de passe.
        assert not compte.has_usable_password()

    def test_commande(self, parakou):
        sortie = StringIO()
        call_command(
            "creer_institution", id_externe="IBDC-12", nom="Mairie de Parakou", commune="PKO",
            email="ibdc@mairie.bj", telephone="+2290196000101", stdout=sortie,
        )
        cle = sortie.getvalue().strip().splitlines()[-1]
        assert services.institution_pour_cle(cle).id_externe == "IBDC-12"
        with pytest.raises(CommandError, match="déjà connectée"):
            call_command(
                "creer_institution", id_externe="IBDC-12", nom="Autre", commune="PKO",
                email="autre@mairie.bj", telephone="+2290196000102", stdout=StringIO(),
            )
        with pytest.raises(CommandError, match="introuvable"):
            call_command(
                "creer_institution", id_externe="IBDC-99", nom="X", commune="XXX",
                email="x@mairie.bj", telephone="+2290196000103", stdout=StringIO(),
            )


class TestAuthentification:
    def test_agit_comme_la_mairie_de_sa_commune(self, institution, signaler, parakou, cotonou):
        a_parakou = signaler(parakou)
        signaler(cotonou)
        client = client_cle(institution.cle)
        reponse = client.get(URL_SIGNALEMENTS)
        assert reponse.status_code == 200, reponse.json()
        assert [d["id"] for d in reponse.json()["donnees"]] == [a_parakou.pk]
        # Peut traiter les dossiers de sa commune.
        url = reverse("signalements:signalement-changer-statut", args=[a_parakou.pk])
        assert client.post(url, {"statut": "RECU"}, format="json").status_code == 200

    @pytest.mark.parametrize("cle", ["n-importe-quoi", "vdc_000000000000_faux", ""])
    def test_cle_invalide(self, institution, cle):
        reponse = client_cle(cle or "vdc_" + institution.cle_prefixe + "_mauvais").get(URL_SIGNALEMENTS)
        assert reponse.status_code == 401
        assert reponse.json()["erreur"]["code"] == CodeErreur.CLE_API_INVALIDE

    def test_institution_desactivee(self, institution):
        Institution.objects.filter(pk=institution.pk).update(actif=False)
        reponse = client_cle(institution.cle).get(URL_SIGNALEMENTS)
        assert reponse.json()["erreur"]["code"] == CodeErreur.CLE_API_INVALIDE

    def test_nouvelle_cle_remplace_l_ancienne(self, institution):
        ancienne = institution.cle
        sortie = StringIO()
        call_command("nouvelle_cle_institution", id_externe="IBDC-12", stdout=sortie)
        nouvelle = sortie.getvalue().strip().splitlines()[-1]
        assert client_cle(ancienne).get(URL_SIGNALEMENTS).status_code == 401
        assert client_cle(nouvelle).get(URL_SIGNALEMENTS).status_code == 200

    def test_sans_cle_ni_jeton(self, api_client):
        assert api_client.get(URL_SIGNALEMENTS).json()["erreur"]["code"] == CodeErreur.NON_AUTHENTIFIE

    def test_connexion_par_mot_de_passe_impossible(self, api_client, institution):
        reponse = api_client.post(
            reverse("accounts:login"), {"email": "ibdc-parakou@mairie.bj", "password": "nimportequoi"}, format="json"
        )
        assert reponse.json()["erreur"]["code"] == CodeErreur.IDENTIFIANTS_INVALIDES


class TestAgentExterne:
    def changer_statut(self, client, dossier, **entetes):
        url = reverse("signalements:signalement-changer-statut", args=[dossier.pk])
        return client.post(url, {"statut": "RECU", "commentaire": "Pris en compte."}, format="json", **entetes)

    @pytest.mark.parametrize(
        "entete",
        [
            "Rodrigue%20Ahouansou%20-%20B%C3%A9atrice",  # encodé en URL
            "Rodrigue Ahouansou - Béatrice".encode("utf-8").decode("latin-1"),  # UTF-8 brut
        ],
    )
    def test_nom_de_l_agent_dans_l_historique(self, institution, signaler, parakou, entete):
        dossier = signaler(parakou)
        reponse = self.changer_statut(client_cle(institution.cle), dossier, HTTP_X_AGENT=entete)
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["donnees"]["historique"][-1]["auteur_nom"] == "Rodrigue Ahouansou - Béatrice (IBDC)"
        assert dossier.suivis.last().agent_externe == "Rodrigue Ahouansou - Béatrice"

    def test_sans_en_tete(self, institution, signaler, parakou):
        reponse = self.changer_statut(client_cle(institution.cle), signaler(parakou))
        assert reponse.json()["donnees"]["historique"][-1]["auteur_nom"] == "Compte technique IBDC Mairie de Parakou"

    def test_ignore_hors_cle_d_api(self, creer_utilisateur, client_connecte, signaler, parakou):
        agent = creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=parakou, nom="Kora", prenoms="Aminatou")
        dossier = signaler(parakou)
        self.changer_statut(client_connecte(agent), dossier, HTTP_X_AGENT="Usurpateur")
        assert dossier.suivis.last().agent_externe == ""


class TestModifieDepuis:
    def test_ne_renvoie_que_les_changements(self, institution, signaler, parakou):
        from datetime import timedelta

        from django.utils import timezone

        from apps.signalements.models import Signalement

        ancien, recent = signaler(parakou), signaler(parakou)
        Signalement.objects.filter(pk=ancien.pk).update(maj_le=timezone.now() - timedelta(hours=2))
        depuis = (timezone.now() - timedelta(hours=1)).isoformat()
        client = client_cle(institution.cle)
        assert [d["id"] for d in client.get(URL_SIGNALEMENTS, {"modifie_depuis": depuis}).json()["donnees"]] == [recent.pk]
        # Un changement de statut fait revenir le dossier.
        client.post(reverse("signalements:signalement-changer-statut", args=[ancien.pk]), {"statut": "RECU"}, format="json")
        ids = {d["id"] for d in client.get(URL_SIGNALEMENTS, {"modifie_depuis": depuis}).json()["donnees"]}
        assert ids == {ancien.pk, recent.pk}

    def test_date_invalide(self, institution):
        reponse = client_cle(institution.cle).get(URL_SIGNALEMENTS, {"modifie_depuis": "hier"})
        assert reponse.json()["erreur"]["code"] == CodeErreur.VALIDATION_ERREUR


class TestLimiteDeDebit:
    def test_par_cle(self, institution, settings, creer_utilisateur, client_connecte):
        from django.core.cache import cache
        from rest_framework.settings import api_settings

        cache.clear()
        taux = {**api_settings.DEFAULT_THROTTLE_RATES, "cle_api": "3/minute"}
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": taux}
        from apps.interop.throttling import ThrottleCleApi

        ThrottleCleApi.THROTTLE_RATES = taux
        try:
            client = client_cle(institution.cle)
            codes = [client.get(URL_SIGNALEMENTS).status_code for _ in range(4)]
            assert codes == [200, 200, 200, 429]
            # Les comptes connectés par jeton ne sont pas concernés.
            agent = client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT))
            assert all(agent.get(URL_SIGNALEMENTS).status_code == 200 for _ in range(4))
        finally:
            ThrottleCleApi.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
            cache.clear()
