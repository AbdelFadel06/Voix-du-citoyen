"""Organisations partenaires et statistiques de leur périmètre (consultation par la mairie)."""

import django_filters
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import FiltreCommune, commune_imposee
from apps.core.exceptions import ErreurMetier
from apps.core.filters import Recherche
from apps.core.permissions import EstAgentMairie
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_ADMINISTRATION,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_succes,
    parametre_id,
)

from . import exemples
from .models import Organisation
from .serializers import OrganisationDetailSerializer, OrganisationListeSerializer
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
EXEMPLE_RESERVE_MAIRIE = exemple_erreur(
    CodeErreur.PERMISSION_REFUSEE, "Action réservée aux agents de la mairie.", nom="Réservé à la mairie"
)
STATISTIQUES = """
**Statistiques** : les signalements du **périmètre** de l'organisation (ses communes
d'intervention × ses secteurs d'intervention), c'est-à-dire ceux qu'elle voit, et la façon dont
la mairie les a traités : en attente (`SOUMIS`), en cours (reçus ou en traitement), résolus,
rejetés, taux de résolution et délai moyen de résolution. Période : `date_debut`, `date_fin`
(date d'envoi des signalements). La **mairie d'une commune** ne voit que les organisations qui
interviennent chez elle, avec des chiffres **limités à sa commune** ; l'**admin de la
plateforme** voit toutes les organisations, toutes communes confondues (ou une seule avec
`?commune=`).

**Connecté** : agents et admins mairie. La création, la modification et la suspension des
organisations se font dans l'administration Django.
"""


@extend_schema_view(
    list=extend_schema(
        tags=[TAG_ADMINISTRATION],
        summary="Lister les organisations et leurs statistiques",
        description=f"""
Liste **paginée** des organisations partenaires (ONG, OSC…), triées par nom, avec leur périmètre
d'intervention, leur état d'habilitation, leurs comptes actifs et leurs chiffres clés.

**Filtres** : `commune`, `secteur`, `type`, `statut_habilitation` ; **recherche** : nom, sigle.
{STATISTIQUES}""",
        responses={200: OrganisationListeSerializer(many=True), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_element_liste("Organisation", exemples.ORGANISATION_LISTE),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"date_fin": ["La date de fin doit suivre la date de début."]},
                nom="Dates incohérentes",
            ),
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
{STATISTIQUES}""",
        parameters=[ID_ORGANISATION],
        responses={200: enveloppe(OrganisationDetailSerializer), **erreurs(400, 401, 403, 404)},
        examples=[
            exemple_succes("Organisation", exemples.ORGANISATION_DETAIL),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"date_fin": ["La date de fin doit suivre la date de début."]},
                nom="Dates incohérentes",
            ),
            EXEMPLE_RESERVE_MAIRIE,
            exemple_erreur(CodeErreur.RESSOURCE_INTROUVABLE, nom="Organisation inconnue"),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class OrganisationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, EstAgentMairie]
    serializer_class = OrganisationListeSerializer
    filter_backends = [DjangoFilterBackend, Recherche]
    filterset_class = OrganisationFilter
    search_fields = ["nom", "sigle"]

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

    def list(self, request, *args, **kwargs):
        organisations = list(self.paginate_queryset(self.filter_queryset(self.get_queryset())))
        contexte = {
            **self.get_serializer_context(),
            "statistiques": statistiques(organisations, **self._parametres_statistiques()),
        }
        return self.get_paginated_response(OrganisationListeSerializer(organisations, many=True, context=contexte).data)

    def retrieve(self, request, *args, **kwargs):
        organisation = self.get_object()
        contexte = {
            **self.get_serializer_context(),
            "statistiques": statistiques([organisation], details=True, **self._parametres_statistiques()),
        }
        return reponse_succes(OrganisationDetailSerializer(organisation, context=contexte).data)
