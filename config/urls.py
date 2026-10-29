from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.accounts import urls as accounts
from apps.core.espaces import EspaceMairie, HorsEspaceMairie, garder
from apps.dashboard import urls as dashboard
from apps.realisations import urls as realisations
from apps.referentiel import urls as referentiel
from apps.signalements import urls as signalements
from apps.suggestions import urls as suggestions
from apps.territoire import urls as territoire

# Volets que la mairie d'une commune utilise par l'espace /mairie/ (apps.core.espaces).
# Restent communs à tous : authentification, médias, notifications, santé.
VOLETS_MAIRIE = [territoire, accounts, referentiel, signalements, suggestions, realisations]
# Actions réservées aux citoyens ou aux organisations : absentes de l'espace mairie.
ACTIONS_HORS_MAIRIE = {
    "signalements": {"create", "mes_signalements", "prendre_en_charge"},
    "suggestions": {"create", "soutenir"},
}


def _hors_auth(motif):
    return not str(motif.pattern).startswith("auth/")


def _routes_generales(module):
    return include((garder(module.urlpatterns, HorsEspaceMairie, selection=_hors_auth), module.app_name))


def _routes_mairie(module):
    motifs = garder(
        module.urlpatterns, EspaceMairie, espace_mairie=True, selection=_hors_auth,
        actions_exclues=ACTIONS_HORS_MAIRIE.get(module.app_name, ()),
    )
    return include((motifs, module.app_name), namespace=module.app_name)


espace_mairie = [
    *[path("", _routes_mairie(module)) for module in VOLETS_MAIRIE],
    path("", include((dashboard.urlpatterns_mairie, "dashboard"), namespace="dashboard")),
]

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.medias.urls")),
    path("", include("apps.notifications.urls")),
    *[path("", _routes_generales(module)) for module in VOLETS_MAIRIE],
    path("", include((garder(dashboard.urlpatterns, HorsEspaceMairie), "dashboard"))),
    path("mairie/", include((espace_mairie, "mairie"))),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.core.views.erreur_404"
handler500 = "apps.core.views.erreur_500"
