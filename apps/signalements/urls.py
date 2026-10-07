from rest_framework.routers import SimpleRouter

from .views import SignalementViewSet

app_name = "signalements"

routeur = SimpleRouter()
routeur.register("signalements", SignalementViewSet, basename="signalement")

urlpatterns = routeur.urls
