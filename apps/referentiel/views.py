from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView

from apps.core.schema import EXEMPLES_AUTH_REQUISE, TAG_SECTEURS, enveloppe, erreurs, exemple_succes

from .filters import SecteurFilter
from .models import Secteur
from .serializers import SecteurSerializer

VOIRIE = {
    "id": 1,
    "nom": "Voirie",
    "code": "VOIRIE",
    "description": "Routes, nids-de-poule, caniveaux bouchés.",
    "icone": "route",
    "couleur": "#F57C00",
    "pour_signalement": True,
    "pour_suggestion": True,
    "pour_realisation": True,
    "ordre": 1,
}
ECLAIRAGE = {
    "id": 2,
    "nom": "Éclairage public",
    "code": "ECLAIRAGE",
    "description": "Lampadaires en panne ou absents.",
    "icone": "lampadaire",
    "couleur": "#FBC02D",
    "pour_signalement": True,
    "pour_suggestion": False,
    "pour_realisation": True,
    "ordre": 2,
}


@extend_schema(
    tags=[TAG_SECTEURS],
    summary="Lister les secteurs",
    description="""
Renvoie **tous les secteurs actifs**, triés par `ordre` puis par nom.

La liste est complète (**pas de pagination**) pour être gardée en cache par les applications.
Filtrer selon l'écran :
- `?pour_signalement=true` : secteurs proposés lors d'un signalement ;
- `?pour_suggestion=true` : secteurs proposés lors d'une suggestion ;
- `?pour_realisation=true` : secteurs des réalisations.

`icone` et `couleur` servent à l'affichage (liste, carte).

**Connecté** : tous les rôles.
""",
    responses={200: enveloppe(SecteurSerializer, many=True), **erreurs(401, 403)},
    examples=[exemple_succes("Secteurs", [VOIRIE, ECLAIRAGE]), *EXEMPLES_AUTH_REQUISE],
)
class SecteurListView(ListAPIView):
    serializer_class = SecteurSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_class = SecteurFilter

    def get_queryset(self):
        return Secteur.objects.filter(actif=True)
