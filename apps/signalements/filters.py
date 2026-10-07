import django_filters

from apps.core.communes import FiltreCommune

from .models import Signalement


class SignalementFilter(django_filters.FilterSet):
    statut = django_filters.ChoiceFilter(
        choices=Signalement.Statut.choices, help_text="Ne renvoyer que les signalements à ce statut."
    )
    secteur = django_filters.NumberFilter(field_name="secteur", help_text="Identifiant du secteur.")
    quartier = django_filters.NumberFilter(field_name="quartier", help_text="Identifiant du quartier.")
    date_debut = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__gte", help_text="Envoyés à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__lte", help_text="Envoyés jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )
    commune = FiltreCommune()

    class Meta:
        model = Signalement
        fields = ["statut", "secteur", "quartier", "date_debut", "date_fin", "commune"]
