from decimal import Decimal

import pytest

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.referentiel.models import Secteur
from apps.signalements import services
from apps.territoire.models import Arrondissement, Quartier
from conftest import commune_de_test


@pytest.fixture
def voirie():
    return ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie et assainissement")


@pytest.fixture
def secteur(voirie):
    return Secteur.objects.create(
        nom="Voirie", code="VOIRIE", pour_signalement=True, service_par_defaut=voirie
    )


@pytest.fixture
def quartier(commune):
    godomey = Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")
    return Quartier.objects.create(
        arrondissement=godomey,
        nom="Togoudo",
        code="TOG",
        latitude_centre=Decimal("6.400000"),
        longitude_centre=Decimal("2.340000"),
    )


@pytest.fixture
def citoyen(creer_utilisateur):
    return creer_utilisateur(nom="Hounkpatin", prenoms="Afiavi")


@pytest.fixture
def agent(creer_utilisateur, voirie):
    return creer_utilisateur(role=Utilisateur.Role.AGENT, service=voirie, nom="Ahouansou", prenoms="Rodrigue")


@pytest.fixture
def donnees_gps(citoyen, secteur, quartier, televerser):
    """Corps valide d'un POST /signalements/ en mode GPS (avec une photo déjà envoyée)."""

    def _donnees(**surcharges):
        return {
            "secteur": secteur.pk,
            "titre": "Nid-de-poule devant l'école",
            "description_texte": "Le trou fait presque un mètre.",
            "medias": [str(televerser(citoyen).id)],
            "mode_localisation": "GPS",
            "latitude": 6.4012345,
            "longitude": 2.3412345,
            "precision_gps": 12,
            "quartier": quartier.pk,
            **surcharges,
        }

    return _donnees


@pytest.fixture
def creer_signalement(secteur, quartier, televerser):
    """Crée un signalement directement par le service (mode manuel)."""

    def _creer(auteur, **kwargs):
        options = {
            "secteur": secteur,
            "quartier": quartier,
            "mode_localisation": "MANUEL",
            "medias_ids": [televerser(auteur).id],
            "titre": "Lampadaire en panne",
            "description_texte": "Plus de lumière depuis une semaine.",
            "repere": "Carrefour de la pharmacie",
            **kwargs,
        }
        signalement, _ = services.creer_signalement(auteur=auteur, **options)
        return signalement

    return _creer
