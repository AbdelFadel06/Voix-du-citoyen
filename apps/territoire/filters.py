import django_filters

from apps.core.communes import FiltreCommune
from apps.core.permissions import est_personnel_mairie

from .models import Quartier


class QuartierFilter(django_filters.FilterSet):
    arrondissement = django_filters.NumberFilter(
        field_name="arrondissement",
        help_text="Ne renvoyer que les quartiers de cet arrondissement (identifiant).",
    )

    commune = FiltreCommune(champ="arrondissement__commune")
    actif = django_filters.BooleanFilter(
        method="filtrer_actif",
        help_text="`false` : uniquement les quartiers désactivés. **Agents et admins uniquement** "
        "(les autres ne voient que les quartiers actifs).",
    )

    class Meta:
        model = Quartier
        fields = ["arrondissement", "actif", "commune"]

    def filtrer_actif(self, queryset, name, valeur):
        if valeur is None or not est_personnel_mairie(getattr(self.request, "user", None)):
            return queryset
        return queryset.filter(actif=valeur)
