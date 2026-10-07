from django.urls import path

from . import views

app_name = "territoire"

urlpatterns = [
    path("quartiers/", views.QuartierListView.as_view(), name="quartiers"),
    path("quartiers/proche/", views.QuartierProcheView.as_view(), name="quartier-proche"),
]
