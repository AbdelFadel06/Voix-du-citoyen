from rest_framework_simplejwt.authentication import JWTAuthentication


class AuthentificationJWT(JWTAuthentication):
    """
    Authentification JWT qui coupe l'accès, à chaque requête, aux organisations
    dont l'habilitation n'est plus active ou a expiré (même avec un jeton valide).
    """

    def get_user(self, validated_token):
        # Import local : DRF charge cette classe pendant son propre import de
        # rest_framework.views, que les services importent indirectement.
        from apps.accounts.services import verifier_acces_organisation

        utilisateur = super().get_user(validated_token)
        verifier_acces_organisation(utilisateur)
        return utilisateur
