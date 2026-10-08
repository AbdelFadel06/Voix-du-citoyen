"""
Permissions communes à toutes les apps.

Un ADMIN_MAIRIE peut tout ce que peut un AGENT : EstAgentMairie les accepte tous les deux.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Utilisateur

Role = Utilisateur.Role


def _a_le_role(utilisateur, *roles):
    return bool(utilisateur and utilisateur.is_authenticated and utilisateur.role in roles)


def organisation_habilitee(utilisateur):
    """Vrai si l'utilisateur est un compte organisation dont l'habilitation est active."""
    return (
        _a_le_role(utilisateur, Role.ORGANISATION)
        and utilisateur.organisation is not None
        and utilisateur.organisation.acces_autorise
    )


class EstCitoyen(BasePermission):
    message = "Action réservée aux citoyens."

    def has_permission(self, request, view):
        return _a_le_role(request.user, Role.CITOYEN)


class EstAgentMairie(BasePermission):
    message = "Action réservée aux agents de la mairie."

    def has_permission(self, request, view):
        return _a_le_role(request.user, Role.AGENT, Role.ADMIN_MAIRIE)


class EstAdminMairie(BasePermission):
    message = "Action réservée aux administrateurs de la mairie."

    def has_permission(self, request, view):
        return _a_le_role(request.user, Role.ADMIN_MAIRIE)


class EstCitoyenOuMairie(BasePermission):
    """Tout sauf les organisations (ex. suggestions, réservées aux citoyens et à la mairie)."""

    message = "Les suggestions sont réservées aux citoyens et à la mairie."

    def has_permission(self, request, view):
        return _a_le_role(request.user, Role.CITOYEN, Role.AGENT, Role.ADMIN_MAIRIE)


class EstOrganisationHabilitee(BasePermission):
    message = "Action réservée aux organisations habilitées."

    def has_permission(self, request, view):
        return organisation_habilitee(request.user)


class EstMairieOuOrganisation(BasePermission):
    """Agents, administrateurs mairie et organisations habilitées (ex. tableaux de bord)."""

    message = "Accès réservé à la mairie et aux organisations habilitées."

    def has_permission(self, request, view):
        return _a_le_role(request.user, Role.AGENT, Role.ADMIN_MAIRIE) or organisation_habilitee(
            request.user
        )


class LectureSeuleOrganisation(BasePermission):
    """Les organisations ne peuvent que consulter : toute écriture leur est refusée."""

    message = "Les organisations ont un accès en lecture seule."

    def has_permission(self, request, view):
        if _a_le_role(request.user, Role.ORGANISATION):
            return request.method in SAFE_METHODS
        return True


def est_personnel_mairie(utilisateur):
    """Agent ou admin mairie : seuls à voir l'auteur des dossiers et les données internes."""
    return _a_le_role(utilisateur, Role.AGENT, Role.ADMIN_MAIRIE)
