"""Espace mairie (/api/v1/mairie/…) et routes générales (apps/core/espaces.py)."""

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur

pytestmark = pytest.mark.django_db

VOLETS = [
    "signalements/", "suggestions/", "realisations/", "secteurs/", "quartiers/", "arrondissements/",
    "communes/", "services/", "agents/", "organisations/", "dashboard/synthese/",
]
COMMUNS = ["auth/me/", "notifications/"]


def client_brut(utilisateur):
    """Client sans redirection automatique vers l'espace mairie (voir conftest.ClientMairie)."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {services.generer_jetons(utilisateur)['access']}")
    return client


@pytest.fixture
def agent(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.AGENT)


class TestMairieDeCommune:
    @pytest.mark.parametrize("volet", VOLETS)
    def test_refusee_sur_les_routes_generales(self, agent, volet):
        reponse = client_brut(agent).get(f"/api/v1/{volet}")
        assert reponse.status_code == 403 and reponse.json()["erreur"]["code"] == CodeErreur.ESPACE_MAIRIE_REQUIS

    @pytest.mark.parametrize("volet", VOLETS + ["dashboard/evolution/", "dashboard/carte/"])
    def test_acceptee_dans_l_espace_mairie(self, agent, volet):
        assert client_brut(agent).get(f"/api/v1/mairie/{volet}").status_code == 200

    @pytest.mark.parametrize("volet", COMMUNS)
    def test_routes_communes_inchangees(self, agent, volet):
        assert client_brut(agent).get(f"/api/v1/{volet}").status_code == 200

    def test_pas_de_synthese_separee_par_secteur_ou_quartier(self, agent):
        for volet in ("dashboard/par-secteur/", "dashboard/par-quartier/", "auth/me/"):
            assert client_brut(agent).get(f"/api/v1/mairie/{volet}").status_code == 404


def test_actions_des_citoyens_et_organisations_absentes_de_l_espace_mairie(agent):
    client = client_brut(agent)
    assert client.post("/api/v1/mairie/signalements/", {}, format="json").status_code == 405
    assert client.post("/api/v1/mairie/suggestions/", {}, format="json").status_code == 405
    for chemin in ("signalements/1/prendre-en-charge/", "suggestions/1/soutenir/"):
        assert client.post(f"/api/v1/mairie/{chemin}").status_code == 404, chemin
    # « mes-signalements » n'existe pas : lu comme un identifiant de signalement inconnu.
    assert client.get("/api/v1/mairie/signalements/mes-signalements/").status_code == 404


class TestAutresComptes:
    @pytest.mark.parametrize(
        "compte",
        [
            {"role": Utilisateur.Role.CITOYEN},
            {"role": Utilisateur.Role.ORGANISATION},
            {"role": Utilisateur.Role.ADMIN_MAIRIE, "commune": None},  # admin de la plateforme
        ],
        ids=["citoyen", "organisation", "plateforme"],
    )
    def test_refuses_dans_l_espace_mairie(self, creer_utilisateur, compte):
        client = client_brut(creer_utilisateur(**compte))
        for volet in VOLETS:
            reponse = client.get(f"/api/v1/mairie/{volet}")
            assert reponse.status_code == 403, volet
            assert reponse.json()["erreur"]["code"] == CodeErreur.PERMISSION_REFUSEE

    def test_sans_compte(self, api_client):
        assert api_client.get("/api/v1/mairie/signalements/").status_code == 401
        # Les réalisations publiées restent publiques sur la route générale seulement.
        assert api_client.get("/api/v1/realisations/").status_code == 200
        assert api_client.get("/api/v1/mairie/realisations/").status_code == 401

    def test_admin_de_la_plateforme_garde_les_routes_generales(self, creer_utilisateur):
        client = client_brut(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=None))
        assert client.get("/api/v1/signalements/").status_code == 200
        assert client.get("/api/v1/dashboard/par-secteur/").status_code == 200


def test_aucun_parametre_commune_dans_l_espace_mairie():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    for chemin, item in schema["paths"].items():
        if not chemin.startswith("/api/v1/mairie/"):
            continue
        for methode, operation in item.items():
            if methode != "get":
                continue
            noms = {p["name"] for p in operation.get("parameters", [])}
            assert "commune" not in noms, f"{methode.upper()} {chemin}"
