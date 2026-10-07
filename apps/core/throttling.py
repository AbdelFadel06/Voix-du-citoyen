from phonenumber_field.phonenumber import to_python
from rest_framework.throttling import SimpleRateThrottle


class ThrottleOTP(SimpleRateThrottle):
    """
    Limite les demandes de code OTP par numéro de téléphone (et non par IP :
    beaucoup d'abonnés mobiles partagent la même adresse IP chez l'opérateur).
    """

    scope = "otp"

    def get_cache_key(self, request, view):
        valeur = request.data.get("telephone") if hasattr(request.data, "get") else None
        numero = to_python(str(valeur)) if valeur else None
        if numero is not None and numero.is_valid():
            identifiant = numero.as_e164
        else:
            identifiant = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": identifiant}
