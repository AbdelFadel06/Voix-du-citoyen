"""Settings de développement local."""

from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, SMS_BACKEND_CONSOLE, env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"])

# En local, le web et l'émulateur mobile tournent sur des ports variables.
CORS_ALLOW_ALL_ORIGINS = True

# Les SMS (codes OTP) s'affichent dans le terminal de runserver.
SMS_BACKEND = env("SMS_BACKEND", default=SMS_BACKEND_CONSOLE)

# API navigable pour faciliter les essais.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "apps.core.renderers.ReponseJSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "apps.core.authentication.AuthentificationJWT",
    "rest_framework.authentication.SessionAuthentication",
]
