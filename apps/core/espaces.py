"""
Espaces d'adresses de l'API.

- **Espace mairie** (`/api/v1/mairie/…`) : réservé aux agents et admins d'une mairie (et aux
  institutions IBDC, dont le compte technique est un admin mairie). Leur commune vient
  toujours du jeton ou de la clé : aucun paramètre `commune` n'y est proposé.
- **Routes générales** (`/api/v1/…`) : citoyens, organisations et admin de la plateforme
  (compte mairie sans commune). La mairie d'une commune y est refusée
  (`ESPACE_MAIRIE_REQUIS`) pour les volets qui ont leur équivalent dans l'espace mairie.

Les deux espaces servent les mêmes vues : `garder` en fait une copie précédée d'une
permission (`EspaceMairie` ou `HorsEspaceMairie`), sans toucher au reste des règles.
"""

from django.urls import URLPattern
from rest_framework.permissions import BasePermission

from apps.accounts.models import Utilisateur

from .codes_erreur import CodeErreur
from .exceptions import ErreurMetier


def est_mairie_de_commune(utilisateur):
    """Agent ou admin rattaché à une commune (l'admin de la plateforme n'en a pas)."""
    return bool(
        utilisateur
        and utilisateur.is_authenticated
        and utilisateur.role in (Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE)
        and utilisateur.commune_id
    )


class EspaceMairie(BasePermission):
    message = "Espace réservé aux agents et administrateurs d'une mairie."

    def has_permission(self, request, view):
        return est_mairie_de_commune(request.user)


class HorsEspaceMairie(BasePermission):
    def has_permission(self, request, view):
        if est_mairie_de_commune(request.user):
            raise ErreurMetier(CodeErreur.ESPACE_MAIRIE_REQUIS)
        return True


def _sans_filtre_commune(filterset_class):
    """Copie du jeu de filtres sans `commune` (la commune de la mairie vient de son compte)."""
    if filterset_class is None or "commune" not in filterset_class.base_filters:
        return filterset_class
    copie = type(filterset_class.__name__, (filterset_class,), {})
    copie.base_filters = {nom: f for nom, f in filterset_class.base_filters.items() if nom != "commune"}
    return copie


def _vue_gardee(callback, garde, espace_mairie, actions=None):
    classe = callback.cls

    def get_permissions(self):
        return [garde(), *super(copie, self).get_permissions()]

    attributs = {"get_permissions": get_permissions, "__module__": classe.__module__}
    if espace_mairie:
        attributs["filterset_class"] = _sans_filtre_commune(getattr(classe, "filterset_class", None))
    copie = type(classe.__name__, (classe,), attributs)
    actions = actions if actions is not None else getattr(callback, "actions", None)
    if actions is not None:  # ViewSet
        return copie.as_view(actions, **callback.initkwargs)
    return copie.as_view(**callback.initkwargs)


def garder(urlpatterns, garde, *, espace_mairie=False, selection=lambda motif: True, actions_exclues=()):
    """
    Copie de `urlpatterns` où chaque vue retenue par `selection` est précédée de `garde`.
    Dans l'espace mairie, les autres vues sont retirées, ainsi que les actions de ViewSet
    `actions_exclues` (réservées aux citoyens ou aux organisations) ; ailleurs, elles restent
    telles quelles.
    """
    resultat = []
    for motif in urlpatterns:
        if not selection(motif):
            if not espace_mairie:
                resultat.append(motif)
            continue
        actions = getattr(motif.callback, "actions", None)
        if espace_mairie and actions is not None:
            actions = {methode: nom for methode, nom in actions.items() if nom not in actions_exclues}
            if not actions:
                continue
        vue = _vue_gardee(motif.callback, garde, espace_mairie, actions)
        resultat.append(URLPattern(motif.pattern, vue, motif.default_args, motif.name))
    return resultat
