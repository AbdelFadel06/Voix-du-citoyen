from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import cloisonner
from apps.core.permissions import (
    EstAgentMairie,
    EstCitoyen,
    EstMairieOuOrganisation,
    EstOrganisationHabilitee,
    est_personnel_mairie,
)
from apps.core.visibilite import communes_autorisees, limiter_aux_communes, limiter_aux_secteurs, secteurs_autorises
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_SIGNALEMENTS,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    exemple_trop_de_requetes,
)

from . import exemples, services
from .filters import SignalementFilter
from .models import Signalement, SuiviSignalement
from .serializers import (
    AffectationOrganisationSerializer,
    AssignationSerializer,
    ChangementStatutSignalementSerializer,
    ReponseSignalementSerializer,
    SignalementCreateSerializer,
    SignalementCreeSerializer,
    SignalementDetailSerializer,
    SignalementListSerializer,
)

ACTIONS_MAIRIE = {"assigner", "repondre", "affecter_organisation"}
ACTIONS_DETAIL = {"retrieve", "create", "changer_statut", "prendre_en_charge", *ACTIONS_MAIRIE}

EXEMPLE_INTROUVABLE = exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Signalement inconnu")
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux agents de la mairie.", nom="Réservé à la mairie"
)
DESCRIPTION_VISIBILITE = """
**Ce que voit chaque rôle**
- **Les citoyens restent anonymes** : `auteur` vaut `null` pour tout le monde, **mairie
  comprise**. Seul l'auteur voit son identité sur ses propres signalements (`est_auteur: true`).
  La mairie lui répond par `/repondre/` et les changements de statut (notifications).
- **Agents et admins** : en plus, le service et l'agent assignés.
- **Citoyens et organisations** : ni assignation, ni notes internes.
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Lister les signalements",
        description=f"""
Liste **paginée** de tous les signalements de la commune, du plus récent au plus ancien.
Chaque élément ne contient que les **miniatures** des photos et vidéos ; le détail complet
est donné par `GET /signalements/{{id}}/`.

