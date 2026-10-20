from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import cloisonner
from apps.accounts.models import Utilisateur
from apps.core.permissions import EstMairieOuOrganisation, est_personnel_mairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_REALISATIONS,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
)

from . import exemples, services
from .filters import RealisationFilter
from .models import Realisation, RealisationMedia
from .serializers import RealisationDetailSerializer, RealisationEcritureSerializer, RealisationListSerializer

EXEMPLE_INTROUVABLE = exemple_erreur(
    CodeErreur.RESSOURCE_INTROUVABLE, nom="Réalisation inconnue ou non publiée"
)
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE,
    "Accès réservé à la mairie et aux organisations habilitées.",
    nom="Réservé à la mairie et aux organisations",
)
EXEMPLE_PAS_PROPRIETAIRE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE,
    "Seul l'auteur de cette réalisation (la mairie ou l'organisation qui l'a publiée) peut la modifier.",
    nom="Réalisation d'un autre auteur",
)
EXEMPLE_JETON_INVALIDE = exemple_erreur(
    CodeErreur.JETON_INVALIDE, description="Un jeton est envoyé mais il a expiré : le renouveler ou ne pas l'envoyer."
)
EXEMPLES_ECRITURE = [
    exemple_erreur(
        CodeErreur.VALIDATION_ERREUR,
        details={
            "quartiers": ["Cette liste ne peut pas être vide."],
            "date_fin_prevue": ["La fin prévue ne peut pas précéder le début prévu."],
        },
        nom="Données invalides",
    ),
    exemple_erreur(CodeErreur.COORDONNEES_HORS_COMMUNE),
    exemple_erreur(
        CodeErreur.MEDIAS_NON_CONFORMES,
        "Les fichiers joints à cette réalisation ne respectent pas les règles.",
        details={"medias": ["10 photo(s) au maximum."]},
    ),
    exemple_erreur(CodeErreur.MEDIA_INTROUVABLE),
    exemple_erreur(CodeErreur.MEDIA_DEJA_UTILISE),
    EXEMPLE_RESERVE_MAIRIE,
    *EXEMPLES_AUTH_REQUISE,
]
DESCRIPTION_PUBLIC = """
**Deux auteurs** : la **mairie** et les **organisations** (ONG, OSC) publient chacune leurs
réalisations. `organisation` indique l'organisation auteur, `null` pour la mairie ; filtres
`?par_la_mairie=true|false` et `?organisation=<id>`.

**Public** : aucun compte nécessaire. Sans jeton (ou pour un citoyen), seules les réalisations
**publiées** sont visibles. Chaque auteur voit en plus **ses propres brouillons**
(`publie: false`) : un agent ou admin ceux de la mairie (de sa commune), une organisation les
siens. `publie` et `cree_par` ne sont renvoyés qu'à qui gère la réalisation ; `peut_modifier`
indique s'il peut la modifier.
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_REALISATIONS],
        summary="Lister les réalisations",
        description=f"""
Liste **paginée** des réalisations de la mairie et des organisations, de la plus récente à la
plus ancienne.
Chaque élément ne contient qu'**une photo de couverture** (miniature) et le nombre de médias ;
le détail complet est donné par `GET /realisations/{{id}}/`.

**Filtres** : `statut`, `secteur`, `quartier`, `date_debut`, `date_fin` (dates de création),
`par_la_mairie`, `organisation` et, pour la mairie et les organisations, `publie=false` (leurs
brouillons).
**Recherche** (`recherche`) : référence, titre, description, prestataire.
**Tri** (`tri`) : `cree_le`, `maj_le`, `taux_avancement`, `date_fin_prevue`.
{DESCRIPTION_PUBLIC}""",
        auth=[],
        responses={200: RealisationListSerializer(many=True), **erreurs(401, 404)},
        examples=[
            exemple_element_liste("Réalisation publiée", exemples.LISTE),
            exemple_element_liste("Brouillon vu par la mairie", exemples.BROUILLON),
            exemple_element_liste("Réalisation d'une organisation", exemples.LISTE_ORGANISATION),
            EXEMPLE_PAGE_INEXISTANTE,
            EXEMPLE_JETON_INVALIDE,
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG_REALISATIONS],
        summary="Consulter une réalisation",
        description=f"""
Détail complet : description, dates prévues et réelles, budget (FCFA), financement,
prestataire, position, **photos et vidéos par phase** (`AVANT`, `PENDANT`, `APRES`) et
signalements / suggestions à l'origine des travaux.

Le brouillon d'un autre auteur donne `RESSOURCE_INTROUVABLE`.
{DESCRIPTION_PUBLIC}""",
        auth=[],
        responses={200: enveloppe(RealisationDetailSerializer), **erreurs(401, 404)},
        examples=[
            exemple_succes("Vue par le public", exemples.DETAIL),
            exemple_succes("Vue par la mairie", exemples.DETAIL_MAIRIE),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_JETON_INVALIDE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_REALISATIONS],
        summary="Créer une réalisation",
        description="""
Crée la fiche d'une réalisation. Par défaut c'est un **brouillon** (`publie: false`), invisible
du public : la publier plus tard avec `PATCH { "publie": true }`, ou directement avec
`"publie": true`.

