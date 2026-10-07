import django_filters

from .models import Secteur


class SecteurFilter(django_filters.FilterSet):
    pour_signalement = django_filters.BooleanFilter(
        help_text="`true` : uniquement les secteurs proposés pour un signalement."
    )
    pour_suggestion = django_filters.BooleanFilter(
        help_text="`true` : uniquement les secteurs proposés pour une suggestion."
    )
    pour_realisation = django_filters.BooleanFilter(
        help_text="`true` : uniquement les secteurs utilisés pour les réalisations."
    )

    class Meta:
        model = Secteur
        fields = ["pour_signalement", "pour_suggestion", "pour_realisation"]
