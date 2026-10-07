"""
Envoi de SMS indépendant du fournisseur.

Le reste du code appelle uniquement `envoyer_sms()` ; le fournisseur réel est choisi
par le setting SMS_BACKEND (chemin d'import d'une sous-classe de FournisseurSMS).
"""

from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from .base import EnvoiSMSEchoue, FournisseurSMS

__all__ = ["EnvoiSMSEchoue", "FournisseurSMS", "envoyer_sms", "obtenir_fournisseur"]


@lru_cache(maxsize=None)
def _charger_fournisseur(chemin):
    return import_string(chemin)()


def obtenir_fournisseur() -> FournisseurSMS:
    """Renvoie l'instance du fournisseur configuré (créée une seule fois par chemin)."""
    return _charger_fournisseur(settings.SMS_BACKEND)


def envoyer_sms(telephone, message):
    """Envoie un SMS ; lève EnvoiSMSEchoue si le fournisseur échoue."""
    obtenir_fournisseur().envoyer(str(telephone), message)
