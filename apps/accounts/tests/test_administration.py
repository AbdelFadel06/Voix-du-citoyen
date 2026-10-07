import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

URL_SERVICES = reverse("accounts:services")
URL_IMPORT = reverse("accounts:services-import")
URL_AGENTS = reverse("accounts:agents")
MOT_DE_PASSE = "Parakou!2026"


def url_agent(agent):
    return reverse("accounts:agent-detail", args=[agent.pk])


@pytest.fixture
def compte_admin(creer_utilisateur, commune):
    return creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=commune)


@pytest.fixture
def admin(compte_admin, client_connecte):
    return client_connecte(compte_admin)


@pytest.fixture
def voirie():
    return ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie et assainissement")


def nouvel_agent(**surcharges):
    return {
        "telephone": "0196000007", "nom": "Ahouansou", "prenoms": "Rodrigue",
        "email": "r.ahouansou@mairie-parakou.bj", "role": "AGENT", "mot_de_passe": MOT_DE_PASSE, **surcharges,
    }


class TestServices:
    def test_creer_et_lister(self, admin, creer_utilisateur):
        reponse = admin.post(URL_SERVICES, {"nom": "Voirie", "description": "Routes"}, format="json")
        assert reponse.status_code == 201 and reponse.json()["message"] == "Service « Voirie » créé."
        service = ServiceMunicipal.objects.get()
        creer_utilisateur(role=Utilisateur.Role.AGENT, service=service)
        creer_utilisateur(role=Utilisateur.Role.AGENT, service=service, is_active=False)
        assert admin.get(URL_SERVICES).json()["donnees"][0]["nb_agents"] == 1

    def test_nom_unique(self, admin, voirie):
        reponse = admin.post(URL_SERVICES, {"nom": "Voirie et assainissement"}, format="json")
        assert reponse.json()["erreur"]["details"]["nom"] == ["Un service porte déjà ce nom dans cette commune."]

    def test_responsable_doit_etre_du_personnel(self, admin, voirie, creer_utilisateur):
        url = reverse("accounts:service-detail", args=[voirie.pk])
        citoyen = creer_utilisateur()
        assert "responsable" in admin.patch(url, {"responsable": citoyen.pk}, format="json").json()["erreur"]["details"]
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie)
        donnees = admin.patch(url, {"responsable": agent.pk}, format="json").json()["donnees"]
        assert donnees["responsable"]["id"] == agent.pk

    def test_lecture_agents_ecriture_admins(self, voirie, creer_utilisateur, client_connecte):
        agent = client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie))
        assert agent.get(URL_SERVICES).status_code == 200
        assert agent.post(URL_SERVICES, {"nom": "X"}, format="json").status_code == 403
        assert client_connecte(creer_utilisateur()).get(URL_SERVICES).status_code == 403

    def test_import(self, admin, voirie):
        fichier = SimpleUploadedFile("s.csv", "nom;description\nVOIRIE ET ASSAINISSEMENT;Routes\nHygiène;Ordures\n".encode(), content_type="text/csv")
        donnees = admin.post(URL_IMPORT, {"fichier": fichier}, format="multipart").json()["donnees"]
        assert (donnees["crees"], donnees["mis_a_jour"]) == (1, 1)
        voirie.refresh_from_db()
        assert voirie.description == "Routes"

    def test_import_doublon_dans_le_fichier(self, admin):
        fichier = SimpleUploadedFile("s.csv", b"nom\nVoirie\nvoirie\n", content_type="text/csv")
        reponse = admin.post(URL_IMPORT, {"fichier": fichier}, format="multipart")
        assert reponse.json()["erreur"]["details"]["lignes"] == ["Ligne 3 : le service « voirie » apparaît déjà ligne 2."]


