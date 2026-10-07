"""Gestion des services municipaux et des comptes du personnel (admins mairie)."""

import django_filters
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import FiltreCommune, cloisonner, commune_d_action
from apps.core.filters import Recherche
from apps.core.import_csv import importer_depuis_requete
from apps.core.permissions import EstAgentMairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_ADMINISTRATION,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    parametre_id,
    schema_import,
)
from apps.core.serializers import ImportCSVSerializer, message_bilan
from apps.territoire.serializers import ImportCommuneMixin
from apps.core.vues import VueAdministration

from . import services
from .models import ServiceMunicipal, Utilisateur
from .serializers import (
    ROLES_PERSONNEL,
    AgentCreationSerializer,
    AgentModificationSerializer,
    AgentSerializer,
    ServiceMunicipalEcritureSerializer,
    ServiceMunicipalSerializer,
)

class ImportServicesSerializer(ImportCommuneMixin, ImportCSVSerializer):
    pass


EXEMPLE_RESERVE_ADMIN = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux administrateurs de la mairie.", nom="Réservé aux admins mairie"
)
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux agents de la mairie.", nom="Réservé à la mairie"
)

# ---------------------------------------------------------------------------
# Services municipaux
# ---------------------------------------------------------------------------

ID_SERVICE = parametre_id("Identifiant du service municipal.")
SERVICE = {
    "id": 3,
    "nom": "Voirie et assainissement",
    "description": "Routes, caniveaux, ponts et dalots.",
    "responsable": {"id": 7, "nom": "Ahouansou", "prenoms": "Rodrigue"},
    "nb_agents": 4,
    "actif": True,
}
EXEMPLE_SERVICE_EXISTANT = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR, details={"nom": ["Un service porte déjà ce nom."]}, nom="Nom déjà pris"
)


