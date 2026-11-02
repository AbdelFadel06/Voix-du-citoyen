import django_filters

from apps.core.communes import FiltreCommune
from apps.core.filters import FiltreChoix, FiltreIdentifiants
from apps.accounts.models import Utilisateur
from apps.core.permissions import est_personnel_mairie

from .models import Realisation


class RealisationFilter(django_filters.FilterSet):
    statut = FiltreChoix(
        choices=Realisation.Statut.choices,
        help_text="Ne renvoyer que les réalisations à ce(s) statut(s). Une ou plusieurs valeurs : `statut=PLANIFIEE&statut=EN_COURS` ou `statut=PLANIFIEE,EN_COURS`.",
    )
    secteur = FiltreIdentifiants(
        field_name="secteur", help_text="Identifiant du secteur. Une ou plusieurs valeurs : `secteur=1&secteur=3` ou `secteur=1,3`."
    )
    quartier = FiltreIdentifiants(
        field_name="quartiers",
        distinct=True,  # une réalisation dans deux des quartiers demandés n'apparaît qu'une fois
        help_text="Identifiant d'un quartier concerné par la réalisation. Une ou plusieurs valeurs : `quartier=12&quartier=15` ou `quartier=12,15`.",
    )
    date_debut = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__gte", help_text="Créées à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__lte", help_text="Créées jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )
    commune = FiltreCommune()
    publie = django_filters.BooleanFilter(
        method="filtrer_publication",
        help_text="`false` : uniquement les brouillons (ceux de la mairie pour un agent, ceux de son "
        "organisation pour une organisation). Ignoré pour les autres, qui ne voient que les publiées.",
    )
    organisation = django_filters.NumberFilter(
        field_name="organisation", help_text="Réalisations de cette organisation (identifiant)."
    )
    par_la_mairie = django_filters.BooleanFilter(
        field_name="organisation",
        lookup_expr="isnull",
        help_text="`true` : réalisations de la mairie ; `false` : réalisations des organisations.",
    )

    modifie_depuis = django_filters.IsoDateTimeFilter(
        field_name="maj_le",
        lookup_expr="gte",
        help_text="Seulement les éléments créés ou modifiés depuis cet instant (ISO 8601, ex. "
        "`2026-10-27T09:00:00+01:00`) : pour une actualisation légère, ne récupérer que les changements.",
    )

    class Meta:
        model = Realisation
        fields = ["statut", "secteur", "quartier", "date_debut", "date_fin", "publie", "commune", "organisation", "par_la_mairie", "modifie_depuis"]

    def filtrer_publication(self, queryset, name, valeur):
        utilisateur = getattr(self.request, "user", None)
        organisation = getattr(utilisateur, "role", None) == Utilisateur.Role.ORGANISATION
        if valeur is None or not (est_personnel_mairie(utilisateur) or organisation):
            return queryset
        return queryset.filter(publie=valeur)
