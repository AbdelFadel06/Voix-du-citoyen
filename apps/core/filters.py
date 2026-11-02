from django_filters.fields import BaseCSVField
from django_filters.filters import BaseInFilter, ChoiceFilter, NumberFilter
from django_filters.widgets import CSVWidget
from rest_framework.filters import OrderingFilter, SearchFilter


class Recherche(SearchFilter):
    """Recherche textuelle `?recherche=` (descriptions en français dans la doc)."""

    search_description = "Texte à rechercher (sans tenir compte des majuscules)."


class Tri(OrderingFilter):
    """Tri `?tri=champ` ou `?tri=-champ` pour l'ordre décroissant."""

    ordering_description = "Champ de tri ; préfixe `-` pour l'ordre décroissant."


# ---------------------------------------------------------------------------
# Filtres à plusieurs valeurs : `?secteur=1,3` ou `?secteur=1&secteur=3` (même écriture que les
# tableaux de bord). Une seule valeur fonctionne comme avant.
# ---------------------------------------------------------------------------


class _ListeWidget(CSVWidget):
    """Accepte le paramètre répété (`secteur=1&secteur=3`) en plus des virgules (`secteur=1,3`)."""

    def value_from_datadict(self, data, files, name):
        if name not in data:
            return None
        valeurs = data.getlist(name) if hasattr(data, "getlist") else [data.get(name)]
        morceaux = [m.strip() for v in valeurs if v for m in str(v).split(",") if m.strip()]
        return morceaux or None


class FiltreIdentifiants(BaseInFilter, NumberFilter):
    """Un ou plusieurs identifiants."""

    base_field_class = BaseCSVField

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lookup_expr", "in")
        kwargs.setdefault("widget", _ListeWidget)
        super().__init__(*args, **kwargs)


class FiltreChoix(BaseInFilter, ChoiceFilter):
    """Une ou plusieurs valeurs parmi les choix (ex. statuts)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("lookup_expr", "in")
        kwargs.setdefault("widget", _ListeWidget)
        super().__init__(*args, **kwargs)