class ServiceFilter(django_filters.FilterSet):
    actif = django_filters.BooleanFilter(help_text="`true` : services actifs ; `false` : services fermés.")
    commune = FiltreCommune()

    class Meta:
        model = ServiceMunicipal
        fields = ["actif", "commune"]


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Lister les services municipaux",
        description="""
Tous les services municipaux, triés par nom, avec leur responsable et leur nombre d'agents
actifs (liste complète, sans pagination). Sert notamment à choisir le service lors de
l'assignation d'un signalement. Filtre `?actif=true`.

**Connecté** : agents et admins mairie.
""",
        responses={200: enveloppe(ServiceMunicipalSerializer, many=True), **erreurs(401, 403)},
        examples=[exemple_succes("Services", [SERVICE]), EXEMPLE_RESERVE_MAIRIE, *EXEMPLES_AUTH_REQUISE],
    ),
    retrieve=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Consulter un service municipal",
        description="""
Détail d'un service : missions, responsable, nombre d'agents actifs. Ses agents :
`GET /agents/?service=<id>`.

**Connecté** : agents et admins mairie.
""",
        parameters=[ID_SERVICE],
        responses={200: enveloppe(ServiceMunicipalSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Service", SERVICE),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Service inconnu"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Créer un service municipal",
        description="""
Crée un service (nom unique). Le responsable, facultatif, doit être un agent ou un admin
actif. Pour en créer plusieurs d'un coup : `POST /services/import/`.

**Connecté** : admins mairie uniquement.
""",
        request=ServiceMunicipalEcritureSerializer,
        responses={201: enveloppe(ServiceMunicipalSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Nouveau service", {"nom": "Voirie et assainissement", "description": "Routes, caniveaux, ponts et dalots."}),
            exemple_succes("Service créé", {**SERVICE, "responsable": None, "nb_agents": 0}, "Service « Voirie et assainissement » créé.", statut=201),
            EXEMPLE_SERVICE_EXISTANT,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Modifier un service municipal",
        description="""
Modifie uniquement les champs envoyés (nom, description, responsable). `{"actif": false}`
ferme le service sans le supprimer : les signalements qui lui ont été confiés restent
intacts.

**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_SERVICE],
        request=ServiceMunicipalEcritureSerializer,
        responses={200: enveloppe(ServiceMunicipalSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Nommer un responsable", {"responsable": 7}),
            exemple_succes("Service modifié", SERVICE, "Service « Voirie et assainissement » modifié."),
            EXEMPLE_SERVICE_EXISTANT,
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Service inconnu"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class ServiceMunicipalViewSet(VueAdministration):
    permission_lecture = EstAgentMairie
    filter_backends = [DjangoFilterBackend]
    filterset_class = ServiceFilter
    serializer_lecture = ServiceMunicipalSerializer
    libelle = "Service"

    def get_serializer_class(self):
        if self.action in ("create", "partial_update"):
            return ServiceMunicipalEcritureSerializer
        return ServiceMunicipalSerializer

    def get_queryset(self):
        queryset = (
            ServiceMunicipal.objects.select_related("responsable", "commune")
            .annotate(nb_agents=Count("agents", filter=Q(agents__is_active=True)))
            .order_by("nom")
        )
        return cloisonner(queryset, self.request.user)

    def _lecture(self, service):
        return ServiceMunicipalSerializer(self.get_queryset().get(pk=service.pk)).data

    @extend_schema(
        **schema_import(
            TAG_ADMINISTRATION,
            "services municipaux",
            "nom;description\nVoirie et assainissement;Routes, caniveaux, ponts et dalots\n"
            "Hygiène et salubrité;Ramassage des ordures, dépôts sauvages",
            {"crees": 5, "mis_a_jour": 1, "desactives": 0},
            ["Ligne 3 : « nom » est vide.", "Ligne 6 : le service « Voirie » apparaît déjà ligne 2."],
            requete=ImportServicesSerializer,
            parametres="""
- `nom` obligatoire, `description` facultative. Les services sont reconnus par leur nom.
""",
        )
    )
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def importer(self, request):
        entree = ImportServicesSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        options = entree.validated_data
        commune = commune_d_action(request.user, options.get("commune"))
        bilan = importer_depuis_requete(
            options["fichier"],
            lambda texte: services.importer_services(
                texte, commune, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            ),
        )
        return reponse_succes(bilan, message_bilan(bilan, "service(s)"))


# ---------------------------------------------------------------------------
# Comptes du personnel
# ---------------------------------------------------------------------------

ID_AGENT = parametre_id("Identifiant du compte.")
AGENT = {
    "id": 7,
    "telephone": "+2290196000007",
    "nom": "Ahouansou",
    "prenoms": "Rodrigue",
    "email": "r.ahouansou@mairie-parakou.bj",
    "role": "AGENT",
    "service": {"id": 3, "nom": "Voirie et assainissement"},
    "actif": True,
    "date_joined": "2026-10-07T09:00:00+01:00",
    "last_login": "2026-10-07T11:42:10+01:00",
}
EXEMPLE_AGENT_INVALIDE = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={
        "service": ["Un agent doit être rattaché à un service municipal."],
        "mot_de_passe": ["Ce mot de passe est trop court. Il doit contenir au minimum 8 caractères."],
    },
    nom="Données invalides",
)


class AgentFilter(django_filters.FilterSet):
    role = django_filters.ChoiceFilter(choices=ROLES_PERSONNEL, help_text="`AGENT` ou `ADMIN_MAIRIE`.")
    service = django_filters.NumberFilter(field_name="service", help_text="Identifiant du service.")
    actif = django_filters.BooleanFilter(field_name="is_active", help_text="`true` : comptes actifs ; `false` : désactivés.")
    commune = FiltreCommune()

    class Meta:
        model = Utilisateur
        fields = ["role", "service", "actif", "commune"]


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Lister les agents et admins",
        description="""
Comptes du personnel de la mairie (rôles `AGENT` et `ADMIN_MAIRIE`), triés par nom (liste
complète). Sert notamment à choisir l'agent lors de l'assignation d'un signalement.

**Filtres** : `role`, `service`, `actif`. **Recherche** : nom, prénoms, téléphone.

**Connecté** : agents et admins mairie.
""",
        responses={200: enveloppe(AgentSerializer, many=True), **erreurs(401, 403)},
        examples=[exemple_succes("Personnel", [AGENT]), EXEMPLE_RESERVE_MAIRIE, *EXEMPLES_AUTH_REQUISE],
    ),
    retrieve=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Consulter un compte du personnel",
        description="""
Détail d'un agent ou d'un admin : identité, rôle, service, état du compte, dernière connexion.

**Connecté** : agents et admins mairie.
""",
        parameters=[ID_AGENT],
        responses={200: enveloppe(AgentSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Agent", AGENT),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Compte inconnu"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Créer un compte agent ou admin",
        description="""
Crée le compte d'un membre du personnel, qui pourra se connecter tout de suite avec son
**adresse e-mail** et le mot de passe choisi (aucun code SMS : la mairie se porte garante de
la personne). L'e-mail est obligatoire et unique ; le téléphone reste enregistré.
Lui communiquer le mot de passe ; il ne peut pas encore le changer lui-même.

- `role` : `AGENT` (doit avoir un `service`) ou `ADMIN_MAIRIE`.
- Numéro béninois ; un numéro déjà utilisé donne `TELEPHONE_DEJA_UTILISE`, un e-mail déjà
  utilisé `EMAIL_DEJA_UTILISE`.

**Connecté** : admins mairie uniquement.
""",
        request=AgentCreationSerializer,
        responses={201: enveloppe(AgentSerializer), **erreurs(400, 401, 403, 409)},
        examples=[
            exemple_requete(
                "Nouvel agent",
                {
                    "telephone": "0196000007",
                    "nom": "Ahouansou",
                    "prenoms": "Rodrigue",
                    "email": "r.ahouansou@mairie-parakou.bj",
                    "role": "AGENT",
                    "service": 3,
                    "mot_de_passe": "Parakou!2026",
                },
            ),
            exemple_succes("Compte créé", {**AGENT, "last_login": None}, "Compte de Rodrigue Ahouansou créé.", statut=201),
            EXEMPLE_AGENT_INVALIDE,
            exemple_erreur(
                CodeErreur.TELEPHONE_DEJA_UTILISE, details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]}
            ),
            exemple_erreur(CodeErreur.EMAIL_DEJA_UTILISE, details={"email": ["Cette adresse e-mail est déjà utilisée."]}),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Modifier un compte agent ou admin",
        description="""
Modifie uniquement les champs envoyés : identité, rôle, service, nouveau mot de passe.

- `{"actif": false}` **désactive** le compte : la personne ne peut plus se connecter, et ses
  sessions en cours sont coupées à la requête suivante (`COMPTE_DESACTIVE`). Rien n'est
  supprimé ; `{"actif": true}` le réactive.
- Le téléphone ne se modifie pas. L'e-mail (identifiant de connexion) peut changer, mais
  jamais être vide, et doit rester unique (`EMAIL_DEJA_UTILISE`).
- Un admin ne peut ni désactiver son propre compte ni changer son propre rôle
  (`ACTION_SUR_SON_PROPRE_COMPTE`).

**Connecté** : admins mairie uniquement.
""",
        parameters=[ID_AGENT],
        request=AgentModificationSerializer,
        responses={200: enveloppe(AgentSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Changer de service", {"service": 5}),
            exemple_requete("Désactiver le compte", {"actif": False}),
            exemple_requete("Nouveau mot de passe", {"mot_de_passe": "Nouveau!2026"}),
            exemple_succes("Compte modifié", AGENT, "Compte de Rodrigue Ahouansou modifié."),
            EXEMPLE_AGENT_INVALIDE,
            exemple_erreur(CodeErreur.ACTION_SUR_SON_PROPRE_COMPTE),
            exemple_erreur(CodeErreur.EMAIL_DEJA_UTILISE, details={"email": ["Cette adresse e-mail est déjà utilisée."]}),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Compte inconnu"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class AgentViewSet(VueAdministration):
    permission_lecture = EstAgentMairie
    filter_backends = [DjangoFilterBackend, Recherche]
    filterset_class = AgentFilter
    search_fields = ["nom", "prenoms", "telephone"]
    serializer_class = AgentSerializer

    def get_queryset(self):
        queryset = (
            Utilisateur.objects.filter(role__in=[Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE])
            .select_related("service", "commune")
            .order_by("nom", "prenoms")
        )
        return cloisonner(queryset, self.request.user)

    def create(self, request, *args, **kwargs):
        entree = AgentCreationSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = dict(entree.validated_data)
        donnees["commune"] = commune_d_action(request.user, donnees.pop("commune", None))
        agent = services.creer_agent(**donnees)
        return reponse_succes(
            AgentSerializer(agent).data, f"Compte de {agent.get_full_name()} créé.", status=status.HTTP_201_CREATED
        )

    def partial_update(self, request, *args, **kwargs):
        entree = AgentModificationSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        agent = services.modifier_agent(self.get_object(), par=request.user, **entree.validated_data)
        return reponse_succes(AgentSerializer(agent).data, f"Compte de {agent.get_full_name()} modifié.")
