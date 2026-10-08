"""Le fichier de données réelles de Parakou s'importe sans erreur (docs/donnees/)."""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.territoire.models import Arrondissement, Quartier

pytestmark = pytest.mark.django_db

FICHIER = Path(settings.BASE_DIR) / "docs" / "donnees" / "parakou_quartiers.csv"
PARAKOU = {
    "nom": "Parakou", "code": "PKO", "departement": "Borgou",
    "lat_min": "9.232868", "lat_max": "9.441936", "lng_min": "2.480804", "lng_max": "2.771794",
}


def test_commune_et_58_quartiers(creer_utilisateur, client_connecte):
    admin = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))
    assert admin.post(reverse("territoire:communes"), PARAKOU, format="json").status_code == 201
    fichier = SimpleUploadedFile("parakou_quartiers.csv", FICHIER.read_bytes(), content_type="text/csv")
    reponse = admin.post(reverse("territoire:quartiers-import"), {"fichier": fichier}, format="multipart")
    assert reponse.status_code == 200, reponse.json()
    assert reponse.json()["donnees"]["arrondissements_crees"] == 3
    assert Quartier.objects.count() == 58
    assert list(Arrondissement.objects.order_by("code").values_list("code", flat=True)) == ["PKO-1", "PKO-2", "PKO-3"]
    assert Quartier.objects.filter(latitude_centre__isnull=False).count() == 15
