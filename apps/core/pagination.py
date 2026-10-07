from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .reponses import corps_succes


class PaginationStandard(PageNumberPagination):
    """Pagination par numéro de page ; la taille se règle avec `?taille=`."""

    page_size = 20
    page_size_query_param = "taille"
    max_page_size = 100
    page_query_description = "Numéro de la page, à partir de 1."
    page_size_query_description = "Nombre d'éléments par page (20 par défaut, 100 au maximum)."

    def get_paginated_response(self, data):
        corps = corps_succes(data)
        corps["pagination"] = {
            "total": self.page.paginator.count,
            "page": self.page.number,
            "pages": self.page.paginator.num_pages,
            "taille": self.page.paginator.per_page,
            "suivant": self.get_next_link(),
            "precedent": self.get_previous_link(),
        }
        return Response(corps)

    def get_paginated_response_schema(self, schema):
        lien = {"type": "string", "format": "uri", "nullable": True}
        entier = {"type": "integer"}
        return {
            "type": "object",
            "required": ["succes", "message", "donnees", "pagination"],
            "properties": {
                "succes": {"type": "boolean", "example": True, "description": "Toujours `true`."},
                "message": {"type": "string", "nullable": True, "example": None, "description": "Toujours `null` pour une liste."},
                # drf-spectacular passe un marqueur (pas un dict) pour construire les exemples.
                "donnees": {**schema, "description": "Éléments de la page demandée."}
                if isinstance(schema, dict)
                else schema,
                "pagination": {
                    "description": "Position dans la liste paginée.",
                    "type": "object",
                    "required": ["total", "page", "pages", "taille", "suivant", "precedent"],
                    "properties": {
                        "total": {**entier, "example": 134, "description": "Nombre total d'éléments."},
                        "page": {**entier, "example": 2, "description": "Numéro de la page renvoyée."},
                        "pages": {**entier, "example": 7, "description": "Nombre total de pages."},
                        "taille": {**entier, "example": 20, "description": "Nombre d'éléments par page."},
                        "suivant": {
                            **lien,
                            "description": "Adresse de la page suivante, ou `null` sur la dernière.",
                            "example": "https://api.exemple.bj/api/v1/signalements/?page=3",
                        },
                        "precedent": {
                            **lien,
                            "description": "Adresse de la page précédente, ou `null` sur la première.",
                            "example": "https://api.exemple.bj/api/v1/signalements/?page=1",
                        },
                    },
                },
            },
        }
