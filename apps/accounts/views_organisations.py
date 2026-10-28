"""
Organisations partenaires : consultation avec statistiques (agents, admins) et gestion par la
mairie (création, périmètre, comptes des membres), depuis l'application web ou la plateforme
IBDC (clé d'API). La suspension totale est réservée à l'admin de la plateforme.
"""

import django_filters
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import FiltreCommune, commune_imposee
from apps.core.exceptions import ErreurMetier
from apps.core.filters import Recherche
from apps.core.permissions import EstAdminMairie, EstAdminPlateforme, EstAgentMairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_ADMINISTRATION,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    parametre_id,
)

from . import exemples, services
from .models import Organisation
from .serializers import (
    MembreCreationSerializer,
    MembreModificationSerializer,
    MembreOrganisationSerializer,
    OrganisationDetailSerializer,
    OrganisationEcritureSerializer,
    OrganisationListeSerializer,
    RetraitCommuneSerializer,
    SuspensionOrganisationSerializer,
)
from .statistiques import statistiques


class OrganisationFilter(django_filters.FilterSet):
    commune = FiltreCommune(
        champ="communes",
        help_text="Organisations intervenant dans cette commune, et statistiques limitées à elle "
        "(admin de la plateforme ; la mairie d'une commune est toujours limitée à la sienne).",
    )
    type = django_filters.ChoiceFilter(choices=Organisation.Type.choices, help_text="`ONG`, `OSC` ou `AUTRE`.")
    statut_habilitation = django_filters.ChoiceFilter(
        choices=Organisation.StatutHabilitation.choices, help_text="`HABILITEE` ou `SUSPENDUE`."
    )
    secteur = django_filters.NumberFilter(
        field_name="secteurs", help_text="Organisations intervenant dans ce secteur (identifiant)."
    )
    # Période des statistiques : ne filtre pas les organisations.
    date_debut = django_filters.DateFilter(
        method="periode", help_text="Statistiques des signalements envoyés à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        method="periode", help_text="Statistiques des signalements envoyés jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )

    class Meta:
        model = Organisation
        fields = ["commune", "type", "statut_habilitation", "secteur", "date_debut", "date_fin"]

    def periode(self, queryset, name, valeur):
        return queryset


ID_ORGANISATION = parametre_id("Identifiant de l'organisation.")
ID_MEMBRE = OpenApiParameter("membre_id", int, OpenApiParameter.PATH, description="Identifiant du compte du membre.")
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux agents de la mairie.", nom="Réservé à la mairie"
)
EXEMPLE_RESERVE_ADMIN = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux administrateurs de la mairie.", nom="Réservé aux admins mairie"
)
EXEMPLE_RESERVE_PLATEFORME = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE,
    "Action réservée à l'administrateur de la plateforme.",
    nom="Réservé à l'admin de la plateforme",
)
EXEMPLE_INCONNUE = exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Organisation inconnue ou hors de votre commune")
EXEMPLE_DATES = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={"date_fin": ["La date de fin doit suivre la date de début."]},
    nom="Dates incohérentes",
)
STATISTIQUES = """
**Statistiques** : les signalements du **périmètre** de l'organisation (ses communes
d'intervention × ses secteurs d'intervention), c'est-à-dire ceux qu'elle voit, et la façon dont
ils ont été traités : en attente (`SOUMIS`), en cours (reçus ou en traitement), résolus,
rejetés, taux de résolution et délai moyen de résolution ; dossiers pris en charge par
l'organisation et réalisations publiées. Période : `date_debut`, `date_fin` (date d'envoi des
signalements). La **mairie d'une commune** ne voit que les organisations qui interviennent chez
elle, avec des chiffres **limités à sa commune** ; l'**admin de la plateforme** voit toutes les
organisations (ou une commune avec `?commune=`).
"""
GESTION = """
**Gestion par la mairie** : chaque mairie gère les organisations qui interviennent dans **sa
commune** (une organisation hors de sa commune donne `RESSOURCE_INTROUVABLE`). Les appels
peuvent venir de l'application web (jeton d'un admin mairie) ou de la plateforme IBDC (clé
d'API de l'institution). Rien ne se supprime : on retire sa commune du périmètre, ou l'admin
de la plateforme suspend l'organisation.
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Lister les organisations et leurs statistiques",
        description=f"""
