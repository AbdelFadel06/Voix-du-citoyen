from django.db.models import Exists, OuterRef, Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.codes_erreur import CodeErreur
from apps.core.permissions import EstAgentMairie, EstCitoyen, est_personnel_mairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_SUGGESTIONS,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
)

from . import exemples, services
from .filters import SuggestionFilter
from .models import Soutien, Suggestion, SuiviSuggestion
from .serializers import (
    PertinenceSerializer,
    ReponseSuggestionSerializer,
    SoutienSerializer,
    SuggestionCreateSerializer,
    SuggestionDetailSerializer,
    SuggestionListSerializer,
)

ACTIONS_MAIRIE = {"pertinente", "repondre"}
ACTIONS_DETAIL = {"retrieve", "create", "repondre"}

MESSAGE_PERTINENTE = "Suggestion marquée comme pertinente."
MESSAGE_NON_PERTINENTE = "Marque « pertinente » retirée."

EXEMPLE_INTROUVABLE = exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Suggestion inconnue")
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux agents de la mairie.", nom="Réservé à la mairie"
)
EXEMPLE_RESERVE_CITOYENS = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux citoyens.", nom="Réservé aux citoyens"
)
DESCRIPTION_VISIBILITE = """
**Ce que voit chaque rôle**
- **Agents et admins** : l'identité complète de l'auteur, la marque `est_pertinente`, l'agent
  qui a répondu, les notes internes.
- **Citoyens** : l'auteur sous la forme « Afiavi H. » (identité complète sur leurs propres
  suggestions) ; `je_soutiens` indique s'ils soutiennent déjà la suggestion.
- **Organisations** : jamais l'auteur (`auteur: null`).

Les suggestions n'ont **pas de statut**. La mairie coche celles qu'elle juge pertinentes ;
cette marque n'est **jamais** montrée aux citoyens ni aux organisations.
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_SUGGESTIONS],
        summary="Lister les suggestions",
        description=f"""
