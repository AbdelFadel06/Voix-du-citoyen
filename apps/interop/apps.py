from django.apps import AppConfig


class InteropConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.interop"
    verbose_name = "Interopérabilité"

    def ready(self):
        from . import schema  # noqa: F401  (documente l'authentification par clé dans OpenAPI)