Liste **paginée** des organisations partenaires (ONG, OSC…), triées par nom, avec leur périmètre
d'intervention, leur état d'habilitation, leurs comptes actifs et leurs chiffres clés.

**Filtres** : `commune`, `secteur`, `type`, `statut_habilitation` ; **recherche** : nom, sigle.
{STATISTIQUES}
**Connecté** : agents et admins mairie.
""",
        responses={200: OrganisationListeSerializer(many=True), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_element_liste("Organisation", exemples.ORGANISATION_LISTE),
            EXEMPLE_DATES,
            EXEMPLE_RESERVE_MAIRIE,
            EXEMPLE_PAGE_INEXISTANTE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    retrieve=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Consulter une organisation et ses statistiques",
        description=f"""
Fiche complète d'une organisation (contacts, habilitation) et ses statistiques, au total puis
**commune par commune** et **secteur par secteur**. Accepte aussi `date_debut` et `date_fin`.
{STATISTIQUES}
**Connecté** : agents et admins mairie.
""",
        parameters=[ID_ORGANISATION],
        responses={200: enveloppe(OrganisationDetailSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_succes("Organisation", exemples.ORGANISATION_DETAIL),
            EXEMPLE_DATES,
            EXEMPLE_RESERVE_MAIRIE,
            EXEMPLE_INCONNUE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    create=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Enregistrer une organisation",
        description=f"""
Enregistre une organisation (ONG, OSC…) qui intervient dans votre commune. Elle est **habilitée**
dès sa création (date du jour, par vous) ; créez ensuite les comptes de ses membres avec
`POST /organisations/{{id}}/membres/`.