Liste **paginée** des suggestions des citoyens, de la plus récente à la plus ancienne
(`?tri=-nb_soutiens` pour les plus soutenues d'abord). Seules les **miniatures** des photos
sont renvoyées ; le détail est donné par `GET /suggestions/{{id}}/`.

`quartier: null` signifie que la suggestion concerne **toute la commune**.

**Filtres** : `secteur`, `quartier`, `date_debut`, `date_fin` (dates d'envoi) et, pour la
mairie uniquement, `est_pertinente=true` (suggestions retenues pour les prises de décision ;
le filtre est ignoré pour les autres rôles).
**Recherche** (`recherche`) : référence, titre, description.
**Tri** (`tri`) : `cree_le`, `maj_le`, `nb_soutiens`, `reference` (`-` pour l'ordre décroissant).
{DESCRIPTION_VISIBILITE}
**Connecté** : tous les rôles.
""",
        responses={200: SuggestionListSerializer(many=True), **erreurs(401, 403, 404)},
        examples=[
            exemple_element_liste("Vue par un citoyen", exemples.LISTE),
            exemple_element_liste("Pour toute la commune", exemples.LISTE_COMMUNE),
            exemple_element_liste("Vue par la mairie", exemples.LISTE_MAIRIE),
            EXEMPLE_PAGE_INEXISTANTE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG_SUGGESTIONS],
        summary="Consulter une suggestion",
        description=f"""
Détail complet : description, photos en taille réelle, **réponse officielle** de la mairie
(`reponse_officielle`, la plus récente) et **historique** des réponses.

Dans l'historique, les notes internes ne sont visibles que par les agents et admins.
{DESCRIPTION_VISIBILITE}
**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(SuggestionDetailSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Vue par un citoyen", exemples.DETAIL),
            exemple_succes("Vue par la mairie", exemples.DETAIL_MAIRIE),
            EXEMPLE_INTROUVABLE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_SUGGESTIONS],
        summary="Proposer une suggestion",
        description="""
Un citoyen propose une idée à la mairie pour le développement et le bien-être de la population.

- `titre`, `description` et `secteur` sont obligatoires.
- `quartier` est facultatif : vide, la suggestion concerne **toute la commune**.
- Photos facultatives (`medias`) : **3 au maximum**, envoyées au préalable avec `POST /medias/`
  (pas de vidéo ni d'audio).

**Après la création** : référence `SUG-AAAA-NNNNN`. Les autres citoyens peuvent la soutenir
avec `POST /suggestions/{id}/soutenir/`.

**Connecté** : citoyens uniquement.
""",
        request=SuggestionCreateSerializer,
        responses={201: enveloppe(SuggestionDetailSerializer), **erreurs(400, 401, 403, 409)},
        examples=[
            exemple_requete("Pour un quartier, avec photo", exemples.REQUETE),
            exemple_requete("Pour toute la commune", exemples.REQUETE_COMMUNE),
            exemple_succes(
                "Suggestion envoyée", exemples.CREEE, "Suggestion envoyée. Votre référence : SUG-2026-00031.", statut=201
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"titre": ["Ce champ est obligatoire."], "secteur": ["Ce champ est obligatoire."]},
                nom="Champs manquants",
            ),
            exemple_erreur(
                CodeErreur.MEDIAS_NON_CONFORMES,
                "Les fichiers joints à cette suggestion ne respectent pas les règles.",
                details={"medias": ["3 photo(s) au maximum."]},
            ),
            exemple_erreur(CodeErreur.MEDIA_INTROUVABLE),
            exemple_erreur(CodeErreur.MEDIA_DEJA_UTILISE),
            EXEMPLE_RESERVE_CITOYENS,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class SuggestionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    filterset_class = SuggestionFilter
    search_fields = ["reference", "titre", "description"]
    ordering_fields = ["cree_le", "maj_le", "nb_soutiens", "reference"]
    ordering = ["-cree_le"]

    def get_permissions(self):
        if self.action in ("create", "soutenir"):
            return [IsAuthenticated(), EstCitoyen()]
        if self.action in ACTIONS_MAIRIE:
            return [IsAuthenticated(), EstAgentMairie()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        return SuggestionDetailSerializer if self.action in ACTIONS_DETAIL else SuggestionListSerializer

    def get_queryset(self):
        utilisateur = self.request.user
        queryset = (
            Suggestion.objects.select_related("secteur", "quartier__arrondissement", "auteur")
            .prefetch_related("medias")
            .annotate(
                je_soutiens=Exists(
                    Soutien.objects.filter(suggestion=OuterRef("pk"), citoyen_id=getattr(utilisateur, "pk", None))
                )
            )
        )
        if self.action in ACTIONS_DETAIL:
            suivis = SuiviSuggestion.objects.select_related("auteur")
            if not est_personnel_mairie(utilisateur):
                suivis = suivis.filter(visible_citoyen=True)
            queryset = queryset.select_related("repondu_par").prefetch_related(Prefetch("suivis", queryset=suivis))
        return queryset

    def _detail(self, pk):
        suggestion = self.get_queryset().get(pk=pk)
        return SuggestionDetailSerializer(suggestion, context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        entree = SuggestionCreateSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = entree.validated_data
        suggestion = services.creer_suggestion(
            auteur=request.user,
            titre=donnees["titre"],
            description=donnees["description"],
            secteur=donnees["secteur"],
            quartier=donnees.get("quartier"),
            medias_ids=donnees["medias"],
        )
        return reponse_succes(
            self._detail(suggestion.pk),
            f"Suggestion envoyée. Votre référence : {suggestion.reference}.",
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        methods=["POST"],
        tags=[TAG_SUGGESTIONS],
        summary="Soutenir une suggestion",
        description="""
Ajoute le soutien du citoyen connecté et renvoie le nouveau nombre de soutiens.

- **Sans effet si le citoyen soutient déjà** : la requête peut être renvoyée sans risque
  (par exemple après une coupure réseau), le compteur n'augmente qu'une fois.
- Impossible sur sa propre suggestion (`SOUTIEN_PROPRE_SUGGESTION`).

**Connecté** : citoyens uniquement.
""",
        request=None,
        responses={200: enveloppe(SoutienSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_succes("Soutien enregistré", {"nb_soutiens": 58, "je_soutiens": True}, "Merci pour votre soutien !"),
            exemple_erreur(CodeErreur.SOUTIEN_PROPRE_SUGGESTION),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_CITOYENS,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @extend_schema(
        methods=["DELETE"],
        tags=[TAG_SUGGESTIONS],
        summary="Retirer son soutien",
        description="""
Retire le soutien du citoyen connecté et renvoie le nouveau nombre de soutiens.
**Sans effet si le citoyen ne soutenait pas** la suggestion (requête renvoyable sans risque).

**Connecté** : citoyens uniquement.
""",
        request=None,
        responses={200: enveloppe(SoutienSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_succes("Soutien retiré", {"nb_soutiens": 57, "je_soutiens": False}, "Votre soutien a été retiré."),
            exemple_erreur(CodeErreur.SOUTIEN_PROPRE_SUGGESTION),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_CITOYENS,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post", "delete"])
    def soutenir(self, request, pk=None):
        suggestion = self.get_object()
        if request.method == "POST":
            suggestion = services.soutenir(suggestion, request.user)
            return reponse_succes(
                {"nb_soutiens": suggestion.nb_soutiens, "je_soutiens": True}, "Merci pour votre soutien !"
            )
        suggestion = services.retirer_soutien(suggestion, request.user)
        return reponse_succes(
            {"nb_soutiens": suggestion.nb_soutiens, "je_soutiens": False}, "Votre soutien a été retiré."
        )

    @extend_schema(
        methods=["POST"],
        tags=[TAG_SUGGESTIONS],
        summary="Marquer une suggestion comme pertinente",
        description="""
Coche la suggestion comme **pertinente** pour la mairie, afin de la retrouver ensuite avec
`GET /suggestions/?est_pertinente=true` lors des prises de décision.

- **Sans effet si elle est déjà cochée** (requête renvoyable sans risque).
- La marque n'est **jamais** visible par les citoyens ni par les organisations, et ne
  déclenche aucune notification.

**Connecté** : agents et admins mairie.
""",
        request=None,
        responses={200: enveloppe(PertinenceSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Cochée", {"est_pertinente": True}, MESSAGE_PERTINENTE),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_MAIRIE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @extend_schema(
        methods=["DELETE"],
        tags=[TAG_SUGGESTIONS],
        summary="Retirer la marque « pertinente »",
        description="""
Décoche la suggestion. **Sans effet si elle n'était pas cochée** (requête renvoyable sans risque).

**Connecté** : agents et admins mairie.
""",
        request=None,
        responses={200: enveloppe(PertinenceSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Décochée", {"est_pertinente": False}, MESSAGE_NON_PERTINENTE),
            EXEMPLE_INTROUVABLE,
            EXEMPLE_RESERVE_MAIRIE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    @action(detail=True, methods=["post", "delete"])
    def pertinente(self, request, pk=None):
        cochee = request.method == "POST"
        suggestion = services.marquer_pertinente(self.get_object(), cochee)
        return reponse_succes(
            {"est_pertinente": suggestion.est_pertinente},
            MESSAGE_PERTINENTE if cochee else MESSAGE_NON_PERTINENTE,
        )

    @extend_schema(
        tags=[TAG_SUGGESTIONS],
        summary="Répondre ou ajouter une note interne",
        description="""
- `interne: false` (défaut) : **réponse officielle**, enregistrée dans `reponse_officielle`
  (visible par tous) et dans l'historique. Une nouvelle réponse remplace la précédente dans
  `reponse_officielle` ; toutes restent dans l'historique. L'auteur sera notifié (étape 9).
- `interne: true` : **note interne**, visible uniquement par les agents et admins.

**Connecté** : agents et admins mairie.
""",
        request=ReponseSuggestionSerializer,
        responses={201: enveloppe(SuggestionDetailSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Réponse officielle", {"commentaire": "Merci : 10 bancs sont prévus au budget 2027."}),
            exemple_requete("Note interne", {"commentaire": "Voir le devis du menuisier.", "interne": True}),
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
        suggestion = self.get_object()
        entree = ReponseSuggestionSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        services.repondre(suggestion, par=request.user, **entree.validated_data)
        message = "Note interne ajoutée." if entree.validated_data["interne"] else "Réponse publiée."
        return reponse_succes(self._detail(suggestion.pk), message, status=status.HTTP_201_CREATED)
