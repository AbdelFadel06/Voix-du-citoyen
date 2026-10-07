from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db


@pytest.fixture
def commune():
    return Commune.objects.create(
        nom="Abomey-Calavi",
        code="ABC",
        departement="Atlantique",
        lat_min=Decimal("6.380000"),
        lat_max=Decimal("6.650000"),
        lng_min=Decimal("2.230000"),
        lng_max=Decimal("2.450000"),
    )


@pytest.fixture
def arrondissement(commune):
    return Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")


def test_commune_contient_un_point_dans_son_emprise(commune):
    assert commune.contient(Decimal("6.450000"), Decimal("2.350000"))


def test_commune_ne_contient_pas_un_point_hors_emprise(commune):
    assert not commune.contient(Decimal("6.360000"), Decimal("2.350000"))
    assert not commune.contient(Decimal("6.450000"), Decimal("2.500000"))


def test_arrondissement_unique_par_commune(commune, arrondissement):
    with pytest.raises(IntegrityError):
        Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD2")


def test_quartier_unique_par_arrondissement(arrondissement):
    Quartier.objects.create(arrondissement=arrondissement, nom="Togoudo", code="TOG")
    with pytest.raises(IntegrityError):
        Quartier.objects.create(arrondissement=arrondissement, nom="Togoudo", code="TOG2")


def test_quartier_actif_par_defaut(arrondissement):
    quartier = Quartier.objects.create(arrondissement=arrondissement, nom="Togoudo", code="TOG")
    assert quartier.actif
