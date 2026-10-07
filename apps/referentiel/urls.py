from django.urls import path

from . import views

app_name = "referentiel"

urlpatterns = [
    path("secteurs/", views.SecteurListView.as_view(), name="secteurs"),
]
