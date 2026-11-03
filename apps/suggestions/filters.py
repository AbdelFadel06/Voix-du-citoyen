import django_filters

from apps.core.communes import FiltreCommune
from apps.core.filters import FiltreIdentifiants
from apps.core.permissions import est_personnel_mairie

from .models import Suggestion


class SuggestionFilter(django_filters.FilterSet):
    secteur = FiltreIdentifiants(
        field_name="secteur", help_text="Identifiant du secteur. Une ou plusieurs valeurs : `secteur=1&secteur=3` ou `secteur=1,3`."
    )
    quartier = FiltreIdentifiants(
        field_name="quartier",
        help_text="Identifiant du quartier (les suggestions pour toute la commune ne sont pas incluses)."
        " Une ou plusieurs valeurs : `quartier=12&quartier=15` ou `quartier=12,15`.",
    )
    date_debut = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__gte", help_text="Envoyées à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__lte", help_text="Envoyées jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )
    commune = FiltreCommune()
    est_pertinente = django_filters.ChoiceFilter(
        choices=[("true", "Pertinentes"), ("false", "Non pertinentes"), ("null", "Pas encore évaluées")],
        method="filtrer_pertinence",
        help_text="`true` : marquées pertinentes ; `false` : marquées non pertinentes ; `null` : pas encore "
        "évaluées. **Agents et admins uniquement** (ignoré pour les autres rôles).",
    )

    modifie_depuis = django_filters.IsoDateTimeFilter(
        field_name="maj_le",
        lookup_expr="gte",
        help_text="Seulement les éléments créés ou modifiés depuis cet instant (ISO 8601, ex. "
        "`2026-10-27T09:00:00+01:00`) : pour une actualisation légère, ne récupérer que les changements.",
    )

    class Meta:
        model = Suggestion
        fields = ["secteur", "quartier", "date_debut", "date_fin", "est_pertinente", "commune", "modifie_depuis"]

    def filtrer_pertinence(self, queryset, name, valeur):
        # Ignoré hors mairie : un citoyen ne doit pas pouvoir deviner les suggestions cochées.
        if not valeur or not est_personnel_mairie(getattr(self.request, "user", None)):
            return queryset
        return queryset.filter(est_pertinente={"true": True, "false": False, "null": None}[valeur])
