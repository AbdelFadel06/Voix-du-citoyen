"""
Settings de production : gunicorn derrière un reverse proxy HTTPS (nginx).
Voir README.md, section « Déploiement ».
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False
EST_PRODUCTION = True
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# HTTPS (terminé par le reverse proxy)
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# La sonde de supervision interroge gunicorn directement, en HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/sante/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------------
# Client web
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Cache partagé entre les processus gunicorn : sans lui, chaque processus aurait son propre
# compteur et la limitation de débit (OTP, signalements, envois) ne fonctionnerait pas.
# Table créée par `python manage.py createcachetable`.
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_django",
    }
}

# ---------------------------------------------------------------------------
# Journalisation : tout sur la sortie standard (récupérée par Docker / systemd)
# ---------------------------------------------------------------------------

LOGGING["root"]["level"] = env("LOG_LEVEL", default="INFO")  # noqa: F405
LOGGING["loggers"] = {  # noqa: F405
    "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
}
