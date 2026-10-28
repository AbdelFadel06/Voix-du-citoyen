from rest_framework.throttling import SimpleRateThrottle


class ThrottleCleApi(SimpleRateThrottle):
    """
    Limite le nombre d'appels par clé d'API (institution), pour protéger l'API si une intégration
    s'emballe (boucle, actualisation trop fréquente). Sans effet pour les autres requêtes.
    Taux réglable par la variable CLE_API_DEBIT (défaut : 600 requêtes par minute).
    """

    scope = "cle_api"

    def get_cache_key(self, request, view):
        from .models import Institution

        if not isinstance(getattr(request, "auth", None), Institution):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.auth.pk}
