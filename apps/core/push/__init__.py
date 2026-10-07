"""
Envoi de notifications push indépendant du fournisseur.

Le reste du code appelle uniquement `envoyer_push()` ; le fournisseur réel est choisi par
le setting PUSH_BACKEND (chemin d'import d'une sous-classe de FournisseurPush).
"""

from functools import lru_cache

from django.conf import settings
from django.utils.module_loading import import_string

from .base import EnvoiPushEchoue, FournisseurPush, JetonPushInvalide

__all__ = ["EnvoiPushEchoue", "FournisseurPush", "JetonPushInvalide", "envoyer_push", "obtenir_fournisseur"]


@lru_cache(maxsize=None)
def _charger_fournisseur(chemin):
    return import_string(chemin)()


def obtenir_fournisseur() -> FournisseurPush:
    return _charger_fournisseur(settings.PUSH_BACKEND)


def envoyer_push(jeton, titre, message, donnees=None):
    """Envoie une notification push ; lève JetonPushInvalide ou EnvoiPushEchoue en cas d'échec."""
    obtenir_fournisseur().envoyer(jeton, titre, message, {k: str(v) for k, v in (donnees or {}).items()})
