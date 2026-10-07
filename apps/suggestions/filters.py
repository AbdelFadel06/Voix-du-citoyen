import django_filters

from apps.core.communes import FiltreCommune
from apps.core.permissions import est_personnel_mairie

from .models import Suggestion


class SuggestionFilter(django_filters.FilterSet):
    secteur = django_filters.NumberFilter(field_name="secteur", help_text="Identifiant du secteur.")
    quartier = django_filters.NumberFilter(
        field_name="quartier",
        help_text="Identifiant du quartier (les suggestions pour toute la commune ne sont pas incluses).",
    )
    date_debut = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__gte", help_text="Envoyées à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__lte", help_text="Envoyées jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )
    commune = FiltreCommune()
    est_pertinente = django_filters.BooleanFilter(
        method="filtrer_pertinence",
        help_text="`true` : uniquement les suggestions cochées « pertinentes » par la mairie. "
        "**Agents et admins uniquement** (ignoré pour les autres rôles).",
    )

    class Meta:
        model = Suggestion
        fields = ["secteur", "quartier", "date_debut", "date_fin", "est_pertinente", "commune"]

    def filtrer_pertinence(self, queryset, name, valeur):
        # Ignoré hors mairie : un citoyen ne doit pas pouvoir deviner les suggestions cochées.
        if valeur is None or not est_personnel_mairie(getattr(self.request, "user", None)):
            return queryset
        return queryset.filter(est_pertinente=valeur)