**Une organisation intervenant dans plusieurs communes n'est enregistrée qu'une fois**, grâce à
son `numero_enregistrement` (facultatif pour l'instant, mais à renseigner dès que possible). S'il
est déjà connu (une autre mairie l'a enregistrée), rien n'est recréé : **votre commune et vos
secteurs sont ajoutés à son périmètre** (réponse **200** au lieu de 201, même fiche, même `id`).
**Sans numéro, une nouvelle fiche est toujours créée** : deux mairies pourraient alors créer la
même organisation en double. Gardez l'`id` renvoyé pour la retrouver.

- Communes d'intervention : la vôtre, automatiquement. L'admin de la plateforme indique `communes`.
- `secteurs` : ses secteurs d'intervention (ils valent pour toutes ses communes).
{GESTION}
**Connecté** : admins mairie (ou clé d'API d'une institution).
""",
        request=OrganisationEcritureSerializer,
        responses={
            201: enveloppe(OrganisationDetailSerializer),
            200: enveloppe(OrganisationDetailSerializer),
            **erreurs(400, 401, 403),
        },
        examples=[
            exemple_requete("Nouvelle organisation", exemples.REQUETE_ORGANISATION),
            exemple_succes(
                "Organisation enregistrée", exemples.ORGANISATION_DETAIL,
                "Organisation « ONG Eau Pour Tous » enregistrée.", statut=201,
            ),
            exemple_succes(
                "Déjà enregistrée par une autre mairie", exemples.ORGANISATION_DETAIL,
                "Organisation déjà enregistrée : votre commune et vos secteurs ont été ajoutés à son périmètre.",
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"type": ["« FONDATION » n'est pas un choix valide."], "nom": ["Ce champ est obligatoire."]},
                nom="Données invalides",
            ),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    partial_update=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Modifier une organisation",
        description=f"""
Modifie uniquement les champs envoyés : nom, sigle, type, contacts, date d'expiration de
l'habilitation, secteurs (la liste **remplace** la précédente). L'admin de la plateforme peut
aussi remplacer `communes`.

Un `numero_enregistrement` déjà porté par une autre organisation donne `CONFLIT` (409).
{GESTION}
**Connecté** : admins mairie (ou clé d'API d'une institution).
""",
        parameters=[ID_ORGANISATION],
        request=OrganisationEcritureSerializer,
        responses={200: enveloppe(OrganisationDetailSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Changer les secteurs", {"secteurs": [4, 2, 7]}),
            exemple_requete("Prolonger l'habilitation", {"date_expiration": "2028-12-31"}),
            exemple_succes("Organisation modifiée", exemples.ORGANISATION_DETAIL, "Organisation « ONG Eau Pour Tous » modifiée."),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"secteurs": ["Ce secteur n'existe pas ou n'est plus actif."]},
                nom="Secteur inconnu",
            ),
            exemple_erreur(
                CodeErreur.CONFLIT,
                "Une autre organisation porte déjà ce numéro d'enregistrement.",
                details={"numero_enregistrement": ["Une autre organisation porte déjà ce numéro."]},
            ),
            EXEMPLE_INCONNUE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class OrganisationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = OrganisationListeSerializer
    filter_backends = [DjangoFilterBackend, Recherche]
    filterset_class = OrganisationFilter
    search_fields = ["nom", "sigle"]

    def get_permissions(self):
        if self.action in ("suspendre", "rehabiliter"):
            return [IsAuthenticated(), EstAdminPlateforme()]
        if self.action in ("create", "partial_update", "retirer_commune", "creer_membre", "modifier_membre"):
            return [IsAuthenticated(), EstAdminMairie()]
        return [IsAuthenticated(), EstAgentMairie()]

    def get_queryset(self):
        queryset = (
            Organisation.objects.prefetch_related("communes", "secteurs")
            .annotate(nb_comptes=Count("membres", filter=Q(membres__is_active=True), distinct=True))
            .order_by("nom")
        )
        imposee = commune_imposee(self.request.user)
        return queryset.filter(communes=imposee) if imposee else queryset

    def _parametres_statistiques(self):
        """Commune et période du calcul (la mairie d'une commune est limitée à la sienne)."""
        filtres = OrganisationFilter(self.request.query_params, queryset=Organisation.objects.none(), request=self.request)
        filtres.is_valid()
        donnees = filtres.form.cleaned_data
        debut, fin = donnees.get("date_debut"), donnees.get("date_fin")
        if debut and fin and fin < debut:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR, details={"date_fin": ["La date de fin doit suivre la date de début."]}
            )
        commune = commune_imposee(self.request.user) or donnees.get("commune")
        return {"commune": int(commune) if commune else None, "date_debut": debut, "date_fin": fin}

    def _detail(self, pk):
        organisation = self.get_queryset().get(pk=pk)
        contexte = {
            **self.get_serializer_context(),
            "statistiques": statistiques([organisation], details=True, **self._parametres_statistiques()),
        }
        return OrganisationDetailSerializer(organisation, context=contexte).data

    def list(self, request, *args, **kwargs):
        organisations = list(self.paginate_queryset(self.filter_queryset(self.get_queryset())))
        contexte = {
            **self.get_serializer_context(),
            "statistiques": statistiques(organisations, **self._parametres_statistiques()),
        }
        return self.get_paginated_response(OrganisationListeSerializer(organisations, many=True, context=contexte).data)

    def retrieve(self, request, *args, **kwargs):
        return reponse_succes(self._detail(self.get_object().pk))

    def create(self, request, *args, **kwargs):
        entree = OrganisationEcritureSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        donnees = dict(entree.validated_data)
        demandees = donnees.pop("communes", None)
        commune = request.user.commune
        communes = [commune] if commune else (demandees or [])
        if not communes:
            raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details={"communes": ["Indiquez au moins une commune."]})
        organisation, creee = services.enregistrer_organisation(
            par=request.user, communes=communes, secteurs=donnees.pop("secteurs", []), **donnees
        )
        if creee:
            return reponse_succes(
                self._detail(organisation.pk),
                f"Organisation « {organisation.nom} » enregistrée.",
                status=status.HTTP_201_CREATED,
            )
        return reponse_succes(
            self._detail(organisation.pk),
            "Organisation déjà enregistrée : votre commune et vos secteurs ont été ajoutés à son périmètre.",
        )

    def partial_update(self, request, *args, **kwargs):
        organisation = self.get_object()
        entree = OrganisationEcritureSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        donnees = dict(entree.validated_data)
        communes = donnees.pop("communes", None)
        organisation = services.modifier_organisation(organisation, **donnees)
        if communes is not None and request.user.commune_id is None:
            organisation.communes.set(communes)
        return reponse_succes(self._detail(organisation.pk), f"Organisation « {organisation.nom} » modifiée.")

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Retirer sa commune du périmètre d'une organisation",
        description=f"""
L'organisation n'intervient plus dans votre commune : elle n'y voit plus aucun signalement et
disparaît de votre liste. Elle reste habilitée ailleurs. Les dossiers dont elle était déjà en
charge dans votre commune restent à son nom : confiez-les à une autre organisation avec
`/signalements/{{id}}/affecter-organisation/` si besoin. Pour la réintégrer, enregistrez-la à
nouveau (`POST /organisations/` avec son numéro d'enregistrement).

L'admin de la plateforme indique la `commune` à retirer.
{GESTION}
**Connecté** : admins mairie (ou clé d'API d'une institution).
""",
        parameters=[ID_ORGANISATION],
        request=RetraitCommuneSerializer,
        responses={200: enveloppe(), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Mairie d'une commune", {}),
            exemple_requete("Admin de la plateforme", {"commune": 1}),
            exemple_succes("Commune retirée", None, "Parakou ne fait plus partie du périmètre de « ONG Eau Pour Tous »."),
            exemple_erreur(CodeErreur.VALIDATION_ERREUR, details={"commune": ["Indiquez la commune."]}, nom="Commune manquante"),
            EXEMPLE_INCONNUE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def retirer_commune(self, request, pk=None):
        organisation = self.get_object()
        entree = RetraitCommuneSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        commune = request.user.commune or entree.validated_data.get("commune")
        if commune is None:
            raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details={"commune": ["Indiquez la commune."]})
        services.retirer_commune(organisation, commune)
        return reponse_succes(message=f"{commune.nom} ne fait plus partie du périmètre de « {organisation.nom} ».")

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Suspendre une organisation",
        description="""
Suspend l'organisation **partout** : ses comptes perdent l'accès à l'API dès la requête
suivante (`ORGANISATION_NON_HABILITEE`), et elle ne reçoit plus de notifications. Le `motif` est
obligatoire. Réhabiliter avec `/rehabiliter/`.

Une mairie qui ne veut plus travailler avec une organisation retire plutôt sa commune de son
périmètre (`/retirer-commune/`).

**Connecté** : administrateur de la plateforme uniquement.
""",
        parameters=[ID_ORGANISATION],
        request=SuspensionOrganisationSerializer,
        responses={200: enveloppe(OrganisationDetailSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_requete("Suspension", {"motif": "Rapport d'activité non transmis depuis un an."}),
            exemple_succes(
                "Organisation suspendue",
                {**exemples.ORGANISATION_DETAIL, "statut_habilitation": "SUSPENDUE", "acces_actif": False,
                 "motif_suspension": "Rapport d'activité non transmis depuis un an."},
                "Organisation « ONG Eau Pour Tous » suspendue.",
            ),
            exemple_erreur(CodeErreur.VALIDATION_ERREUR, details={"motif": ["Ce champ ne peut être vide."]}, nom="Motif manquant"),
            EXEMPLE_INCONNUE,
            EXEMPLE_RESERVE_PLATEFORME,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def suspendre(self, request, pk=None):
        organisation = self.get_object()
        entree = SuspensionOrganisationSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        services.suspendre_organisation(organisation, entree.validated_data["motif"])
        return reponse_succes(self._detail(organisation.pk), f"Organisation « {organisation.nom} » suspendue.")

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Réhabiliter une organisation",
        description="""
Rétablit l'habilitation d'une organisation suspendue et efface le motif : ses comptes
retrouvent l'accès. Une habilitation expirée se prolonge plutôt avec `PATCH`
(`date_expiration`).

**Connecté** : administrateur de la plateforme uniquement.
""",
        parameters=[ID_ORGANISATION],
        request=None,
        responses={200: enveloppe(OrganisationDetailSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Organisation réhabilitée", exemples.ORGANISATION_DETAIL, "Organisation « ONG Eau Pour Tous » réhabilitée."),
            EXEMPLE_INCONNUE,
            EXEMPLE_RESERVE_PLATEFORME,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def rehabiliter(self, request, pk=None):
        organisation = self.get_object()
        services.rehabiliter_organisation(organisation)
        return reponse_succes(self._detail(organisation.pk), f"Organisation « {organisation.nom} » réhabilitée.")

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Lister les comptes des membres d'une organisation",
        description="""
Comptes utilisateurs des membres de l'organisation (actifs et désactivés), qui se connectent à
l'interface des organisations avec leur e-mail et leur mot de passe.

**Connecté** : agents et admins mairie (organisations de leur commune).
""",
        parameters=[ID_ORGANISATION],
        responses={200: enveloppe(MembreOrganisationSerializer, many=True), **erreurs(401, 403, 404)},
        examples=[exemple_succes("Membres", [exemples.MEMBRE]), EXEMPLE_INCONNUE, EXEMPLE_RESERVE_MAIRIE, *EXEMPLES_AUTH_REQUISE],
    )
    def membres(self, request, pk=None):
        organisation = self.get_object()
        comptes = organisation.membres.order_by("nom", "prenoms")
        return reponse_succes(MembreOrganisationSerializer(comptes, many=True).data)

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Créer le compte d'un membre d'une organisation",
        description=f"""
Crée le compte d'un membre de l'organisation. Il se connecte tout de suite à l'interface des
organisations avec son **e-mail** et ce mot de passe (aucun code SMS) : communiquez-le lui.

- E-mail obligatoire et unique (`EMAIL_DEJA_UTILISE`), numéro béninois unique
  (`TELEPHONE_DEJA_UTILISE`).
- Il voit les signalements du périmètre de l'organisation (ses communes et secteurs).
{GESTION}
**Connecté** : admins mairie (ou clé d'API d'une institution).
""",
        parameters=[ID_ORGANISATION],
        request=MembreCreationSerializer,
        responses={201: enveloppe(MembreOrganisationSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Nouveau membre", exemples.REQUETE_MEMBRE),
            exemple_succes("Compte créé", exemples.MEMBRE, "Compte de Mireille Dossou créé.", statut=201),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"mot_de_passe": ["Ce mot de passe est trop court. Il doit contenir au minimum 6 caractères."]},
                nom="Mot de passe trop court",
            ),
            exemple_erreur(CodeErreur.EMAIL_DEJA_UTILISE, details={"email": ["Cette adresse e-mail est déjà utilisée."]}),
            EXEMPLE_INCONNUE,
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def creer_membre(self, request, pk=None):
        organisation = self.get_object()
        entree = MembreCreationSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        membre = services.creer_membre(organisation, **entree.validated_data)
        return reponse_succes(
            MembreOrganisationSerializer(membre).data,
            f"Compte de {membre.get_full_name()} créé.",
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Modifier le compte d'un membre d'une organisation",
        description=f"""
Modifie uniquement les champs envoyés : identité, e-mail (identifiant de connexion, jamais vide
et unique), nouveau mot de passe. `{{"actif": false}}` désactive le compte (la personne ne peut
plus se connecter, ses sessions sont coupées à la requête suivante) ; `true` le réactive.
{GESTION}
**Connecté** : admins mairie (ou clé d'API d'une institution).
""",
        parameters=[ID_ORGANISATION, ID_MEMBRE],
        request=MembreModificationSerializer,
        responses={200: enveloppe(MembreOrganisationSerializer), **erreurs(400, 401, 403, 404, 409)},
        examples=[
            exemple_requete("Désactiver", {"actif": False}),
            exemple_requete("Nouveau mot de passe", {"mot_de_passe": "Nouveau!2026"}),
            exemple_succes("Compte modifié", exemples.MEMBRE, "Compte de Mireille Dossou modifié."),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"email": ["L'adresse e-mail est obligatoire : elle sert à se connecter."]},
                nom="E-mail vide",
            ),
            exemple_erreur(CodeErreur.EMAIL_DEJA_UTILISE, details={"email": ["Cette adresse e-mail est déjà utilisée."]}),
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Membre ou organisation inconnu"),
            EXEMPLE_RESERVE_ADMIN,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def modifier_membre(self, request, pk=None, membre_id=None):
        organisation = self.get_object()
        membre = organisation.membres.filter(pk=membre_id).first()
        if membre is None:
            raise ErreurMetier(CodeErreur.RESSOURCE_INTROUVABLE)
        entree = MembreModificationSerializer(data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        membre = services.modifier_membre(membre, **entree.validated_data)
        return reponse_succes(MembreOrganisationSerializer(membre).data, f"Compte de {membre.get_full_name()} modifié.")
