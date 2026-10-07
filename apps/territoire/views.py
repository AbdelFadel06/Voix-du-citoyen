import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import FiltreCommune, cloisonner, commune_d_action, commune_imposee
from apps.core.exceptions import ErreurMetier
from apps.core.filters import Recherche
from apps.core.import_csv import importer_depuis_requete
from apps.core.permissions import est_personnel_mairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_TERRITOIRE,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    parametre_id,
    schema_import,
)
from apps.core.serializers import message_bilan
from apps.core.vues import VueAdministration

from . import services
from .filters import QuartierFilter
from .models import Arrondissement, Commune, Quartier
from .serializers import (
    ArrondissementSerializer,
    BilanImportQuartiersSerializer,
    CommuneSerializer,
    ImportQuartiersSerializer,
    PositionSerializer,
    QuartierEcritureSerializer,
    QuartierProcheSerializer,
    QuartierSerializer,
)

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


COMMUNE = {
    "id": 1,
    "nom": "Parakou",
    "code": "PKO",
    "departement": "Borgou",
    "lat_min": "9.232900",
    "lat_max": "9.441900",
    "lng_min": "2.480800",
    "lng_max": "2.771800",
}
ARRONDISSEMENT = {"id": 3, "commune": 1, "nom": "1er arrondissement", "code": "PKO-1"}
EXEMPLE_RESERVE_ADMIN = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux administrateurs de la mairie.", nom="Réservé aux admins mairie"
)
VISIBILITE_QUARTIERS = """
**Ce que voit chaque rôle** : citoyens et organisations ne voient que les quartiers **actifs**.
Les agents et admins voient aussi les quartiers désactivés, avec le champ `actif`
(filtre `?actif=false`).
"""


# ---------------------------------------------------------------------------
# Quartiers
# ---------------------------------------------------------------------------

ID_QUARTIER = parametre_id("Identifiant du quartier.")
REQUETE_QUARTIER = {
    "arrondissement": 3,
    "nom": "Banikanni",
    "code": "BAN",
    "latitude_centre": "9.324070",
    "longitude_centre": "2.647370",
}
QUARTIER_MAIRIE = {
    "id": 21,
    "nom": "Banikanni",
    "code": "BAN",
    "arrondissement": {"id": 3, "nom": "1er arrondissement"},
    "latitude_centre": "9.324070",
    "longitude_centre": "2.647370",
    "actif": True,
}
EXEMPLE_QUARTIER_INVALIDE = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={
        "nom": ["Ce quartier existe déjà dans cet arrondissement."],
        "latitude_centre": ["Ce point est hors de l'emprise de Parakou."],
    },
    nom="Données invalides",
)


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Lister les quartiers",
        description=f"""
Renvoie les quartiers de la commune, triés par nom, avec leur arrondissement.

La liste est complète (**pas de pagination**) : l'application mobile peut la télécharger une
fois et la garder en cache pour le choix du quartier (inscription, signalement en mode manuel).

- `?arrondissement=<id>` : quartiers d'un seul arrondissement.
- `?recherche=<texte>` : quartiers dont le nom contient le texte.

Les coordonnées du centre peuvent être `null` si elles ne sont pas encore connues.
{VISIBILITE_QUARTIERS}
**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(QuartierSerializer, many=True), **erreurs(401, 403)},
        examples=[
            exemple_succes("Vus par un citoyen", [TOGOUDO, ZOGBADJE]),
            exemple_succes("Vus par la mairie", [QUARTIER_MAIRIE]),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Consulter un quartier",
        description=f"""
Détail d'un quartier (par exemple pour préremplir un formulaire de modification).
{VISIBILITE_QUARTIERS}
**Connecté** : tous les rôles.
""",
        parameters=[ID_QUARTIER],
        responses={200: enveloppe(QuartierSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Quartier", QUARTIER_MAIRIE),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Quartier inconnu"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Créer un quartier",
        description="""
Crée un quartier dans un arrondissement existant (`GET /arrondissements/`).

- `nom` unique dans l'arrondissement.
- Centre facultatif, mais nécessaire pour `GET /quartiers/proche/` : `latitude_centre` et
  `longitude_centre` vont ensemble et doivent être dans l'emprise de la commune.

Pour en créer plusieurs d'un coup (avec leurs arrondissements) : `POST /quartiers/import/`.

**Connecté** : admins mairie uniquement.
""",
        request=QuartierEcritureSerializer,
        responses={201: enveloppe(QuartierSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Nouveau quartier", REQUETE_QUARTIER),
            exemple_succes("Quartier créé", QUARTIER_MAIRIE, "Quartier « Banikanni » créé.", statut=201),
            EXEMPLE_QUARTIER_INVALIDE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Modifier un quartier",
        description="""
Modifie uniquement les champs envoyés (nom, code, centre, arrondissement).
`{"actif": false}` retire le quartier des listes sans le supprimer : les dossiers qui
l'utilisent restent intacts.

