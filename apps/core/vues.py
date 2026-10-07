"""Base des vues de gestion du référentiel (commune, quartiers, services, agents…)."""

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated

from .permissions import EstAdminMairie
from .reponses import reponse_succes


class PermissionsAdministration:
    """Lecture selon `permission_lecture`, écriture (création, modification, import) : admins mairie."""

    permission_lecture = IsAuthenticated

    def get_permissions(self):
        if self.action in ("create", "partial_update", "importer"):
            return [IsAuthenticated(), EstAdminMairie()]
        return [IsAuthenticated(), self.permission_lecture()]


class VueAdministration(
    PermissionsAdministration,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Base des vues de gestion : messages de confirmation et réponse avec le serializer de lecture."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    pagination_class = None
    serializer_lecture = None
    libelle = "Élément"

    def _lecture(self, objet):
        return self.serializer_lecture(objet, context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        entree = self.get_serializer(data=request.data)
        entree.is_valid(raise_exception=True)
        objet = entree.save()
        return reponse_succes(self._lecture(objet), f"{self.libelle} « {objet.nom} » créé.", status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        entree = self.get_serializer(self.get_object(), data=request.data, partial=True)
        entree.is_valid(raise_exception=True)
        objet = entree.save()
        return reponse_succes(self._lecture(objet), f"{self.libelle} « {objet.nom} » modifié.")