class TestAgents:
    def test_creer_un_agent_qui_peut_se_connecter(self, admin, voirie, api_client):
        reponse = admin.post(URL_AGENTS, nouvel_agent(service=voirie.pk), format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["message"] == "Compte de Rodrigue Ahouansou créé."
        assert reponse.json()["donnees"]["service"] == {"id": voirie.pk, "nom": voirie.nom}
        connexion = api_client.post(
            reverse("accounts:login"), {"email": "r.ahouansou@mairie-parakou.bj", "password": MOT_DE_PASSE}, format="json"
        )
        assert connexion.status_code == 200
        assert connexion.json()["donnees"]["utilisateur"]["role"] == "AGENT"

    def test_email_obligatoire_et_unique(self, admin, voirie, creer_utilisateur):
        sans_email = nouvel_agent(service=voirie.pk)
        del sans_email["email"]
        assert "email" in admin.post(URL_AGENTS, sans_email, format="json").json()["erreur"]["details"]
        creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie, email="pris@mairie-parakou.bj")
        reponse = admin.post(URL_AGENTS, nouvel_agent(service=voirie.pk, email="PRIS@mairie-parakou.bj"), format="json")
        assert reponse.status_code == 409
        assert reponse.json()["erreur"]["code"] == CodeErreur.EMAIL_DEJA_UTILISE

    def test_changer_l_email(self, admin, voirie, creer_utilisateur):
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie)
        admin.patch(url_agent(agent), {"email": "Nouveau@Mairie-Parakou.bj"}, format="json")
        agent.refresh_from_db()
        assert agent.email == "nouveau@mairie-parakou.bj"

    def test_un_agent_doit_avoir_un_service(self, admin):
        reponse = admin.post(URL_AGENTS, nouvel_agent(), format="json")
        assert reponse.json()["erreur"]["details"] == {"service": ["Un agent doit être rattaché à un service municipal."]}

    def test_un_admin_sans_service(self, admin):
        assert admin.post(URL_AGENTS, nouvel_agent(role="ADMIN_MAIRIE"), format="json").status_code == 201

    def test_role_citoyen_refuse(self, admin, voirie):
        reponse = admin.post(URL_AGENTS, nouvel_agent(role="CITOYEN", service=voirie.pk), format="json")
        assert "role" in reponse.json()["erreur"]["details"]

    def test_telephone_deja_utilise(self, admin, voirie, creer_utilisateur):
        creer_utilisateur(telephone="+2290196000007")
        reponse = admin.post(URL_AGENTS, nouvel_agent(service=voirie.pk), format="json")
        assert reponse.status_code == 409
        assert reponse.json()["erreur"]["code"] == CodeErreur.TELEPHONE_DEJA_UTILISE

    @pytest.mark.parametrize("surcharges, champ", [({"mot_de_passe": "1234"}, "mot_de_passe"), ({"telephone": "+33612345678"}, "telephone")])
    def test_donnees_invalides(self, admin, voirie, surcharges, champ):
        reponse = admin.post(URL_AGENTS, nouvel_agent(service=voirie.pk, **surcharges), format="json")
        assert champ in reponse.json()["erreur"]["details"]

    def test_liste_du_personnel_seulement(self, admin, voirie, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie, nom="Agent")
        creer_utilisateur(nom="Citoyen")
        noms = [a["nom"] for a in admin.get(URL_AGENTS).json()["donnees"]]
        assert "Agent" in noms and "Citoyen" not in noms
        assert [a["nom"] for a in admin.get(URL_AGENTS, {"service": voirie.pk}).json()["donnees"]] == ["Agent"]

    def test_desactiver_coupe_l_acces(self, admin, voirie, creer_utilisateur, client_connecte):
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie)
        session = client_connecte(agent)
        reponse = admin.patch(url_agent(agent), {"actif": False}, format="json")
        assert reponse.json()["donnees"]["actif"] is False
        refus = session.get(reverse("accounts:me"))
        assert refus.status_code == 403 and refus.json()["erreur"]["code"] == CodeErreur.COMPTE_DESACTIVE

    def test_changer_service_et_mot_de_passe(self, admin, voirie, creer_utilisateur, api_client):
        hygiene = ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Hygiène")
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie)
        admin.patch(url_agent(agent), {"service": hygiene.pk, "mot_de_passe": "Nouveau!2026"}, format="json")
        agent.refresh_from_db()
        assert agent.service == hygiene and agent.check_password("Nouveau!2026")

    def test_retirer_le_service_d_un_agent_refuse(self, admin, voirie, creer_utilisateur):
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie)
        assert admin.patch(url_agent(agent), {"service": None}, format="json").status_code == 400

    @pytest.mark.parametrize("changement", [{"actif": False}, {"role": "AGENT"}])
    def test_un_admin_ne_peut_pas_se_retirer_lui_meme(self, admin, compte_admin, voirie, changement):
        reponse = admin.patch(url_agent(compte_admin), {**changement, "service": voirie.pk}, format="json")
        assert reponse.json()["erreur"]["code"] == CodeErreur.ACTION_SUR_SON_PROPRE_COMPTE
        compte_admin.refresh_from_db()
        assert compte_admin.is_active and compte_admin.role == Utilisateur.Role.ADMIN_MAIRIE

    def test_un_citoyen_n_est_pas_modifiable_ici(self, admin, creer_utilisateur):
        citoyen = creer_utilisateur()
        assert admin.patch(url_agent(citoyen), {"nom": "X"}, format="json").status_code == 404

    def test_agent_peut_lire_mais_pas_creer(self, voirie, creer_utilisateur, client_connecte):
        agent = client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie))
        assert agent.get(URL_AGENTS).status_code == 200
        assert agent.post(URL_AGENTS, nouvel_agent(service=voirie.pk), format="json").status_code == 403
        assert client_connecte(creer_utilisateur(role=Utilisateur.Role.ORGANISATION)).get(URL_AGENTS).status_code == 403
