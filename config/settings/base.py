"""
Settings communs à tous les environnements.

Toute valeur sensible ou dépendante de l'environnement est lue depuis `.env`
via django-environ. Les fichiers `dev.py` et `prod.py` surchargent ce socle.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "phonenumber_field",
    "storages",
]

LOCAL_APPS = [
    "apps.core",
    "apps.territoire",
    "apps.accounts",
    "apps.referentiel",
    "apps.medias",
    "apps.signalements",
    "apps.suggestions",
    "apps.realisations",
    "apps.notifications",
    "apps.dashboard",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.Utilisateur"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Base de données (PostgreSQL)
# ---------------------------------------------------------------------------

# Hébergeurs (Render…) : une seule variable DATABASE_URL ; sinon les variables POSTGRES_*.
if env("DATABASE_URL", default=None):
    BASE_DE_DONNEES = env.db_url("DATABASE_URL")
else:
    BASE_DE_DONNEES = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
    }
DATABASES = {"default": {**BASE_DE_DONNEES, "CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Porto-Novo"
USE_I18N = True
USE_TZ = True

PHONENUMBER_DEFAULT_REGION = "BJ"
PHONENUMBER_DB_FORMAT = "E164"

# ---------------------------------------------------------------------------
# Fichiers statiques et médias
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Les FileField / ImageField passent par le stockage "default" : disque local par défaut,
# stockage objet S3-compatible (MinIO, AWS, Scaleway…) avec USE_S3=True. Le code métier
# ne change pas : seul le backend de stockage change.
USE_S3 = env.bool("USE_S3", default=False)

if USE_S3:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default=None)
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    # URL signées (temporaires) : les fichiers ne sont pas publics sur le stockage.
    AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=True)
    AWS_QUERYSTRING_EXPIRE = 3600
    STOCKAGE_FICHIERS = "storages.backends.s3.S3Storage"
else:
    STOCKAGE_FICHIERS = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {"BACKEND": STOCKAGE_FICHIERS},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Limite des envois (la plus grosse : vidéo de 25 Mo + miniature) ; à aligner avec le
# reverse proxy (client_max_body_size de nginx).
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440  # corps hors fichiers (JSON…), 2,5 Mo
FILE_UPLOAD_PERMISSIONS = 0o644

# ---------------------------------------------------------------------------
# Cache (utilisé par la limitation de débit)
# ---------------------------------------------------------------------------

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.core.authentication.AuthentificationJWT",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "apps.core.renderers.ReponseJSONRenderer",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "apps.core.filters.Recherche",
        "apps.core.filters.Tri",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.PaginationStandard",
    "PAGE_SIZE": 20,
    "SEARCH_PARAM": "recherche",
    "ORDERING_PARAM": "tri",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.gestionnaire_exceptions",
    "DEFAULT_THROTTLE_RATES": {
        "otp": "5/hour",
        "creation_signalement": "10/day",
        "televersement": "60/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Voix du Citoyen — API",
    # L'introduction détaillée et les tags sont ajoutés par apps.core.schema.completer_documentation.
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "CodeErreurEnum": "apps.core.schema.CHOIX_CODES_ERREUR",
        "StatutSignalementEnum": "apps.signalements.models.Signalement.Statut",
        "NouveauStatutSignalementEnum": "apps.signalements.serializers.CHOIX_STATUTS_CIBLES",
        "StatutMediaEnum": "apps.medias.models.Media.Statut",
        "RoleEnum": "apps.accounts.models.Utilisateur.Role",
        "RolePersonnelEnum": "apps.accounts.serializers.ROLES_PERSONNEL",
        "TypeMediaEnum": "apps.medias.models.Media.Type",
        "TypeNotificationEnum": "apps.notifications.models.Notification.Type",
        "StatutRealisationEnum": "apps.realisations.models.Realisation.Statut",
        "TypeEvenementSignalementEnum": "apps.signalements.models.SuiviSignalement.TypeEvenement",
        "TypeEvenementSuggestionEnum": "apps.suggestions.models.SuiviSuggestion.TypeEvenement",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.schema.completer_documentation",
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 0,
        "tryItOutEnabled": True,
    },
}

# ---------------------------------------------------------------------------
# SMS (voir apps/core/sms/)
# ---------------------------------------------------------------------------

SMS_BACKEND_CONSOLE = "apps.core.sms.backends.console.ConsoleSMS"
SMS_BACKEND = env("SMS_BACKEND", default=SMS_BACKEND_CONSOLE)

# ---------------------------------------------------------------------------
# Notifications push (voir apps/core/push/)
# ---------------------------------------------------------------------------

PUSH_BACKEND_CONSOLE = "apps.core.push.backends.console.ConsolePush"
PUSH_BACKEND = env("PUSH_BACKEND", default=PUSH_BACKEND_CONSOLE)

# Passe à True dans prod.py : active les contrôles qui bloquent le démarrage.
EST_PRODUCTION = False

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# Le mobile n'est pas concerné par CORS ; seul le client web l'est.
# En dev tout est autorisé (voir dev.py) ; les origines de prod sont dans prod.py.
CORS_ALLOWED_ORIGINS = []

# ---------------------------------------------------------------------------
# Journalisation
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name} : {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
