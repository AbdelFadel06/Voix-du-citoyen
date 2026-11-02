"""
Jeton `refresh` en cookie `httpOnly` pour le client web.

Le web envoie l'en-tête `X-Client: web` sur `/auth/login/`, `/auth/refresh/`, `/auth/logout/` et
`/auth/password/change/` : le `refresh` est alors posé dans un cookie `httpOnly` (illisible par le
JavaScript) au lieu d'être renvoyé dans le JSON, puis relu dans ce cookie. Sans cet en-tête
(mobile, Swagger, Postman, IBDC), rien ne change : les jetons restent dans le JSON.

Le cookie n'est lu que si la requête porte `X-Client: web` : un site tiers ne peut pas ajouter
cet en-tête sans l'accord de CORS (origines autorisées seulement), ce qui protège `refresh` et
`logout` contre les requêtes forgées (CSRF), en plus de `SameSite`.
"""

from django.conf import settings
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from apps.core.reponses import reponse_succes

ENTETE_CLIENT = "HTTP_X_CLIENT"
CLIENT_WEB = "web"


def mode_cookie(request):
    return request.META.get(ENTETE_CLIENT, "").strip().lower() == CLIENT_WEB


def refresh_du_cookie(request):
    """`refresh` envoyé par le navigateur, seulement pour un client web déclaré."""
    return request.COOKIES.get(settings.REFRESH_COOKIE_NOM) if mode_cookie(request) else None


def poser(reponse, refresh):
    reponse.set_cookie(
        settings.REFRESH_COOKIE_NOM,
        refresh,
        max_age=int(jwt_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        path=settings.REFRESH_COOKIE_CHEMIN,
        domain=settings.REFRESH_COOKIE_DOMAINE,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )
    return reponse


def effacer(reponse):
    reponse.delete_cookie(
        settings.REFRESH_COOKIE_NOM,
        path=settings.REFRESH_COOKIE_CHEMIN,
        domain=settings.REFRESH_COOKIE_DOMAINE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )
    return reponse


def reponse_jetons(request, donnees, message=None):
    """Réponse avec des jetons : en mode web, le `refresh` part dans le cookie, pas dans le JSON."""
    if not mode_cookie(request):
        return reponse_succes(donnees, message)
    donnees = dict(donnees)
    refresh = donnees.pop("refresh")
    return poser(reponse_succes(donnees, message), refresh)
