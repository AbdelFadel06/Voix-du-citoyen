import pytest
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured

from apps.core import sms
from apps.core.checks import bloquer_si_erreurs, verifier_backend_sms
from apps.core.sms import EnvoiSMSEchoue, FournisseurSMS, envoyer_sms
from apps.core.sms.backends.console import ConsoleSMS
from apps.core.sms.backends.memoire import MemoireSMS

CONSOLE = "apps.core.sms.backends.console.ConsoleSMS"


class FauxFournisseur(FournisseurSMS):
    envois = []

    def envoyer(self, telephone, message):
        self.envois.append((telephone, message))


def test_envoyer_sms_utilise_le_backend_configure():
    envoyer_sms("+2290197000001", "Bonjour")
    assert [(s.telephone, s.message) for s in MemoireSMS.boite] == [("+2290197000001", "Bonjour")]


def test_un_nouveau_fournisseur_se_branche_par_le_setting(settings):
    settings.SMS_BACKEND = "apps.core.tests.test_sms.FauxFournisseur"
    envoyer_sms("+2290197000001", "Bonjour")
    assert FauxFournisseur.envois == [("+2290197000001", "Bonjour")]
    assert MemoireSMS.boite == []


def test_le_fournisseur_est_mis_en_cache():
    assert sms.obtenir_fournisseur() is sms.obtenir_fournisseur()


def test_le_numero_est_converti_en_texte():
    from phonenumber_field.phonenumber import to_python

    envoyer_sms(to_python("0197000001"), "Bonjour")
    assert MemoireSMS.boite[0].telephone == "+2290197000001"


def test_l_echec_du_fournisseur_est_propage():
    MemoireSMS.simuler_echec = True
    with pytest.raises(EnvoiSMSEchoue):
        envoyer_sms("+2290197000001", "Bonjour")


def test_un_fournisseur_doit_implementer_envoyer():
    class Incomplet(FournisseurSMS):
        pass

    with pytest.raises(TypeError):
        Incomplet()


def test_backend_console_affiche_un_encadre(caplog):
    caplog.set_level("INFO")
    ConsoleSMS().envoyer("+2290197000001", "Voix du Citoyen : votre code est 123456.")
    assert "╔" in caplog.text and "╚" in caplog.text
    assert "+2290197000001" in caplog.text
    assert "123456" in caplog.text


class TestCheckProduction:
    def test_console_interdit_en_production(self, settings):
        settings.EST_PRODUCTION = True
        settings.SMS_BACKEND = CONSOLE
        erreurs = verifier_backend_sms(None)
        assert len(erreurs) == 1
        assert isinstance(erreurs[0], Error) and erreurs[0].id == "core.E001"

    def test_le_demarrage_est_bloque(self, settings):
        settings.EST_PRODUCTION = True
        settings.SMS_BACKEND = CONSOLE
        with pytest.raises(ImproperlyConfigured, match="core.E001"):
            bloquer_si_erreurs()

    def test_vrai_fournisseur_accepte_en_production(self, settings):
        settings.EST_PRODUCTION = True
        settings.SMS_BACKEND = "apps.core.tests.test_sms.FauxFournisseur"
        assert verifier_backend_sms(None) == []

    def test_console_accepte_hors_production(self, settings):
        settings.EST_PRODUCTION = False
        settings.SMS_BACKEND = CONSOLE
        assert verifier_backend_sms(None) == []
