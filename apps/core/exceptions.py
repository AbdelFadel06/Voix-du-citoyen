import logging
import math

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import set_rollback
from rest_framework_simplejwt.exceptions import InvalidToken

from .codes_erreur import CodeErreur, code_pour_statut, message_par_defaut, statut_http
from .reponses import corps_erreur

logger = logging.getLogger(__name__)


class ErreurMetier(exceptions.APIException):
    """
    Erreur métier à lever depuis les services : le code (CodeErreur) fixe le statut HTTP
    et le message par défaut, qu'on peut préciser au cas par cas.

        raise ErreurMetier(CodeErreur.OTP_EXPIRE)
        raise ErreurMetier(CodeErreur.OTP_INVALIDE, "Code incorrect.", details={...})
    """

    def __init__(self, code, message=None, status_code=None, details=None):
        self.code_erreur = CodeErreur(code)
        self.message = message or message_par_defaut(self.code_erreur)
        self.status_code = status_code or statut_http(self.code_erreur)
        self.details = details
        super().__init__(detail=self.message, code=self.code_erreur.value)


def gestionnaire_exceptions(exc, context):
    """Convertit toute exception levée dans une vue DRF au format d'erreur commun."""
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if not isinstance(exc, exceptions.APIException):
        requete = context.get("request")
        logger.error(
            "Erreur interne sur %s %s",
            getattr(requete, "method", "?"),
            getattr(requete, "path", "?"),
            exc_info=exc,
        )
        set_rollback()
        code = CodeErreur.ERREUR_SERVEUR
        return Response(corps_erreur(code, message_par_defaut(code)), status=statut_http(code))

    code, message, details, statut = _convertir(exc)
    entetes = {}
    if getattr(exc, "auth_header", None):
        entetes["WWW-Authenticate"] = exc.auth_header
    if getattr(exc, "wait", None):
        entetes["Retry-After"] = str(math.ceil(exc.wait))

    set_rollback()
    return Response(corps_erreur(code, message, details), status=statut, headers=entetes)


def _convertir(exc):
    """Renvoie (code, message, details, statut HTTP) pour une APIException."""
    if isinstance(exc, ErreurMetier):
        return exc.code_erreur, exc.message, exc.details, exc.status_code

    if isinstance(exc, exceptions.ValidationError):
        details = exc.detail
        if not isinstance(details, dict):
            details = {api_settings.NON_FIELD_ERRORS_KEY: details}
        return _generique(CodeErreur.VALIDATION_ERREUR, details=details)

    if isinstance(exc, exceptions.ParseError):
        return _generique(
            CodeErreur.VALIDATION_ERREUR, "Le contenu de la requête est mal formé."
        )

    if isinstance(exc, exceptions.NotAuthenticated):
        return _generique(CodeErreur.NON_AUTHENTIFIE)

    if isinstance(exc, exceptions.AuthenticationFailed):
        # simplejwt met son code dans la valeur detail["code"] ; DRF dans get_codes().
        if isinstance(exc.detail, dict):
            code_jwt = str(exc.detail.get("code", ""))
        else:
            code_jwt = exc.get_codes()
        if not isinstance(exc, InvalidToken) and code_jwt == "user_inactive":
            return _generique(CodeErreur.COMPTE_DESACTIVE)
        return _generique(CodeErreur.JETON_INVALIDE)

    if isinstance(exc, exceptions.PermissionDenied):
        # Les permissions de l'API ont des messages explicites en français.
        return _generique(CodeErreur.PERMISSION_REFUSEE, str(exc.detail))

    if isinstance(exc, exceptions.NotFound):
        return _generique(CodeErreur.RESSOURCE_INTROUVABLE)

    if isinstance(exc, exceptions.MethodNotAllowed):
        return _generique(CodeErreur.METHODE_NON_AUTORISEE)

    if isinstance(exc, exceptions.Throttled):
        if exc.wait is None:
            return _generique(CodeErreur.TROP_DE_REQUETES)
        secondes = math.ceil(exc.wait)
        return _generique(
            CodeErreur.TROP_DE_REQUETES,
            f"Trop de demandes. Réessayez dans {_duree_lisible(secondes)}.",
            details={"attente_secondes": secondes},
        )

    # Autres erreurs DRF (406, 415…) : code générique selon le statut, statut d'origine conservé.
    return code_pour_statut(exc.status_code), str(exc.detail), None, exc.status_code


def _generique(code, message=None, details=None):
    return code, message or message_par_defaut(code), details, statut_http(code)


def _duree_lisible(secondes):
    if secondes < 60:
        return f"{secondes} seconde{'s' if secondes > 1 else ''}"
    minutes = math.ceil(secondes / 60)
    return f"{minutes} minute{'s' if minutes > 1 else ''}"
