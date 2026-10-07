from django.db import connection
from django.db.utils import DatabaseError
from django.http import JsonResponse
from django.views import defaults
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from .codes_erreur import CodeErreur, message_par_defaut, statut_http
from .exceptions import ErreurMetier
from .reponses import corps_erreur, reponse_succes
from .schema import TAG_SYSTEME, enveloppe, erreurs, exemple_erreur, exemple_succes


class SanteSerializer(serializers.Serializer):
    statut = serializers.CharField(help_text="`ok` quand l'API fonctionne.")
    base_de_donnees = serializers.CharField(help_text="`ok` quand la base de données répond.")


class SanteView(APIView):
    """Vérifie que l'API répond et que la base de données est joignable."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=[TAG_SYSTEME],
        summary="Vérifier l'état de l'API",
        description="""
Indique si l'API répond et si la base de données est joignable. Utilisé par la supervision
et par les applications pour distinguer « serveur indisponible » de « pas de connexion ».

**Public** : aucun jeton requis.
""",
        auth=[],
        responses={200: enveloppe(SanteSerializer), **erreurs(503)},
        examples=[
            exemple_succes("API opérationnelle", {"statut": "ok", "base_de_donnees": "ok"}),
            exemple_erreur(
                CodeErreur.SERVICE_INDISPONIBLE,
                details={"base_de_donnees": "indisponible"},
                description="La base de données ne répond pas.",
            ),
        ],
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            raise ErreurMetier(
                CodeErreur.SERVICE_INDISPONIBLE, details={"base_de_donnees": "indisponible"}
            )
        return reponse_succes({"statut": "ok", "base_de_donnees": "ok"})


# ---------------------------------------------------------------------------
# Erreurs hors DRF (URL inconnue, plantage hors vue) : JSON pour /api/, HTML sinon.
# Utilisés par Django uniquement quand DEBUG = False.
# ---------------------------------------------------------------------------


def _erreur_json(code):
    return JsonResponse(
        corps_erreur(code, message_par_defaut(code)),
        status=statut_http(code),
        json_dumps_params={"ensure_ascii": False},
    )


def erreur_404(request, exception):
    if request.path.startswith("/api/"):
        return _erreur_json(CodeErreur.RESSOURCE_INTROUVABLE)
    return defaults.page_not_found(request, exception)


def erreur_500(request):
    if request.path.startswith("/api/"):
        return _erreur_json(CodeErreur.ERREUR_SERVEUR)
    return defaults.server_error(request)
