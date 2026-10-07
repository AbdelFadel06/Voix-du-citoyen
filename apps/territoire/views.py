from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.filters import Recherche
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_TERRITOIRE,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_succes,
)

from . import services
from .filters import QuartierFilter
from .models import Quartier
from .serializers import PositionSerializer, QuartierProcheSerializer, QuartierSerializer

TOGOUDO = {
    "id": 12,
    "nom": "Togoudo",
    "code": "TOG",
    "arrondissement": {"id": 3, "nom": "Godomey"},
    "latitude_centre": "6.401234",
    "longitude_centre": "2.341234",
}
ZOGBADJE = {
    "id": 15,
    "nom": "Zogbadjè",
    "code": "ZOG",
    "arrondissement": {"id": 1, "nom": "Abomey-Calavi"},
    "latitude_centre": "6.452100",
    "longitude_centre": "2.350800",
}


@extend_schema(
    tags=[TAG_TERRITOIRE],
    summary="Lister les quartiers",
    description="""
Renvoie **tous les quartiers actifs** de la commune, triés par nom, avec leur arrondissement.

La liste est complète (**pas de pagination**) : l'application mobile peut la télécharger une
fois et la garder en cache pour le choix du quartier (inscription, signalement en mode manuel).

- `?arrondissement=<id>` : quartiers d'un seul arrondissement.
- `?recherche=<texte>` : quartiers dont le nom contient le texte.

Les coordonnées du centre peuvent être `null` si elles ne sont pas encore connues.

**Connecté** : tous les rôles.
""",
    responses={200: enveloppe(QuartierSerializer, many=True), **erreurs(401, 403)},
    examples=[exemple_succes("Quartiers", [TOGOUDO, ZOGBADJE]), *EXEMPLES_AUTH_REQUISE],
)
class QuartierListView(ListAPIView):
    serializer_class = QuartierSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, Recherche]
    filterset_class = QuartierFilter
    search_fields = ["nom"]

    def get_queryset(self):
        return Quartier.objects.filter(actif=True).select_related("arrondissement")


class QuartierProcheView(APIView):
    @extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Proposer le quartier le plus proche d'une position GPS",
        description="""
Utilisé lors d'un signalement en **mode GPS** : à partir de la position choisie sur la carte,
l'API propose le quartier actif dont le **centre** est le plus proche.
**Le citoyen doit confirmer ou corriger** cette proposition : c'est une aide, pas une certitude
(les limites réelles des quartiers ne sont pas connues).

**Règles**
- Une position en dehors de la commune est refusée (`COORDONNEES_HORS_COMMUNE`).
- Seuls les quartiers actifs dont le centre est renseigné sont pris en compte. S'il n'y en a
  aucun : `RESSOURCE_INTROUVABLE` ; proposer alors la liste `GET /quartiers/`.

**Connecté** : tous les rôles.
""",
        parameters=[PositionSerializer],
        responses={200: enveloppe(QuartierProcheSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_succes("Quartier proposé", {"quartier": TOGOUDO, "distance_metres": 140}),
            exemple_erreur(
                CodeErreur.COORDONNEES_HORS_COMMUNE,
                description="La position est en dehors de l'emprise de la commune.",
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"lat": ["Ce champ est obligatoire."], "lng": ["Un nombre valide est requis."]},
                nom="Position manquante ou invalide",
            ),
            exemple_erreur(
                CodeErreur.RESSOURCE_INTROUVABLE,
                "Aucun quartier localisé n'est disponible. Choisissez votre quartier dans la liste.",
                nom="Aucun quartier localisé",
            ),
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def get(self, request):
        position = PositionSerializer(data=request.query_params)
        position.is_valid(raise_exception=True)
        quartier, distance = services.quartier_le_plus_proche(
            position.validated_data["lat"], position.validated_data["lng"]
        )
        return reponse_succes(
            {"quartier": QuartierSerializer(quartier).data, "distance_metres": round(distance)}
        )