- Obligatoires : `titre`, `description`, `secteur` (utilisé pour les réalisations),
  `quartiers` (au moins un).
- `latitude` et `longitude` vont ensemble et doivent être dans la commune.
- Les dates de fin ne peuvent pas précéder les dates de début.
- `medias` : photos et vidéos envoyées au préalable avec `POST /medias/` par l'agent
  connecté, chacune avec sa `phase` (10 photos et 2 vidéos au maximum).
- `signalements` / `suggestions` : dossiers citoyens à l'origine des travaux.

**Organisation** (ONG, OSC) : la réalisation est à son nom (`organisation`) et elle seule pourra
la modifier. Elle doit rester dans son **périmètre** : quartiers d'une de ses communes
d'intervention, `secteur` parmi ses secteurs, signalements de ses secteurs ; pas de
`suggestions` (sinon `VALIDATION_ERREUR`).

**Après la création** : référence `REA-AAAA-NNNNN`.

**Connecté** : agents et admins mairie ; organisations habilitées.
""",
        request=RealisationEcritureSerializer,
        responses={201: enveloppe(RealisationDetailSerializer), **erreurs(400, 401, 403, 409)},
        examples=[
            exemple_requete("Nouveau chantier (brouillon)", exemples.REQUETE_CREATION),
            exemple_succes(
                "Réalisation enregistrée",
                {**exemples.DETAIL_MAIRIE, "publie": False},
                "Réalisation enregistrée. Référence : REA-2026-00004.",
                statut=201,
            ),
            *EXEMPLES_ECRITURE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_REALISATIONS],
        summary="Modifier une réalisation",
        description="""
Modification **partielle** : seuls les champs envoyés changent (mise à jour de l'avancement,
des dates réelles, publication…).

- `medias` **remplace** la liste complète : renvoyer les médias à garder (leur phase, légende
  et ordre peuvent changer) et ajouter les nouveaux ; les médias absents sont **supprimés**.
- `quartiers`, `signalements`, `suggestions` remplacent aussi leur liste.
- `"publie": true` rend la réalisation visible du public (les citoyens seront notifiés à
  l'étape 9).

Mêmes contrôles qu'à la création, appliqués à l'état final.

**Seul l'auteur** modifie une réalisation : la mairie les siennes, chaque organisation les siennes
(`PERMISSION_REFUSEE` sinon, même si elle est visible).

**Connecté** : agents et admins mairie ; organisations habilitées.
""",
        request=RealisationEcritureSerializer,
        responses={200: enveloppe(RealisationDetailSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Point d'avancement avec nouvelle photo", exemples.REQUETE_AVANCEMENT),
            exemple_requete("Publication", exemples.REQUETE_PUBLICATION),
            exemple_succes("Réalisation publiée", exemples.DETAIL_MAIRIE, "Réalisation publiée."),
            exemple_succes("Réalisation mise à jour", exemples.DETAIL_MAIRIE, "Réalisation mise à jour."),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_PAS_PROPRIETAIRE,
            *EXEMPLES_ECRITURE,
        ],
    ),
)
class RealisationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_class = RealisationFilter
    search_fields = ["reference", "titre", "description", "prestataire"]
    ordering_fields = ["cree_le", "maj_le", "taux_avancement", "date_fin_prevue"]
    ordering = ["-cree_le"]

    def get_permissions(self):
        if self.action in ("create", "partial_update"):
            return [IsAuthenticated(), EstMairieOuOrganisation()]
        return [AllowAny()]

    def get_serializer_class(self):
        return RealisationListSerializer if self.action == "list" else RealisationDetailSerializer

    def get_queryset(self):
        medias = RealisationMedia.objects.select_related("media").order_by("ordre", "id")
        queryset = (
            cloisonner(Realisation.objects.all(), self.request.user)
            .select_related("commune", "secteur", "organisation")
            .prefetch_related("quartiers__arrondissement", Prefetch("medias", queryset=medias))
            .distinct()
        )
        # Publiées pour tous ; chaque auteur voit en plus ses propres brouillons.
        utilisateur = self.request.user
        if est_personnel_mairie(utilisateur):
            queryset = queryset.filter(Q(publie=True) | Q(organisation__isnull=True))
        elif getattr(utilisateur, "role", None) == Utilisateur.Role.ORGANISATION:
            queryset = queryset.filter(Q(publie=True) | Q(organisation=utilisateur.organisation_id))
        else:
            queryset = queryset.filter(publie=True)
        if self.action != "list":
            queryset = queryset.select_related("cree_par").prefetch_related("signalements", "suggestions")
        return queryset

    def _detail(self, pk):
        realisation = self.get_queryset().get(pk=pk)
        return RealisationDetailSerializer(realisation, context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        entree = RealisationEcritureSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        realisation = services.creer_realisation(par=request.user, **entree.validated_data)
        return reponse_succes(
            self._detail(realisation.pk),
            f"Réalisation enregistrée. Référence : {realisation.reference}.",
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        realisation = self.get_object()
        etait_publiee = realisation.publie
        entree = RealisationEcritureSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        realisation = services.modifier_realisation(realisation, par=request.user, **entree.validated_data)
        message = "Réalisation publiée." if realisation.publie and not etait_publiee else "Réalisation mise à jour."
        return reponse_succes(self._detail(realisation.pk), message)
