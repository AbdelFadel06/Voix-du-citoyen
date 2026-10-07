from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.codes_erreur import CodeErreur
from apps.territoire.models import Arrondissement, Commune, Quartier
from apps.territoire.services import distance_metres

pytestmark = pytest.mark.django_db

URL_LISTE = reverse("territoire:quartiers")
URL_PROCHE = reverse("territoire:quartier-proche")


@pytest.fixture
def quartiers(commune):
    godomey = Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")
    calavi = Arrondissement.objects.create(commune=commune, nom="Calavi", code="CAL")

    def creer(arrondissement, nom, lat=None, lng=None, actif=True):
        return Quartier.objects.create(
            arrondissement=arrondissement,
            nom=nom,
            code=nom[:3].upper(),
            latitude_centre=Decimal(lat) if lat else None,
            longitude_centre=Decimal(lng) if lng else None,
            actif=actif,
        )

    return {
        "togoudo": creer(godomey, "Togoudo", "6.400000", "2.340000"),
        "cococodji": creer(godomey, "Cococodji", "6.420000", "2.290000"),
        "zogbadje": creer(calavi, "Zogbadjè", "6.450000", "2.350000"),
        "sans_centre": creer(calavi, "Kpota"),
        "inactif": creer(calavi, "Ancien quartier", "6.400100", "2.340100", actif=False),
    }


@pytest.fixture
def client(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur())


class TestListe:
    def test_non_authentifie(self, api_client):
        assert api_client.get(URL_LISTE).status_code == 401

    def test_actifs_seulement_tries_par_nom(self, quartiers, client):
        corps = client.get(URL_LISTE).json()
        assert "pagination" not in corps
        noms = [q["nom"] for q in corps["donnees"]]
        assert noms == ["Cococodji", "Kpota", "Togoudo", "Zogbadjè"]

    def test_arrondissement_imbrique(self, quartiers, client):
        togoudo = next(q for q in client.get(URL_LISTE).json()["donnees"] if q["nom"] == "Togoudo")
        assert togoudo["arrondissement"] == {
            "id": quartiers["togoudo"].arrondissement_id,
            "nom": "Godomey",
        }
        assert togoudo["latitude_centre"] == "6.400000"

    def test_filtre_par_arrondissement(self, quartiers, client):
        arrondissement = quartiers["zogbadje"].arrondissement_id
        noms = [q["nom"] for q in client.get(URL_LISTE, {"arrondissement": arrondissement}).json()["donnees"]]
        assert noms == ["Kpota", "Zogbadjè"]

    def test_recherche(self, quartiers, client):
        noms = [q["nom"] for q in client.get(URL_LISTE, {"recherche": "togo"}).json()["donnees"]]
        assert noms == ["Togoudo"]


class TestProche:
    def test_propose_le_quartier_le_plus_proche(self, quartiers, client):
        reponse = client.get(URL_PROCHE, {"lat": 6.401, "lng": 2.341})
        assert reponse.status_code == 200
        donnees = reponse.json()["donnees"]
        assert donnees["quartier"]["nom"] == "Togoudo"
        assert 100 < donnees["distance_metres"] < 200

    def test_ignore_les_quartiers_inactifs_et_sans_centre(self, quartiers, client):
        # Le point est sur le quartier inactif : c'est Togoudo, actif, qui est proposé.
        donnees = client.get(URL_PROCHE, {"lat": 6.4001, "lng": 2.3401}).json()["donnees"]
        assert donnees["quartier"]["nom"] == "Togoudo"

    def test_hors_de_la_commune(self, quartiers, client):
        reponse = client.get(URL_PROCHE, {"lat": 6.37, "lng": 2.34})  # Cotonou, au sud
        assert reponse.status_code == 400
        assert reponse.json()["erreur"]["code"] == CodeErreur.COORDONNEES_HORS_COMMUNE

    @pytest.mark.parametrize(
        "params", [{}, {"lat": 6.4}, {"lng": 2.3}, {"lat": "abc", "lng": 2.3}, {"lat": 95, "lng": 2.3}]
    )
    def test_parametres_invalides(self, quartiers, client, params):
        reponse = client.get(URL_PROCHE, params)
        assert reponse.status_code == 400
        assert reponse.json()["erreur"]["code"] == CodeErreur.VALIDATION_ERREUR

    def test_aucun_quartier_localise(self, commune, client):
        reponse = client.get(URL_PROCHE, {"lat": 6.4, "lng": 2.34})
        assert reponse.status_code == 404
        assert reponse.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE

    def test_non_authentifie(self, api_client):
        assert api_client.get(URL_PROCHE, {"lat": 6.4, "lng": 2.34}).status_code == 401


def test_distance_haversine():
    # 0,01° de latitude ≈ 1 112 m.
    assert 1100 < distance_metres(6.40, 2.34, 6.41, 2.34) < 1125
    assert distance_metres(6.4, 2.34, 6.4, 2.34) == 0
