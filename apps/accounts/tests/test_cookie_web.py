"""Jeton `refresh` en cookie httpOnly pour le client web (en-tête `X-Client: web`, apps/accounts/cookies.py)."""

import pytest
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from conftest import MOT_DE_PASSE

pytestmark = pytest.mark.django_db

URL_LOGIN = reverse("accounts:login")
URL_REFRESH = reverse("accounts:refresh")
URL_LOGOUT = reverse("accounts:logout")
URL_CHANGEMENT = reverse("accounts:password-change")
URL_ME = reverse("accounts:me")
WEB = {"HTTP_X_CLIENT": "web"}
NOM = settings.REFRESH_COOKIE_NOM


@pytest.fixture
def membre(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.ORGANISATION)


def connexion_web(client, compte):
    reponse = client.post(URL_LOGIN, {"email": compte.email, "password": MOT_DE_PASSE}, format="json", **WEB)
    assert reponse.status_code == 200, reponse.json()
    return reponse


def test_connexion_pose_le_cookie_sans_refresh_dans_le_json(api_client, membre):
    reponse = connexion_web(api_client, membre)
    donnees = reponse.json()["donnees"]
    assert "refresh" not in donnees and donnees["access"] and donnees["utilisateur"]["id"] == membre.pk
    cookie = reponse.cookies[NOM]
    assert cookie.value and cookie["httponly"] and cookie["path"] == "/api/v1/auth/"
    assert cookie["samesite"] == "Lax" and int(cookie["max-age"]) == 30 * 24 * 3600


def test_rafraichissement_par_le_cookie_avec_rotation(api_client, membre):
    ancien = connexion_web(api_client, membre).cookies[NOM].value
    reponse = api_client.post(URL_REFRESH, {}, format="json", **WEB)  # le client de test renvoie le cookie
    assert reponse.status_code == 200, reponse.json()
    assert set(reponse.json()["donnees"]) == {"access"}
    nouveau = reponse.cookies[NOM].value
    assert nouveau and nouveau != ancien
    # L'ancien cookie (rotation) ne marche plus.
    api_client.cookies[NOM] = ancien
    rejoue = api_client.post(URL_REFRESH, {}, format="json", **WEB)
    assert rejoue.status_code == 401 and rejoue.json()["erreur"]["code"] == CodeErreur.JETON_INVALIDE


def test_cookie_ignore_sans_l_en_tete_web(api_client, membre):
    # Protection contre les requêtes forgées : sans X-Client, le cookie n'est jamais lu.
    connexion_web(api_client, membre)
    reponse = api_client.post(URL_REFRESH, {}, format="json")
    assert reponse.status_code == 400 and "refresh" in reponse.json()["erreur"]["details"]


def test_deconnexion_invalide_et_efface_le_cookie(api_client, membre):
    reponse = connexion_web(api_client, membre)
    refresh = reponse.cookies[NOM].value
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {reponse.json()['donnees']['access']}")
    deconnexion = api_client.post(URL_LOGOUT, {}, format="json", **WEB)
    assert deconnexion.status_code == 204
    assert deconnexion.cookies[NOM].value == "" and int(deconnexion.cookies[NOM]["max-age"]) == 0
    api_client.cookies[NOM] = refresh
    assert api_client.post(URL_REFRESH, {}, format="json", **WEB).status_code == 401


def test_changement_de_mot_de_passe_repose_le_cookie(api_client, membre):
    reponse = connexion_web(api_client, membre)
    ancien = reponse.cookies[NOM].value
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {reponse.json()['donnees']['access']}")
    changement = api_client.post(
        URL_CHANGEMENT, {"ancien_mot_de_passe": MOT_DE_PASSE, "nouveau_mot_de_passe": "Nouveau!2026"}, format="json", **WEB
    )
    assert changement.status_code == 200, changement.json()
    assert "refresh" not in changement.json()["donnees"]
    assert changement.cookies[NOM].value not in ("", ancien)
    assert api_client.post(URL_REFRESH, {}, format="json", **WEB).status_code == 200


def test_le_refresh_dans_le_corps_reste_accepte(api_client, membre):
    # Un client web peut toujours envoyer le refresh lui-même (ex. Postman avec X-Client: web).
    connexion_web(api_client, membre)
    refresh = api_client.post(URL_REFRESH, {}, format="json", **WEB).cookies[NOM].value
    api_client.cookies.clear()
    reponse = api_client.post(URL_REFRESH, {"refresh": refresh}, format="json", **WEB)
    assert reponse.status_code == 200 and NOM in reponse.cookies


def test_mobile_et_swagger_inchanges(api_client, creer_utilisateur):
    citoyen = creer_utilisateur()
    reponse = api_client.post(URL_LOGIN, {"telephone": str(citoyen.telephone), "password": MOT_DE_PASSE}, format="json")
    donnees = reponse.json()["donnees"]
    assert {"access", "refresh"} <= set(donnees) and NOM not in reponse.cookies
    rafraichi = api_client.post(URL_REFRESH, {"refresh": donnees["refresh"]}, format="json")
    assert {"access", "refresh"} == set(rafraichi.json()["donnees"]) and NOM not in rafraichi.cookies


def test_cors_autorise_le_cookie_et_l_en_tete(api_client, settings):
    settings.CORS_ALLOW_ALL_ORIGINS = False
    settings.CORS_ALLOWED_ORIGINS = ["https://ong.piecitizenvoice.com"]
    reponse = api_client.options(
        URL_REFRESH,
        HTTP_ORIGIN="https://ong.piecitizenvoice.com",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type, x-client",
    )
    assert reponse["access-control-allow-origin"] == "https://ong.piecitizenvoice.com"
    assert reponse["access-control-allow-credentials"] == "true"
    assert "x-client" in reponse["access-control-allow-headers"]
    # Un site non autorisé n'obtient pas l'accord : son navigateur n'enverra pas X-Client.
    refus = api_client.options(
        URL_REFRESH, HTTP_ORIGIN="https://pirate.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-client",
    )
    assert "access-control-allow-origin" not in refus
