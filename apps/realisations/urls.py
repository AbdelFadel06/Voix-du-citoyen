from rest_framework.routers import SimpleRouter

from .views import RealisationViewSet

app_name = "realisations"

routeur = SimpleRouter()
routeur.register("realisations", RealisationViewSet, basename="realisation")

urlpatterns = routeur.urls
