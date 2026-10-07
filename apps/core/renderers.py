from rest_framework.renderers import JSONRenderer

from .codes_erreur import code_pour_statut, message_par_defaut
from .reponses import corps_erreur, corps_succes, est_enveloppe

PREFIXE_API = "/api/v1/"


class ReponseJSONRenderer(JSONRenderer):
    """
    Enveloppe automatiquement les réponses de /api/v1/ au format commun.

    Non modifiées : les réponses déjà enveloppées (reponse_succes, pagination,
    gestionnaire d'exceptions), les 204 et tout ce qui est hors /api/v1/
    (schéma OpenAPI, documentation).
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        contexte = renderer_context or {}
        reponse = contexte.get("response")
        requete = contexte.get("request")
        if (
            reponse is not None
            and requete is not None
            and requete.path.startswith(PREFIXE_API)
            and reponse.status_code != 204
            and not est_enveloppe(data)
        ):
            if reponse.status_code >= 400:
                # Erreur renvoyée à la main par une vue (à éviter : lever ErreurMetier).
                code = code_pour_statut(reponse.status_code)
                data = corps_erreur(code, message_par_defaut(code), details=data)
            else:
                data = corps_succes(data)
        return super().render(data, accepted_media_type, renderer_context)
