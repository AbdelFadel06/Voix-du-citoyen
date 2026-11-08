"""Fournisseur NotifyHub (apps/core/sms/backends/notifyhub.py), sans appel réseau réel."""

import io
import json
import logging
import urllib.error

import pytest

from apps.core.checks import verifier_notifyhub
from apps.core.sms import Canal, EnvoiSMSEchoue
from apps.core.sms.backends import notifyhub
from apps.core.sms.backends.notifyhub import NotifyHubSMS

NUMERO = "+33612345678"
MESSAGE = "Voix du Citoyen : votre code de vérification est 482913."


@pytest.fixture
def config(settings):
    settings.SMS_BACKEND = settings.SMS_BACKEND_NOTIFYHUB
    settings.NOTIFYHUB_URL = "https://notifyhub.test/api/v1/"
    settings.NOTIFYHUB_CLE = "gd_test_secret"
    settings.NOTIFYHUB_WHATSAPP_MODELE = "code_verification"
    settings.NOTIFYHUB_WHATSAPP_LANGUE = "fr"
    settings.NOTIFYHUB_SMS_EXPEDITEUR = "VOIXCITOYEN"
    return settings


class FausseReponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def requetes(monkeypatch):
    """Intercepte urlopen : `requetes.reponse` (octets) ou `requetes.erreur` (exception à lever)."""

    class Journal(list):
        reponse = b'{"success": true, "data": {"id": "msg_1", "status": "queued"}}'
        erreur = None

    journal = Journal()

    def urlopen(requete, timeout):
        journal.append((requete, json.loads(requete.data), timeout))
        if journal.erreur:
            raise journal.erreur
        return FausseReponse(journal.reponse)

    monkeypatch.setattr(notifyhub.urllib.request, "urlopen", urlopen)
    return journal


def test_whatsapp_par_modele_avec_le_code(config, requetes):
    NotifyHubSMS().envoyer(NUMERO, MESSAGE, Canal.WHATSAPP, code="482913")
    requete, corps, delai = requetes[0]
    assert requete.full_url == "https://notifyhub.test/api/v1/messages/whatsapp"
    assert requete.get_header("Authorization") == "Bearer gd_test_secret"
    assert requete.get_header("Idempotency-key")
    assert corps == {"to": NUMERO, "template": {"name": "code_verification", "language": "fr", "variables": ["482913"]}}
    assert delai == config.NOTIFYHUB_DELAI


def test_sms_avec_expediteur(config, requetes):
    NotifyHubSMS().envoyer(NUMERO, MESSAGE, Canal.SMS, code="482913")
    requete, corps, _ = requetes[0]
    assert requete.full_url.endswith("/messages/sms")
    assert corps == {"from": "VOIXCITOYEN", "to": NUMERO, "message": MESSAGE, "type": "otp"}


@pytest.mark.parametrize("reglage, canal", [("NOTIFYHUB_WHATSAPP_MODELE", Canal.WHATSAPP), ("NOTIFYHUB_SMS_EXPEDITEUR", Canal.SMS)])
def test_canal_non_configure(config, requetes, reglage, canal):
    setattr(config, reglage, "")
    with pytest.raises(EnvoiSMSEchoue):
        NotifyHubSMS().envoyer(NUMERO, MESSAGE, canal, code="482913")
    assert requetes == []


def test_refus_de_notifyhub_sans_le_code_dans_les_journaux(config, requetes, caplog):
    corps = b'{"success": false, "error": {"code": "INSUFFICIENT_BALANCE", "message": "Solde insuffisant"}}'
    requetes.erreur = urllib.error.HTTPError("url", 402, "Payment Required", {}, io.BytesIO(corps))
    with caplog.at_level(logging.ERROR), pytest.raises(EnvoiSMSEchoue, match="INSUFFICIENT_BALANCE"):
        NotifyHubSMS().envoyer(NUMERO, MESSAGE, Canal.WHATSAPP, code="482913")
    assert "INSUFFICIENT_BALANCE" in caplog.text and "482913" not in caplog.text


@pytest.mark.parametrize(
    "erreur", [urllib.error.URLError("dns"), TimeoutError()], ids=["injoignable", "delai"]
)
def test_notifyhub_injoignable(config, requetes, erreur):
    requetes.erreur = erreur
    with pytest.raises(EnvoiSMSEchoue):
        NotifyHubSMS().envoyer(NUMERO, MESSAGE, Canal.WHATSAPP, code="482913")


def test_reponse_200_en_echec(config, requetes):
    requetes.reponse = b'{"success": false, "error": {"code": "INVALID_RECIPIENT"}}'
    with pytest.raises(EnvoiSMSEchoue, match="INVALID_RECIPIENT"):
        NotifyHubSMS().envoyer(NUMERO, MESSAGE, Canal.SMS)


def test_controle_de_configuration(config):
    assert verifier_notifyhub(None) == []
    config.NOTIFYHUB_SMS_EXPEDITEUR = ""
    assert [a.id for a in verifier_notifyhub(None)] == ["core.W002"]
    config.NOTIFYHUB_CLE = ""
    assert [a.id for a in verifier_notifyhub(None)] == ["core.E004"]
    config.SMS_BACKEND = "apps.core.sms.backends.memoire.MemoireSMS"
    assert verifier_notifyhub(None) == []
