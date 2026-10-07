from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.codes_erreur import CodeErreur
from apps.core.import_csv import importer_depuis_requete
from apps.core.permissions import EstAdminMairie, est_personnel_mairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_SECTEURS,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    parametre_id,
    schema_import,
)
from apps.core.serializers import ImportCSVSerializer, message_bilan

from . import services
from .filters import SecteurFilter
from .models import Secteur
from .serializers import SecteurEcritureSerializer, SecteurSerializer

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
VOIRIE_MAIRIE = {**VOIRIE, "service_par_defaut": {"id": 3, "nom": "Voirie et assainissement"}, "actif": True}
REQUETE = {
    "nom": "Voirie",
    "code": "VOIRIE",
    "description": "Routes, nids-de-poule, caniveaux bouchés.",
    "icone": "route",
    "couleur": "#F57C00",
    "pour_signalement": True,
    "pour_suggestion": True,
    "pour_realisation": True,
    "service_par_defaut": 3,
    "ordre": 1,
}
EXEMPLE_RESERVE_ADMIN = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux administrateurs de la mairie.", nom="Réservé aux admins mairie"
)
EXEMPLE_INTROUVABLE = exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Secteur inconnu")
ID_SECTEUR = parametre_id("Identifiant du secteur.")
EXEMPLE_INVALIDE = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={
        "code": ["Un secteur utilise déjà ce code."],
        "couleur": ["La couleur doit être au format hexadécimal, par exemple #1E88E5."],
    },
    nom="Données invalides",
)
VISIBILITE = """
**Ce que voit chaque rôle** : citoyens et organisations ne voient que les secteurs **actifs**.
Les agents et admins voient aussi les secteurs désactivés, avec les champs `actif` et
`service_par_defaut` (filtre `?actif=false`).
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_SECTEURS],
        summary="Lister les secteurs",
        description=f"""
Renvoie les secteurs, triés par `ordre` puis par nom.

La liste est complète (**pas de pagination**) pour être gardée en cache par les applications.
Filtrer selon l'écran :
- `?pour_signalement=true` : secteurs proposés lors d'un signalement ;
- `?pour_suggestion=true` : secteurs proposés lors d'une suggestion ;
- `?pour_realisation=true` : secteurs des réalisations.

`icone` et `couleur` servent à l'affichage (liste, carte).
{VISIBILITE}
**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(SecteurSerializer, many=True), **erreurs(401, 403)},
        examples=[
            exemple_succes("Vus par un citoyen", [VOIRIE, ECLAIRAGE]),
            exemple_succes("Vus par la mairie", [VOIRIE_MAIRIE]),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG_SECTEURS],
        summary="Consulter un secteur",
        description=f"""
Détail d'un secteur (par exemple pour préremplir un formulaire de modification).
{VISIBILITE}
**Connecté** : tous les rôles.
""",
        parameters=[ID_SECTEUR],
        responses={200: enveloppe(SecteurSerializer), **erreurs(401, 403, 404)},
        examples=[exemple_succes("Secteur", VOIRIE_MAIRIE), EXEMPLE_INTROUVABLE, *EXEMPLES_AUTH_REQUISE],
    ),
    create=extend_schema(
        tags=[TAG_SECTEURS],
        summary="Créer un secteur",
        description="""
Crée un secteur. `nom` et `code` sont obligatoires et uniques ; le code est mis en majuscules.

Penser à cocher au moins un usage (`pour_signalement`, `pour_suggestion`,
`pour_realisation`), sinon le secteur n'est proposé nulle part. `service_par_defaut` reçoit
automatiquement les nouveaux signalements du secteur.

Pour en créer plusieurs d'un coup : `POST /secteurs/import/`.

**Connecté** : admins mairie uniquement.
""",
        request=SecteurEcritureSerializer,
        responses={201: enveloppe(SecteurSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Nouveau secteur", REQUETE),
            exemple_succes("Secteur créé", VOIRIE_MAIRIE, "Secteur « Voirie » créé.", statut=201),
            EXEMPLE_INVALIDE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_SECTEURS],
        summary="Modifier un secteur",
        description="""
Modifie uniquement les champs envoyés. `{"actif": false}` retire le secteur des listes des
citoyens sans le supprimer : les signalements, suggestions et réalisations qui l'utilisent
restent intacts.

**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_SECTEUR],
        request=SecteurEcritureSerializer,
        responses={200: enveloppe(SecteurSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Changer la couleur", {"couleur": "#E65100"}),
            exemple_requete("Désactiver", {"actif": False}),
            exemple_succes("Secteur modifié", VOIRIE_MAIRIE, "Secteur « Voirie » modifié."),
            EXEMPLE_INVALIDE,
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class SecteurViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_class = SecteurFilter

    def get_permissions(self):
        if self.action in ("create", "partial_update", "importer"):
            return [IsAuthenticated(), EstAdminMairie()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ("create", "partial_update"):
            return SecteurEcritureSerializer
        return SecteurSerializer

    def get_queryset(self):
        queryset = Secteur.objects.select_related("service_par_defaut")
        if not est_personnel_mairie(self.request.user):
            queryset = queryset.filter(actif=True)
        return queryset

    def _lecture(self, secteur):
        return SecteurSerializer(secteur, context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        entree = SecteurEcritureSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        secteur = entree.save()
        return reponse_succes(self._lecture(secteur), f"Secteur « {secteur.nom} » créé.", status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        entree = SecteurEcritureSerializer(self.get_object(), data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        secteur = entree.save()
        return reponse_succes(self._lecture(secteur), f"Secteur « {secteur.nom} » modifié.")

    @extend_schema(
        **schema_import(
            TAG_SECTEURS,
            "secteurs",
            "code;nom;description;icone;couleur;pour_signalement;pour_suggestion;pour_realisation;service_par_defaut;ordre\n"
            "VOIRIE;Voirie;Routes, nids-de-poule;route;#F57C00;oui;oui;oui;Voirie et assainissement;1\n"
            "ECLAIRAGE;Éclairage public;;lampadaire;#FBC02D;oui;non;oui;;2",
            {"crees": 6, "mis_a_jour": 2, "desactives": 0},
            [
                "Ligne 4 : couleur « bleu » invalide (attendu #RRGGBB).",
                "Ligne 7 : service « Hygiène » introuvable (créez-le d'abord).",
            ],
            parametres="""
- Seules les colonnes `code` et `nom` sont obligatoires ; une colonne absente laisse la
  valeur actuelle. Les secteurs sont reconnus par leur `code`.
- Oui / non : `oui`, `non`, `1`, `0`, `x` ; une cellule vide vaut « non ».
- `service_par_defaut` : nom exact d'un service municipal existant.
""",
        )
    )
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def importer(self, request):
        entree = ImportCSVSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        options = entree.validated_data
        bilan = importer_depuis_requete(
            options["fichier"],
            lambda texte: services.importer_secteurs(
                texte, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            ),
        )
        return reponse_succes(bilan, message_bilan(bilan, "secteur(s)"))
