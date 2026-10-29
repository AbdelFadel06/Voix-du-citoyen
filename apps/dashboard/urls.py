from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("dashboard/synthese/", views.SyntheseView.as_view(), name="synthese"),
    path("dashboard/par-secteur/", views.ParSecteurView.as_view(), name="par-secteur"),
    path("dashboard/par-quartier/", views.ParQuartierView.as_view(), name="par-quartier"),
    path("dashboard/evolution/", views.EvolutionView.as_view(), name="evolution"),
    path("dashboard/carte/", views.CarteView.as_view(), name="carte"),
]

# Espace mairie (/api/v1/mairie/…), monté par config/urls.py
urlpatterns_mairie = [
    path("dashboard/synthese/", views.SyntheseCompleteView.as_view(), name="synthese"),
    path("dashboard/evolution/", views.EvolutionMairieView.as_view(), name="evolution"),
    path("dashboard/carte/", views.CarteMairieView.as_view(), name="carte"),
]
