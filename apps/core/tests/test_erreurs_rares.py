"""Conversions d'erreurs plus rares : elles doivent elles aussi respecter le format commun."""

import json

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.test import RequestFactory
from rest_framework import exceptions

from apps.core.exceptions import gestionnaire_exceptions
from apps.core.views import erreur_404, erreur_500


def convertir(exc):
    reponse = gestionnaire_exceptions(exc, {"request": None})
    return reponse.status_code, reponse.data["erreur"]


def test_permission_refusee_de_django():
    assert convertir(DjangoPermissionDenied())[1]["code"] == "PERMISSION_REFUSEE"


def test_validation_sans_champ():
    statut, erreur = convertir(exceptions.ValidationError(["Ce créneau est déjà pris."]))
    assert statut == 400
    assert erreur["details"] == {"non_field_errors": ["Ce créneau est déjà pris."]}


def test_authentification_echouee_classique():
    statut, erreur = convertir(exceptions.AuthenticationFailed())
    assert (statut, erreur["code"]) == (401, "JETON_INVALIDE")


def test_trop_de_requetes_sans_delai():
    statut, erreur = convertir(exceptions.Throttled())
    assert (statut, erreur["code"], erreur["details"]) == (429, "TROP_DE_REQUETES", None)


@pytest.mark.parametrize("secondes, attendu", [(1, "1 seconde"), (45, "45 secondes"), (61, "2 minutes")])
def test_delai_lisible(secondes, attendu):
    assert attendu in convertir(exceptions.Throttled(wait=secondes))[1]["message"]


def test_format_non_supporte_garde_son_statut():
    statut, erreur = convertir(exceptions.UnsupportedMediaType("text/plain"))
    assert (statut, erreur["code"]) == (415, "VALIDATION_ERREUR")


class TestErreursHorsDRF:
    def test_500_sous_api_en_json(self):
        reponse = erreur_500(RequestFactory().get("/api/v1/signalements/"))
        assert reponse.status_code == 500
        assert json.loads(reponse.content)["erreur"]["code"] == "ERREUR_SERVEUR"

    def test_500_hors_api_en_html(self):
        reponse = erreur_500(RequestFactory().get("/admin/"))
        assert reponse.status_code == 500 and "text/html" in reponse["Content-Type"]

    def test_404_hors_api_en_html(self):
        reponse = erreur_404(RequestFactory().get("/inconnu/"), Exception())
        assert reponse.status_code == 404 and "text/html" in reponse["Content-Type"]
