from rest_framework.routers import SimpleRouter

from .views import SuggestionViewSet

app_name = "suggestions"

routeur = SimpleRouter()
routeur.register("suggestions", SuggestionViewSet, basename="suggestion")

urlpatterns = routeur.urls
