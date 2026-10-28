from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AuthentificationCleApiScheme(OpenApiAuthenticationExtension):
    """Documente l'authentification par clé d'application (IBDC) dans OpenAPI."""

    target_class = "apps.interop.authentication.AuthentificationCleApi"
    name = "cleApi"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-Api-Key",
            "description": "Clé d'une **institution** (mairie connectée depuis la plateforme IBDC), "
            "fournie par l'équipe Voix du Citoyen. Les appels agissent au nom de cette mairie, avec "
            "les droits d'un admin mairie de sa commune. Ne jamais l'utiliser depuis un navigateur.",
        }
