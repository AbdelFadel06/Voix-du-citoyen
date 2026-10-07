import django_filters

from .models import Quartier


class QuartierFilter(django_filters.FilterSet):
    arrondissement = django_filters.NumberFilter(
        field_name="arrondissement",
        help_text="Ne renvoyer que les quartiers de cet arrondissement (identifiant).",
    )

    class Meta:
        model = Quartier
        fields = ["arrondissement"]
