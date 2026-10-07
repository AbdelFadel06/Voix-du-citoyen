import django_filters

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
    publie = django_filters.BooleanFilter(
        method="filtrer_publication",
        help_text="`false` : uniquement les brouillons. **Agents et admins uniquement** "
        "(les autres ne voient que les réalisations publiées).",
    )

    class Meta:
        model = Realisation
        fields = ["statut", "secteur", "quartier", "date_debut", "date_fin", "publie"]

    def filtrer_publication(self, queryset, name, valeur):
        if valeur is None or not est_personnel_mairie(getattr(self.request, "user", None)):
            return queryset
        return queryset.filter(publie=valeur)
