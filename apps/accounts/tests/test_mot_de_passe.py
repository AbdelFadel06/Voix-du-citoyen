import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from conftest import MOT_DE_PASSE

pytestmark = pytest.mark.django_db

URL_DEMANDE = reverse("accounts:password-reset")
URL_CONFIRMER = reverse("accounts:password-reset-confirm")
URL_LOGIN = reverse("accounts:login")
URL_REFRESH = reverse("accounts:refresh")
NOUVEAU = "Nouveau!Pass2026"


@pytest.fixture(autouse=True)
def vider_cache():
    cache.clear()  # limitation de débit des demandes de code


@pytest.fixture
def citoyen(creer_utilisateur):
    return creer_utilisateur(telephone="+2290197123456", nom="Hounkpatin", prenoms="Afiavi")


@pytest.fixture
def agent(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.AGENT, email="r.ahouansou@mairie-parakou.bj")


def demander(client, **identifiant):
    reponse = client.post(URL_DEMANDE, identifiant, format="json")
    assert reponse.status_code == 200, reponse.json()
    return reponse


def confirmer(client, code, password=NOUVEAU, **identifiant):
    return client.post(URL_CONFIRMER, {**identifiant, "code": code, "password": password}, format="json")


class TestCitoyen:
    def test_parcours_complet(self, api_client, sms, citoyen):
        ancienne_session = api_client.post(URL_LOGIN, {"telephone": "0197123456", "password": MOT_DE_PASSE}, format="json")
        refresh = ancienne_session.json()["donnees"]["refresh"]

        demander(api_client, telephone="0197123456")
        assert len(sms) == 1 and sms[0].telephone == citoyen.telephone
        reponse = confirmer(api_client, sms.dernier_code(), telephone="0197123456")
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["message"].startswith("Votre mot de passe a été modifié")

        citoyen.refresh_from_db()
        assert citoyen.check_password(NOUVEAU)
        # Les anciennes sessions sont fermées.
        assert api_client.post(URL_REFRESH, {"refresh": refresh}, format="json").json()["erreur"]["code"] == CodeErreur.JETON_INVALIDE
        assert api_client.post(URL_LOGIN, {"telephone": "0197123456", "password": NOUVEAU}, format="json").status_code == 200

    def test_code_a_usage_unique(self, api_client, sms, citoyen):
        demander(api_client, telephone="0197123456")
        code = sms.dernier_code()
        assert confirmer(api_client, code, telephone="0197123456").status_code == 200
        reponse = confirmer(api_client, code, password="Autre!Pass2026", telephone="0197123456")
        assert reponse.json()["erreur"]["code"] == CodeErreur.OTP_EXPIRE

    def test_mauvais_code(self, api_client, sms, citoyen):
        demander(api_client, telephone="0197123456")
        faux = "000000" if sms.dernier_code() != "000000" else "111111"
        erreur = confirmer(api_client, faux, telephone="0197123456").json()["erreur"]
        assert (erreur["code"], erreur["details"]) == (CodeErreur.OTP_INVALIDE, {"tentatives_restantes": 4})
        citoyen.refresh_from_db()
        assert citoyen.check_password(MOT_DE_PASSE)

    def test_mot_de_passe_faible_ne_consomme_pas_le_code(self, api_client, sms, citoyen):
        demander(api_client, telephone="0197123456")
        code = sms.dernier_code()
        erreur = confirmer(api_client, code, password="12345678", telephone="0197123456").json()["erreur"]
        assert erreur["code"] == CodeErreur.VALIDATION_ERREUR and "password" in erreur["details"]
        assert confirmer(api_client, code, telephone="0197123456").status_code == 200

    def test_le_code_d_inscription_ne_sert_pas(self, api_client, sms, citoyen):
        from apps.accounts.models import CodeOTP
        from apps.accounts.services import generer_code_otp

        generer_code_otp(citoyen, CodeOTP.Motif.INSCRIPTION)
        reponse = confirmer(api_client, sms.dernier_code(), telephone="0197123456")
        assert reponse.json()["erreur"]["code"] == CodeErreur.OTP_EXPIRE


class TestSansRevelerLesComptes:
    @pytest.mark.parametrize(
        "identifiant",
        [
            {"telephone": "0197999999"},  # inconnu
            {"email": "personne@mairie.test"},  # inconnu
            {"telephone": "0196000007"},  # agent : se connecte par e-mail
        ],
    )
    def test_meme_reponse_et_aucun_sms(self, api_client, sms, creer_utilisateur, identifiant):
        creer_utilisateur(role=Utilisateur.Role.AGENT, telephone="+2290196000007")
        reponse = demander(api_client, **identifiant)
        assert reponse.json()["message"].startswith("Si un compte correspond")
        assert len(sms) == 0

    @pytest.mark.parametrize("etat", [{"telephone_verifie": False}, {"is_active": False}])
    def test_citoyen_non_verifie_ou_desactive(self, api_client, sms, creer_utilisateur, etat):
        creer_utilisateur(telephone="+2290197123456", **etat)
        demander(api_client, telephone="0197123456")
        assert len(sms) == 0
        assert confirmer(api_client, "123456", telephone="0197123456").json()["erreur"]["code"] == CodeErreur.OTP_EXPIRE

    def test_identifiant_obligatoire_et_unique(self, api_client):
        reponse = api_client.post(URL_DEMANDE, {"telephone": "0197123456", "email": "a@b.bj"}, format="json")
        assert "identifiant" in reponse.json()["erreur"]["details"]


class TestMairie:
    def test_par_email(self, api_client, sms, agent):
        demander(api_client, email="R.Ahouansou@mairie-parakou.bj")
        assert sms[0].telephone == agent.telephone
        assert confirmer(api_client, sms.dernier_code(), email="r.ahouansou@mairie-parakou.bj").status_code == 200
        assert api_client.post(URL_LOGIN, {"email": agent.email, "password": NOUVEAU}, format="json").status_code == 200


class TestLimitation:
    def test_cinq_demandes_par_heure(self, api_client, sms, citoyen):
        for _ in range(5):
            demander(api_client, telephone="0197123456")
        reponse = api_client.post(URL_DEMANDE, {"telephone": "0197123456"}, format="json")
        assert reponse.json()["erreur"]["code"] == CodeErreur.TROP_DE_REQUETES

    def test_par_email(self, api_client, sms, agent):
        for _ in range(5):
            demander(api_client, email=agent.email)
        reponse = api_client.post(URL_DEMANDE, {"email": agent.email}, format="json")
        assert reponse.status_code == 429
