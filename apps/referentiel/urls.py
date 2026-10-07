from django.urls import path

from .views import SecteurViewSet

app_name = "referentiel"

urlpatterns = [
    path("secteurs/", SecteurViewSet.as_view({"get": "list", "post": "create"}), name="secteurs"),
    path("secteurs/import/", SecteurViewSet.as_view({"post": "importer"}), name="secteurs-import"),
    path(
        "secteurs/<int:pk>/",
        SecteurViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="secteur-detail",
    ),
]
