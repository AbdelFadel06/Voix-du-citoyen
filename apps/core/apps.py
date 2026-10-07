from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Noyau"

    def ready(self):
        from . import checks, schema  # noqa: F401  (enregistre les checks et l'extension OpenAPI)
