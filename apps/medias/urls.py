from django.urls import path

from . import views

app_name = "medias"

urlpatterns = [
    path("medias/", views.TeleversementView.as_view(), name="televersement"),
]
