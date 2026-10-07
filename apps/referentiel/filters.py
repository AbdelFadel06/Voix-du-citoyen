import django_filters

from apps.core.permissions import est_personnel_mairie

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

    actif = django_filters.BooleanFilter(
        method="filtrer_actif",
        help_text="`false` : uniquement les secteurs désactivés. **Agents et admins uniquement** "
        "(les autres ne voient que les secteurs actifs).",
    )

    class Meta:
        model = Secteur
        fields = ["pour_signalement", "pour_suggestion", "pour_realisation", "actif"]

    def filtrer_actif(self, queryset, name, valeur):
        if valeur is None or not est_personnel_mairie(getattr(self.request, "user", None)):
            return queryset
        return queryset.filter(actif=valeur)
