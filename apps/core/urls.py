from django.urls import path

from .views import SanteView

app_name = "core"

urlpatterns = [
    path("sante/", SanteView.as_view(), name="sante"),
]
