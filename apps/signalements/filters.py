import django_filters

from apps.core.communes import FiltreCommune
from apps.core.filters import FiltreChoix, FiltreIdentifiants

from .models import Signalement


class SignalementFilter(django_filters.FilterSet):
    statut = FiltreChoix(
        choices=Signalement.Statut.choices,
        help_text="Ne renvoyer que les signalements à ce(s) statut(s). Une ou plusieurs valeurs : `statut=SOUMIS&statut=RECU` ou `statut=SOUMIS,RECU`.",
    )
    secteur = FiltreIdentifiants(
        field_name="secteur", help_text="Identifiant du secteur. Une ou plusieurs valeurs : `secteur=1&secteur=3` ou `secteur=1,3`."
    )
    quartier = FiltreIdentifiants(
        field_name="quartier", help_text="Identifiant du quartier. Une ou plusieurs valeurs : `quartier=12&quartier=15` ou `quartier=12,15`."
    )
    date_debut = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__gte", help_text="Envoyés à partir de ce jour (AAAA-MM-JJ)."
    )
    date_fin = django_filters.DateFilter(
        field_name="cree_le", lookup_expr="date__lte", help_text="Envoyés jusqu'à ce jour inclus (AAAA-MM-JJ)."
    )
    commune = FiltreCommune()
    organisation = django_filters.NumberFilter(
        field_name="organisation_assignee",
        help_text="Signalements pris en charge par cette organisation (identifiant). Pour une "
        "organisation : son propre identifiant donne « mes dossiers ».",
    )
    pris_en_charge = django_filters.BooleanFilter(
        field_name="organisation_assignee",
        lookup_expr="isnull",
        exclude=True,
        help_text="`true` : déjà pris en charge par une organisation ; `false` : aucune organisation "
        "(ceux qu'une organisation peut encore prendre en charge, s'ils ne sont pas clos).",
    )

    modifie_depuis = django_filters.IsoDateTimeFilter(
        field_name="maj_le",
        lookup_expr="gte",
        help_text="Seulement les éléments créés ou modifiés depuis cet instant (ISO 8601, ex. "
        "`2026-10-27T09:00:00+01:00`) : pour une actualisation légère, ne récupérer que les changements.",
    )

    class Meta:
        model = Signalement
        fields = ["statut", "secteur", "quartier", "date_debut", "date_fin", "commune", "organisation", "pris_en_charge", "modifie_depuis"]
