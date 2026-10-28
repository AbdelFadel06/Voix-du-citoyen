"""Changement de mot de passe par la personne connectée, et mots de passe provisoires."""

import pytest
from django.core.checks import run_checks
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Organisation, Utilisateur
from apps.core.codes_erreur import CodeErreur
from conftest import MOT_DE_PASSE, commune_de_test

pytestmark = pytest.mark.django_db

URL = reverse("accounts:password-change")
NOUVEAU = "Nouveau!Pass2026"


def changer(client, ancien=MOT_DE_PASSE, nouveau=NOUVEAU):
    return client.post(URL, {"ancien_mot_de_passe": ancien, "nouveau_mot_de_passe": nouveau}, format="json")


class TestChangement:
    def test_change_et_ferme_les_autres_sessions(self, creer_utilisateur, api_client, client_connecte):
        compte = creer_utilisateur()
        autre_session = api_client.post(
            reverse("accounts:login"), {"telephone": str(compte.telephone), "password": MOT_DE_PASSE}, format="json"
        ).json()["donnees"]["refresh"]

        reponse = changer(client_connecte(compte))
        assert reponse.status_code == 200, reponse.json()
        donnees = reponse.json()["donnees"]
        assert donnees["access"] and donnees["refresh"]  # nouveaux jetons pour rester connecté
        compte.refresh_from_db()
        assert compte.check_password(NOUVEAU)
        refus = api_client.post(reverse("accounts:refresh"), {"refresh": autre_session}, format="json")
        assert refus.json()["erreur"]["code"] == CodeErreur.JETON_INVALIDE
        assert api_client.post(reverse("accounts:refresh"), {"refresh": donnees["refresh"]}, format="json").status_code == 200

    def test_mot_de_passe_actuel_incorrect(self, creer_utilisateur, client_connecte):
        reponse = changer(client_connecte(creer_utilisateur()), ancien="faux")
        assert "ancien_mot_de_passe" in reponse.json()["erreur"]["details"]

    @pytest.mark.parametrize("nouveau", [MOT_DE_PASSE, "12345"])
    def test_nouveau_refuse(self, creer_utilisateur, client_connecte, nouveau):
        reponse = changer(client_connecte(creer_utilisateur()), nouveau=nouveau)
        assert "nouveau_mot_de_passe" in reponse.json()["erreur"]["details"]

    def test_connexion_obligatoire(self, api_client):
        assert changer(api_client).json()["erreur"]["code"] == CodeErreur.NON_AUTHENTIFIE


class TestMotDePasseProvisoire:
    def test_agent_cree_par_un_admin(self, creer_utilisateur, client_connecte, api_client):
        admin = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))
        service = Utilisateur.objects.get(pk=creer_utilisateur(role=Utilisateur.Role.AGENT).pk).service
        admin.post(reverse("accounts:agents"), {
            "telephone": "0196000077", "email": "nouvel.agent@mairie.bj", "nom": "Kora", "prenoms": "Aminatou",
            "role": "AGENT", "service": service.pk, "mot_de_passe": "Provisoire!2026",
        }, format="json")
        connexion = api_client.post(
            reverse("accounts:login"), {"email": "nouvel.agent@mairie.bj", "password": "Provisoire!2026"}, format="json"
        ).json()["donnees"]
        assert connexion["utilisateur"]["mot_de_passe_provisoire"] is True

        client = api_client
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {connexion['access']}")
        donnees = changer(client, ancien="Provisoire!2026").json()["donnees"]
        assert donnees["utilisateur"]["mot_de_passe_provisoire"] is False

    def test_membre_d_organisation_et_nouveau_mot_de_passe_fixe(self, creer_utilisateur, client_connecte):
        admin = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=commune_de_test()))
        organisation = Organisation.objects.create(nom="ONG", type="ONG")
        organisation.communes.add(commune_de_test())
        url = reverse("accounts:organisation-membres", args=[organisation.pk])
        membre = admin.post(url, {
            "telephone": "0195000015", "nom": "Dossou", "prenoms": "Mireille", "email": "m@ong.bj",
            "mot_de_passe": "EauPourTous!2026",
        }, format="json").json()["donnees"]
        assert Utilisateur.objects.get(pk=membre["id"]).mot_de_passe_provisoire is True

    def test_admin_qui_change_son_propre_mot_de_passe(self, creer_utilisateur, client_connecte):
        compte = creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE)
        client_connecte(compte).patch(
            reverse("accounts:agent-detail", args=[compte.pk]), {"mot_de_passe": NOUVEAU}, format="json"
        )
        compte.refresh_from_db()
        assert compte.check_password(NOUVEAU) and compte.mot_de_passe_provisoire is False

    def test_reinitialisation_retire_le_caractere_provisoire(self, creer_utilisateur, api_client):
        from django.core import mail

        compte = creer_utilisateur(role=Utilisateur.Role.AGENT, mot_de_passe_provisoire=True)
        api_client.post(reverse("accounts:password-reset"), {"email": compte.email}, format="json")
        import re

        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        api_client.post(
            reverse("accounts:password-reset-confirm"), {"email": compte.email, "code": code, "password": NOUVEAU}, format="json"
        )
        compte.refresh_from_db()
        assert compte.mot_de_passe_provisoire is False


@override_settings(EST_PRODUCTION=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
def test_production_refuse_les_emails_dans_les_journaux():
    assert "core.E003" in [message.id for message in run_checks()]


@pytest.mark.parametrize("mot_de_passe", ["482915", "afiavi", "Hounkpatin", "123456"])
def test_regle_unique_six_caracteres(api_client, sms, mot_de_passe):
    """Seule règle : 6 caractères minimum (code à 6 chiffres, prénom ou nom acceptés)."""
    corps = {"commune": commune_de_test().pk, "telephone": "0197123456", "nom": "Hounkpatin",
             "prenoms": "Afiavi", "password": mot_de_passe}
    assert api_client.post(reverse("accounts:register"), corps, format="json").status_code == 201


def test_moins_de_six_caracteres_refuse(api_client, sms):
    corps = {"commune": commune_de_test().pk, "telephone": "0197123456", "nom": "Hounkpatin",
             "prenoms": "Afiavi", "password": "12345"}
    details = api_client.post(reverse("accounts:register"), corps, format="json").json()["erreur"]["details"]
    assert details["password"] == ["Ce mot de passe est trop court. Il doit contenir au minimum 6 caractères."]
