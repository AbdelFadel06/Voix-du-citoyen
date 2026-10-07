from django.db.utils import OperationalError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import views


def test_sante_accessible_sans_authentification(db):
    reponse = APIClient().get(reverse("core:sante"))
    assert reponse.status_code == 200
    assert reponse.json() == {
        "succes": True,
        "message": None,
        "donnees": {"statut": "ok", "base_de_donnees": "ok"},
    }


def test_sante_base_indisponible(db, monkeypatch):
    class ConnexionEnPanne:
        def cursor(self):
            raise OperationalError("connexion refusée")

    # On remplace la connexion utilisée par la vue seulement (pas celle de pytest).
    monkeypatch.setattr(views, "connection", ConnexionEnPanne())
    reponse = APIClient().get(reverse("core:sante"))
    assert reponse.status_code == 503
    assert reponse.json()["erreur"]["code"] == "SERVICE_INDISPONIBLE"
    assert reponse.json()["erreur"]["details"] == {"base_de_donnees": "indisponible"}
