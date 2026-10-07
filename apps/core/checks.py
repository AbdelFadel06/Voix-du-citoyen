from django.conf import settings
from django.core.checks import Error, register


@register()
def verifier_backend_sms(app_configs, **kwargs):
    """En production, interdit le backend console : les SMS ne partiraient jamais."""
    if getattr(settings, "EST_PRODUCTION", False) and settings.SMS_BACKEND == settings.SMS_BACKEND_CONSOLE:
        return [
            Error(
                "SMS_BACKEND utilise le backend console en production : "
                "aucun SMS (code OTP) ne serait envoyé.",
                hint="Renseignez SMS_BACKEND dans le .env avec un vrai fournisseur SMS.",
                id="core.E001",
            )
        ]
    return []


@register()
def verifier_backend_push(app_configs, **kwargs):
    """En production, interdit le backend console : aucune notification push ne partirait."""
    if getattr(settings, "EST_PRODUCTION", False) and settings.PUSH_BACKEND == settings.PUSH_BACKEND_CONSOLE:
        return [
            Error(
                "PUSH_BACKEND utilise le backend console en production : "
                "aucune notification push ne serait envoyée.",
                hint="Renseignez PUSH_BACKEND dans le .env avec un vrai fournisseur (Firebase).",
                id="core.E002",
            )
        ]
    return []


def bloquer_si_erreurs():
    """
    Lance les checks au démarrage du serveur (gunicorn ne le fait pas, contrairement à
    manage.py) et refuse de démarrer si l'un d'eux est une erreur.
    """
    from django.core.checks import run_checks
    from django.core.exceptions import ImproperlyConfigured

    erreurs = [message for message in run_checks() if message.is_serious()]
    if erreurs:
        raise ImproperlyConfigured("\n".join(str(erreur) for erreur in erreurs))
