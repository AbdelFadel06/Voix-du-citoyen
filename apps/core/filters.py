from rest_framework.filters import OrderingFilter, SearchFilter


class Recherche(SearchFilter):
    """Recherche textuelle `?recherche=` (descriptions en français dans la doc)."""

    search_description = "Texte à rechercher (sans tenir compte des majuscules)."


class Tri(OrderingFilter):
    """Tri `?tri=champ` ou `?tri=-champ` pour l'ordre décroissant."""

    ordering_description = "Champ de tri ; préfixe `-` pour l'ordre décroissant."