**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_QUARTIER],
        request=QuartierEcritureSerializer,
        responses={200: enveloppe(QuartierSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Renseigner le centre", {"latitude_centre": "9.324070", "longitude_centre": "2.647370"}),
            exemple_requete("Désactiver", {"actif": False}),
            exemple_succes("Quartier modifié", QUARTIER_MAIRIE, "Quartier « Banikanni » modifié."),
            EXEMPLE_QUARTIER_INVALIDE,
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Quartier inconnu"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class QuartierViewSet(VueAdministration):
    filter_backends = [DjangoFilterBackend, Recherche]
    filterset_class = QuartierFilter
    search_fields = ["nom"]
    serializer_lecture = QuartierSerializer
    libelle = "Quartier"

    def get_serializer_class(self):
        return QuartierEcritureSerializer if self.action in ("create", "partial_update") else QuartierSerializer

    def get_queryset(self):
        queryset = cloisonner(
            Quartier.objects.select_related("arrondissement"), self.request.user, "arrondissement__commune"
        )
        if not est_personnel_mairie(self.request.user):
            queryset = queryset.filter(actif=True)
        return queryset

    @extend_schema(
        **schema_import(
            TAG_TERRITOIRE,
            "quartiers",
            "arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude\n"
            "PKO-1;1er arrondissement;BAN;Banikanni;9.32407;2.64737\n"
            "PKO-1;1er arrondissement;KPE;Kpébié;;",
            {"arrondissements_crees": 3, "crees": 41, "mis_a_jour": 0, "desactives": 0},
            [
                "Ligne 5 : « quartier_nom » est vide.",
                "Ligne 9 : le centre de « Tourou » (2.543970, 9.345310) est hors de l'emprise de Parakou.",
            ],
            serializer_bilan=BilanImportQuartiersSerializer,
            parametres="""
- Les arrondissements absents sont créés au passage ; les quartiers sont reconnus par leur
  nom dans leur arrondissement.
- `latitude` / `longitude` (centre) sont facultatives ; si elles sont données, elles doivent
  être dans l'emprise de la commune (virgule décimale acceptée).
- `commune` : facultatif s'il n'existe qu'une commune.
""",
        )
        | {"request": {"multipart/form-data": ImportQuartiersSerializer}}
    )
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def importer(self, request):
        entree = ImportQuartiersSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        options = entree.validated_data
        commune = commune_d_action(request.user, options.get("commune"))
        bilan = importer_depuis_requete(
            options["fichier"],
            lambda texte: services.importer_quartiers(
                texte, commune, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            ),
        )
        return reponse_succes(bilan, message_bilan(bilan, "quartier(s)"))


# ---------------------------------------------------------------------------
# Arrondissements
# ---------------------------------------------------------------------------

ID_ARRONDISSEMENT = parametre_id("Identifiant de l'arrondissement.")
EXEMPLE_ARRONDISSEMENT_EXISTANT = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={"nom": ["Cet arrondissement existe déjà dans cette commune."]},
    nom="Arrondissement existant",
)


class ArrondissementFilter(django_filters.FilterSet):
    commune = FiltreCommune()

    class Meta:
        model = Arrondissement
        fields = ["commune"]


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Lister les arrondissements",
        description="""
Tous les arrondissements de la commune, triés par nom (liste complète, sans pagination).
Utile pour filtrer les quartiers (`GET /quartiers/?arrondissement=<id>`).

**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(ArrondissementSerializer, many=True), **erreurs(401, 403)},
        examples=[exemple_succes("Arrondissements", [ARRONDISSEMENT]), *EXEMPLES_AUTH_REQUISE],
    ),
    retrieve=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Consulter un arrondissement",
        description="""
Détail d'un arrondissement : nom, code et commune (par exemple pour préremplir un formulaire
de modification). Ses quartiers : `GET /quartiers/?arrondissement=<id>`.

**Connecté** : tous les rôles.
""",
        parameters=[ID_ARRONDISSEMENT],
        responses={200: enveloppe(ArrondissementSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Arrondissement", ARRONDISSEMENT),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Arrondissement inconnu"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Créer un arrondissement",
        description="""
Crée un arrondissement. `nom` unique dans la commune ; `commune` est facultatif s'il
n'existe qu'une commune. L'import des quartiers (`POST /quartiers/import/`) crée aussi
les arrondissements manquants.

**Connecté** : admins mairie uniquement.
""",
        request=ArrondissementSerializer,
        responses={201: enveloppe(ArrondissementSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Nouvel arrondissement", {"nom": "1er arrondissement", "code": "PKO-1"}),
            exemple_succes("Arrondissement créé", ARRONDISSEMENT, "Arrondissement « 1er arrondissement » créé.", statut=201),
            EXEMPLE_ARRONDISSEMENT_EXISTANT,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Modifier un arrondissement",
        description="""