**Filtres** : `statut`, `secteur`, `quartier`, `date_debut`, `date_fin` (dates d'envoi).
**Recherche** (`recherche`) : référence, titre, description, repère.
**Tri** (`tri`) : `cree_le`, `maj_le`, `reference` (`-` pour l'ordre décroissant).
{DESCRIPTION_VISIBILITE}
**Connecté** : tous les rôles.
""",
        examples=[
            exemple_element_liste("Vu par un citoyen", exemples.LISTE_CITOYEN),
            exemple_element_liste("Vu par la mairie", exemples.LISTE_MAIRIE),
            EXEMPLE_PAGE_INEXISTANTE,
            *EXEMPLES_AUTH_REQUISE,
        ],
        responses={200: SignalementListSerializer(many=True), **erreurs(401, 403, 404)},
    ),
    retrieve=extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Consulter un signalement",
        description=f"""
Détail complet d'un signalement : photos et vidéos en taille réelle, description vocale,
précision GPS et **historique** chronologique (`historique`).

Dans l'historique, les **notes internes** ne sont visibles que par les agents et admins ;
les citoyens et organisations ne voient que les événements `visible_citoyen`.
{DESCRIPTION_VISIBILITE}
**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(SignalementDetailSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Vu par un citoyen", exemples.DETAIL_CITOYEN),
            exemple_succes("Vu par la mairie", exemples.DETAIL_MAIRIE),
            EXEMPLE_INTROUVABLE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Envoyer un signalement",
        description="""
**Deuxième étape de l'envoi en deux temps** : les photos, vidéos et l'enregistrement vocal
ont d'abord été envoyés un par un avec `POST /medias/` ; on envoie ici leurs identifiants.

**Description** : écrite (`description_texte`) **ou** vocale (`description_audio`), ou les deux.
Le `titre` est facultatif avec une description vocale : il est alors généré
« Secteur – Quartier » (`titre_genere: true`).

**Médias** (`medias`) : au moins 1 photo ou vidéo, au plus 4 photos et 1 vidéo. Les fichiers
doivent avoir été envoyés par le même utilisateur et ne pas avoir déjà servi.

**Localisation** — le `quartier` est **toujours obligatoire** :
- `GPS` (recommandé) : `latitude`, `longitude` et `precision_gps` obligatoires. La position
  doit se trouver dans la commune (`COORDONNEES_HORS_COMMUNE` sinon). Proposer le quartier
  avec `GET /quartiers/proche/` et le faire confirmer. Si la précision dépasse 100 m, le
  signalement est créé avec un avertissement `GPS_IMPRECIS` à afficher.
- `MANUEL` : `repere` obligatoire (« derrière le marché… ») ; les coordonnées sont ignorées.

**Après la création** : statut `SOUMIS`, référence `SIG-AAAA-NNNNN` à montrer au citoyen,
dossier confié automatiquement au service par défaut du secteur.

**Limitation** : 10 signalements par jour et par citoyen.

**Connecté** : citoyens uniquement.
""",
        request=SignalementCreateSerializer,
        responses={201: enveloppe(SignalementCreeSerializer), **erreurs(400, 401, 403, 409, 429)},
        examples=[
            exemple_requete("Mode GPS, description écrite", exemples.REQUETE_GPS),
            exemple_requete("Mode manuel, description vocale", exemples.REQUETE_VOCALE),
            exemple_succes(
                "Signalement envoyé",
                exemples.CREE,
                "Signalement envoyé. Votre référence : SIG-2026-00128.",
                statut=201,
            ),
            exemple_succes(
                "Envoyé avec un avertissement GPS",
                exemples.CREE_GPS_IMPRECIS,
                "Signalement envoyé. Votre référence : SIG-2026-00128.",
                statut=201,
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={
                    "description_texte": ["Décrivez le problème par écrit ou par un enregistrement vocal."],
                    "repere": ["Indiquez un repère (lieu connu à proximité) en mode manuel."],
                },
                nom="Champs manquants",
            ),
            exemple_erreur(CodeErreur.COORDONNEES_HORS_COMMUNE),
            exemple_erreur(
                CodeErreur.MEDIAS_NON_CONFORMES,
                "Les fichiers joints à ce signalement ne respectent pas les règles.",
                details={"medias": ["Au moins 1 photo ou vidéo est obligatoire."]},
            ),
            exemple_erreur(CodeErreur.MEDIA_INTROUVABLE),
            exemple_erreur(CodeErreur.MEDIA_DEJA_UTILISE),
            exemple_erreur(
                CodeErreur.PERMISSION_REFUSEE, "Action réservée aux citoyens.", nom="Réservé aux citoyens"
            ),
            exemple_trop_de_requetes(43200),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class SignalementViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    filterset_class = SignalementFilter
    search_fields = ["reference", "titre", "description_texte", "repere"]
    ordering_fields = ["cree_le", "maj_le", "reference"]
    ordering = ["-cree_le"]

    def get_permissions(self):
        if self.action in ("create", "mes_signalements"):
            return [IsAuthenticated(), EstCitoyen()]
        if self.action in ACTIONS_MAIRIE:
            return [IsAuthenticated(), EstAgentMairie()]
        if self.action == "changer_statut":
            # Organisation : seulement sur un dossier dont elle est en charge (contrôlé par le service).
            return [IsAuthenticated(), EstMairieOuOrganisation()]
        if self.action == "prendre_en_charge":
            return [IsAuthenticated(), EstOrganisationHabilitee()]
        return [IsAuthenticated()]

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "creation_signalement"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_serializer_class(self):
        return SignalementDetailSerializer if self.action in ACTIONS_DETAIL else SignalementListSerializer

    def get_queryset(self):
        queryset = cloisonner(
            Signalement.objects.select_related(
                "commune", "secteur", "quartier__arrondissement", "auteur", "service_assigne", "agent_assigne",
                "organisation_assignee",
            ).prefetch_related("medias"),
            self.request.user,
        )
        # Une organisation ne voit que les signalements de ses communes et secteurs d'intervention.
        queryset = limiter_aux_secteurs(queryset, secteurs_autorises(self.request.user))
        queryset = limiter_aux_communes(queryset, communes_autorisees(self.request.user))
        if self.action == "mes_signalements" and not getattr(self, "swagger_fake_view", False):
            queryset = queryset.filter(auteur=self.request.user)
        if self.action in ACTIONS_DETAIL:
            suivis = SuiviSignalement.objects.select_related("auteur__organisation")
            if not est_personnel_mairie(self.request.user):
                suivis = suivis.filter(visible_citoyen=True)
            queryset = queryset.select_related("description_audio", "doublon_de").prefetch_related(
                Prefetch("suivis", queryset=suivis)
            )
        return queryset

    def _detail(self, pk, serializer_class=SignalementDetailSerializer):
        signalement = self.get_queryset().get(pk=pk)
        return serializer_class(signalement, context=self.get_serializer_context()).data

    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        entree = SignalementCreateSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data
        signalement, avertissements = services.creer_signalement(
            auteur=request.user,
            secteur=donnees["secteur"],
            quartier=donnees["quartier"],
            mode_localisation=donnees["mode_localisation"],
            medias_ids=donnees["medias"],
            titre=donnees.get("titre", ""),
            description_texte=donnees.get("description_texte", ""),
            description_audio_id=donnees.get("description_audio"),
            latitude=donnees.get("latitude"),
            longitude=donnees.get("longitude"),
            precision_gps=donnees.get("precision_gps"),
            repere=donnees.get("repere", ""),
        )
        corps = self._detail(signalement.pk)
        corps["avertissements"] = avertissements
        return reponse_succes(
            corps,
            f"Signalement envoyé. Votre référence : {signalement.reference}.",
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Lister mes signalements",
        description="""
Signalements envoyés par le citoyen connecté, pour suivre leur traitement (liste paginée,
mêmes filtres, recherche et tri que `GET /signalements/`).

**Connecté** : citoyens uniquement.
""",
        responses={200: SignalementListSerializer(many=True), **erreurs(401, 403, 404)},
        examples=[
            exemple_element_liste("Mon signalement", {**exemples.LISTE_CITOYEN, "auteur": exemples.AUTEUR_COMPLET, "est_auteur": True}),
            exemple_erreur(CodeErreur.PERMISSION_REFUSEE, "Action réservée aux citoyens.", nom="Réservé aux citoyens"),
            EXEMPLE_PAGE_INEXISTANTE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=False, methods=["get"], url_path="mes-signalements")
    def mes_signalements(self, request):
        return self.list(request)

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Changer le statut d'un signalement",
        description="""
Fait avancer le dossier. Chaque changement est inscrit dans l'historique (visible par le
citoyen, avec le `commentaire`).

**Transitions possibles**
| Statut actuel | Nouveaux statuts possibles |
|---|---|
| `SOUMIS` | `RECU`, `REJETE`, `DOUBLON` |
| `RECU` | `EN_COURS`, `REJETE`, `DOUBLON` |
| `EN_COURS` | `RESOLU`, `REJETE`, `DOUBLON` |
| `RESOLU`, `REJETE`, `DOUBLON` | aucun (dossier clos) |

- `REJETE` : `commentaire` (motif) **obligatoire**.
- `DOUBLON` : `doublon_de` **obligatoire** (signalement d'origine, qui n'est pas lui-même un
  doublon). Un commentaire citant sa référence est ajouté s'il est vide.
- `RESOLU` : la date de résolution est enregistrée.

Une transition impossible donne `TRANSITION_STATUT_INVALIDE` avec, dans `details`, le statut
actuel et les statuts possibles.

**Organisation en charge** : l'organisation à qui le dossier est confié (elle l'a pris en charge,
ou la mairie le lui a confié) peut le faire avancer vers `RECU`, `EN_COURS` et `RESOLU`, avec un
`commentaire` visible par le citoyen. Rejeter ou classer en doublon reste réservé à la mairie
(`PERMISSION_REFUSEE`). Une organisation qui n'est pas en charge reçoit
`ORGANISATION_NON_EN_CHARGE` (403). L'historique indique le nom de l'organisation.

**Connecté** : agents et admins mairie ; organisation en charge du dossier.
""",
        request=ChangementStatutSignalementSerializer,
        responses={200: enveloppe(SignalementDetailSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Prise en charge", {"statut": "EN_COURS", "commentaire": "Une équipe interviendra cette semaine."}),
            exemple_requete("Rejet", {"statut": "REJETE", "commentaire": "Ce terrain est privé : contactez le propriétaire."}),
            exemple_requete("Doublon", {"statut": "DOUBLON", "doublon_de": 97}),
            exemple_succes("Statut mis à jour", exemples.DETAIL_MAIRIE, "Statut mis à jour : En cours de traitement."),
            exemple_erreur(
                CodeErreur.TRANSITION_STATUT_INVALIDE,
                "Impossible de passer de « Soumis » à « Résolu ».",
                details={"statut_actuel": "SOUMIS", "statuts_possibles": ["DOUBLON", "RECU", "REJETE"]},
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"commentaire": ["Le motif du rejet est obligatoire."]},
                nom="Rejet sans motif",
            ),
            EXEMPLE_INTROUVABLE,
            exemple_erreur(CodeErreur.ORGANISATION_NON_EN_CHARGE),
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post"], url_path="changer-statut")
    def changer_statut(self, request, pk=None):
        signalement = self.get_object()
        entree = ChangementStatutSignalementSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        signalement = services.changer_statut(signalement, par=request.user, **entree.validated_data)
        return reponse_succes(
            self._detail(signalement.pk), f"Statut mis à jour : {signalement.get_statut_display()}."
        )

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Assigner un signalement",
        description="""
Confie le dossier à un **service** et/ou à un **agent**. Avec un agent seul, son service est
assigné automatiquement ; avec les deux, l'agent doit appartenir au service.

L'historique indique au citoyen le service chargé du dossier (jamais le nom de l'agent).
Un dossier clos (`RESOLU`, `REJETE`, `DOUBLON`) ne peut plus être assigné
(`SIGNALEMENT_CLOTURE`).

À la création, le dossier est déjà confié au service par défaut de son secteur.

**Connecté** : agents et admins mairie.
""",
        request=AssignationSerializer,
        responses={200: enveloppe(SignalementDetailSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("À un agent", {"agent": 7}),
            exemple_requete("À un service", {"service": 3}),
            exemple_succes("Dossier assigné", exemples.DETAIL_MAIRIE, "Dossier assigné."),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"agent": ["Cet agent ne fait pas partie du service « Éclairage public »."]},
                nom="Agent d'un autre service",
            ),
            exemple_erreur(CodeErreur.SIGNALEMENT_CLOTURE),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_MAIRIE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post"])
    def assigner(self, request, pk=None):
        signalement = self.get_object()
        entree = AssignationSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        services.assigner(signalement, par=request.user, **entree.validated_data)
        return reponse_succes(self._detail(signalement.pk), "Dossier assigné.")

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Prendre en charge un signalement (organisation)",
        description="""
L'organisation connectée **se confie** ce signalement : son nom apparaît alors comme
organisation en charge (`organisation_assignee`), pour tous, et elle peut faire avancer le
statut (`/changer-statut/`). Les autres organisations de la zone continuent de voir le
signalement, avec le nom de l'organisation en charge.

**Conditions**
- Le signalement est dans son périmètre (commune et secteur d'intervention), sinon 404.
- Aucune organisation n'en est encore chargée, sinon `SIGNALEMENT_DEJA_PRIS_EN_CHARGE` (409) :
  afficher le nom de l'organisation en charge.
- Il n'est pas clos (`RESOLU`, `REJETE`, `DOUBLON`), sinon `SIGNALEMENT_CLOTURE` (409).
- Renvoyer la requête quand on en est déjà chargé est sans effet.

L'historique indique au citoyen que son dossier est pris en charge par l'organisation.
Pour voir les dossiers encore libres : `GET /signalements/?pris_en_charge=false`.

**Connecté** : organisations habilitées.
""",
        request=None,
        responses={200: enveloppe(SignalementDetailSerializer), **erreurs(401, 403, 404, 409)},
        examples=[
            exemple_succes("Dossier pris en charge", exemples.DETAIL_ORGANISATION, "Vous êtes en charge de ce signalement."),
            exemple_erreur(CodeErreur.SIGNALEMENT_DEJA_PRIS_EN_CHARGE),
            exemple_erreur(CodeErreur.SIGNALEMENT_CLOTURE),
            exemple_erreur(
                CodeErreur.PERMISSION_REFUSEE, "Action réservée aux organisations habilitées.", nom="Pas une organisation"
            ),
            EXEMPLE_INTROUVABLE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post"], url_path="prendre-en-charge")
    def prendre_en_charge(self, request, pk=None):
        signalement = services.prendre_en_charge(self.get_object(), par=request.user)
        return reponse_succes(self._detail(signalement.pk), "Vous êtes en charge de ce signalement.")

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Confier un signalement à une organisation",
        description="""
La mairie confie le dossier à une **organisation** (ONG, OSC), qui pourra alors faire avancer son
statut. Elle remplace l'organisation éventuellement déjà en charge ; `{"organisation": null}` la
retire. Une seule organisation à la fois.

- L'organisation doit être **habilitée** et intervenir dans la **commune et le secteur** du
  dossier, sinon `VALIDATION_ERREUR` sur `organisation`.
- Impossible sur un dossier clos (`SIGNALEMENT_CLOTURE`).
- Les comptes de l'organisation reçoivent une notification `AFFECTATION_SIGNALEMENT` ;
  l'historique l'indique au citoyen.

Pour choisir l'organisation : `GET /organisations/?commune=…&secteur=…`.

**Connecté** : agents et admins mairie.
""",
        request=AffectationOrganisationSerializer,
        responses={200: enveloppe(SignalementDetailSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Confier", {"organisation": 2}),
            exemple_requete("Retirer", {"organisation": None}),
            exemple_succes("Dossier confié", exemples.DETAIL_MAIRIE_ORGANISATION, "Dossier confié à l'organisation."),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"organisation": ["Cette organisation n'intervient pas dans la commune ou le secteur de ce dossier."]},
                nom="Hors du périmètre de l'organisation",
            ),
            exemple_erreur(CodeErreur.SIGNALEMENT_CLOTURE),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_MAIRIE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post"], url_path="affecter-organisation")
    def affecter_organisation(self, request, pk=None):
        signalement = self.get_object()
        entree = AffectationOrganisationSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        signalement = services.affecter_organisation(signalement, par=request.user, **entree.validated_data)
        message = "Dossier confié à l'organisation." if signalement.organisation_assignee_id else "Organisation retirée du dossier."
        return reponse_succes(self._detail(signalement.pk), message)

    @extend_schema(
        tags=[TAG_SIGNALEMENTS],
        summary="Répondre ou ajouter une note interne",
        description="""
Ajoute un message à l'historique du signalement :
- `interne: false` (défaut) : **réponse officielle** de la mairie, visible par le citoyen ;
- `interne: true` : **note interne**, visible uniquement par les agents et admins.

Possible à tout moment, y compris sur un dossier clos.

**Connecté** : agents et admins mairie.
""",
        request=ReponseSignalementSerializer,
        responses={201: enveloppe(SignalementDetailSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Réponse au citoyen", {"commentaire": "Merci, les travaux sont prévus pour lundi."}),
            exemple_requete("Note interne", {"commentaire": "Prévoir 2 m³ de latérite.", "interne": True}),
            exemple_succes("Réponse publiée", exemples.DETAIL_MAIRIE, "Réponse publiée.", statut=201),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"commentaire": ["Ce champ est obligatoire."]},
                nom="Commentaire manquant",
            ),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_MAIRIE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post"])
    def repondre(self, request, pk=None):
        signalement = self.get_object()
        entree = ReponseSignalementSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        services.repondre(signalement, par=request.user, **entree.validated_data)
        message = "Note interne ajoutée." if entree.validated_data["interne"] else "Réponse publiée."
        return reponse_succes(self._detail(signalement.pk), message, status=status.HTTP_201_CREATED)
