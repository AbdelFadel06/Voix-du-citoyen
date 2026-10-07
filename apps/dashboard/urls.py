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