Modifie uniquement les champs envoyés (`nom`, `code`). Le nouveau nom doit rester unique dans
la commune. Les quartiers de l'arrondissement ne changent pas.

**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_ARRONDISSEMENT],
        request=ArrondissementSerializer,
        responses={200: enveloppe(ArrondissementSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Changer le code", {"code": "PKO-1"}),
            exemple_succes("Arrondissement modifié", ARRONDISSEMENT, "Arrondissement « 1er arrondissement » modifié."),
            EXEMPLE_ARRONDISSEMENT_EXISTANT,
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Arrondissement inconnu"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class ArrondissementViewSet(VueAdministration):
    serializer_class = ArrondissementSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ArrondissementFilter

    def get_queryset(self):
        return cloisonner(Arrondissement.objects.order_by("nom"), self.request.user)

    serializer_lecture = ArrondissementSerializer
    libelle = "Arrondissement"


# ---------------------------------------------------------------------------
# Commune
# ---------------------------------------------------------------------------

ID_COMMUNE = parametre_id("Identifiant de la commune.")
DESCRIPTION_EMPRISE = """
**Emprise** (`lat_min`, `lat_max`, `lng_min`, `lng_max`) : rectangle qui entoure la commune.
Toute position GPS hors de ce rectangle est refusée (signalements, chantiers, centres des
quartiers) : cela écarte les erreurs de GPS des téléphones. Les valeurs se trouvent sur
OpenStreetMap (recherche de la commune → « boundingbox »).
"""
EXEMPLE_COMMUNE_INVALIDE = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR, details={"lat_max": ["Doit être supérieur à lat_min."]}, nom="Emprise incohérente"
)


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Lister les communes",
        description=f"""
La plateforme sert une seule commune ; la liste n'en contient donc normalement qu'une.
{DESCRIPTION_EMPRISE}
**Connecté** : agents et admins mairie.
""",
        responses={200: enveloppe(CommuneSerializer, many=True), **erreurs(401, 403)},
        examples=[exemple_succes("Commune", [COMMUNE]), *EXEMPLES_AUTH_REQUISE],
    ),
    retrieve=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Consulter la commune",
        description=f"""
Détail de la commune : nom, code, département et emprise GPS.
{DESCRIPTION_EMPRISE}
**Connecté** : agents et admins mairie.
""",
        parameters=[ID_COMMUNE],
        responses={200: enveloppe(CommuneSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Commune", COMMUNE),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Commune inconnue"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Créer la commune",
        description=f"""
Crée la commune servie par la plateforme (à faire une fois, avant les quartiers).
Tous les champs sont obligatoires ; `code` est unique.
{DESCRIPTION_EMPRISE}
**Connecté** : admins mairie uniquement.
""",
        request=CommuneSerializer,
        responses={201: enveloppe(CommuneSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Parakou", {k: v for k, v in COMMUNE.items() if k != "id"}),
            exemple_succes("Commune créée", COMMUNE, "Commune « Parakou » créée.", statut=201),
            EXEMPLE_COMMUNE_INVALIDE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_TERRITOIRE],
        summary="Modifier la commune",
        description=f"""
Modifie uniquement les champs envoyés, par exemple pour corriger l'emprise.
{DESCRIPTION_EMPRISE}
**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_COMMUNE],
        request=CommuneSerializer,
        responses={200: enveloppe(CommuneSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Élargir l'emprise", {"lat_max": "9.450000"}),
            exemple_succes("Commune modifiée", COMMUNE, "Commune « Parakou » modifiée."),
            EXEMPLE_COMMUNE_INVALIDE,
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Commune inconnue"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class CommuneViewSet(VueAdministration):
    queryset = Commune.objects.order_by("nom")
    serializer_class = CommuneSerializer
    serializer_lecture = CommuneSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]  # écran d'inscription : choix de la commune de résidence
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        if commune_imposee(request.user) is not None:
            raise ErreurMetier(
                CodeErreur.PERMISSION_REFUSEE,
                "Seul un administrateur de la plateforme (sans commune) peut ajouter une commune.",
            )
        entree = CommuneSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        commune = entree.save()
        return reponse_succes(CommuneSerializer(commune).data, f"Commune « {commune.nom} » créée.", status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        commune = self.get_object()
        if commune_imposee(request.user) not in (None, commune.pk):
            raise ErreurMetier(CodeErreur.PERMISSION_REFUSEE, "Vous ne pouvez modifier que votre commune.")
        entree = CommuneSerializer(commune, data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        commune = entree.save()
        return reponse_succes(CommuneSerializer(commune).data, f"Commune « {commune.nom} » modifiée.")


# ---------------------------------------------------------------------------
# Quartier le plus proche
# ---------------------------------------------------------------------------


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
            position.validated_data["lat"], position.validated_data["lng"], commune_id=commune_imposee(request.user)
        )
        return reponse_succes(
            {"quartier": QuartierSerializer(quartier).data, "distance_metres": round(distance)}
        )
