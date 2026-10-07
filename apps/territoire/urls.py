from django.urls import path

from . import views

app_name = "territoire"

LECTURE_CREATION = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "patch": "partial_update"}

urlpatterns = [
    path("quartiers/", views.QuartierViewSet.as_view(LECTURE_CREATION), name="quartiers"),
    path("quartiers/proche/", views.QuartierProcheView.as_view(), name="quartier-proche"),
    path("quartiers/import/", views.QuartierViewSet.as_view({"post": "importer"}), name="quartiers-import"),
    path("quartiers/<int:pk>/", views.QuartierViewSet.as_view(DETAIL), name="quartier-detail"),
    path("arrondissements/", views.ArrondissementViewSet.as_view(LECTURE_CREATION), name="arrondissements"),
    path("arrondissements/<int:pk>/", views.ArrondissementViewSet.as_view(DETAIL), name="arrondissement-detail"),
    path("communes/", views.CommuneViewSet.as_view(LECTURE_CREATION), name="communes"),
    path("communes/<int:pk>/", views.CommuneViewSet.as_view(DETAIL), name="commune-detail"),
]
