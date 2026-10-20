import django_filters

from apps.core.communes import FiltreCommune
from apps.accounts.models import Utilisateur
from apps.core.permissions import est_personnel_mairie

from .models import Realisation


class RealisationFilter(django_filters.FilterSet):
    statut = django_filters.ChoiceFilter(
        choices=Realisation.Statut.choices, help_text="Ne renvoyer que les réalisations à ce statut."
    )
    secteur = django_filters.NumberFilter(field_name="secteur", help_text="Identifiant du secteur.")
    quartier = django_filters.NumberFilter(
        field_name="quartiers", help_text="Identifiant d'un quartier concerné par la réalisation."
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

    class Meta:
        model = Realisation
        fields = ["statut", "secteur", "quartier", "date_debut", "date_fin", "publie", "commune", "organisation", "par_la_mairie"]

    def filtrer_publication(self, queryset, name, valeur):
        utilisateur = getattr(self.request, "user", None)
        organisation = getattr(utilisateur, "role", None) == Utilisateur.Role.ORGANISATION
        if valeur is None or not (est_personnel_mairie(utilisateur) or organisation):
            return queryset
        return queryset.filter(publie=valeur)
