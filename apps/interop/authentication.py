from rest_framework.authentication import BaseAuthentication

from urllib.parse import unquote

ENTETE = "HTTP_X_API_KEY"
ENTETE_AGENT = "HTTP_X_AGENT"


def nom_agent(request):
    """
    Nom de l'agent IBDC (`X-Agent`), pour l'historique. Accepte un texte encodé en URL
    (`Rodrigue%20Ahouansou`) ou de l'UTF-8 brut (que Django lit comme du latin-1).
    """
    valeur = request.META.get(ENTETE_AGENT, "")
    try:
        valeur = valeur.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return " ".join(unquote(valeur).split())[:150]


class AuthentificationCleApi(BaseAuthentication):
    """
    Application tierce (IBDC) : en-tête `X-Api-Key: <clé de l'institution>`. La requête agit
    au nom du compte technique de l'institution (admin mairie de sa commune) ;
    `request.auth` est l'institution.
    """

    def authenticate(self, request):
        cle = request.META.get(ENTETE)
        if not cle:
            return None  # pas de clé : on laisse les autres authentifications (JWT) décider
        # Imports locaux : DRF charge cette classe pendant son propre import de rest_framework.views,
        # que apps.core.exceptions importe.
        from apps.core.codes_erreur import CodeErreur
        from apps.core.exceptions import ErreurMetier

        from .services import institution_pour_cle

        institution = institution_pour_cle(cle.strip())
        if institution is None:
            raise ErreurMetier(CodeErreur.CLE_API_INVALIDE)
        compte = institution.compte
        compte.agent_externe = nom_agent(request)  # repris par l'historique des dossiers
        return compte, institution

    def authenticate_header(self, request):
        return "X-Api-Key"
