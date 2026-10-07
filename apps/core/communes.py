"""
Cloisonnement par commune (CLAUDE.md § 2).

La plateforme peut servir plusieurs communes. Chaque compte est rattaché à sa commune :
- **citoyen** : commune choisie à l'inscription ;
- **agent / admin mairie** : commune de sa mairie ;
- **admin de la plateforme** : admin sans commune, il voit toutes les communes ;
- **organisation** : aucune commune, elle peut intervenir partout.

Les citoyens, agents et admins rattachés à une commune ne voient et ne traitent que les
dossiers de leur commune. Les organisations et les admins de la plateforme voient toutes
les communes et peuvent filtrer avec `?commune=<id>`.
"""

import django_filters

from apps.accounts.models import Utilisateur

from .codes_erreur import CodeErreur
from .exceptions import ErreurMetier


def commune_imposee(utilisateur):
    """Identifiant de la commune à laquelle l'utilisateur est cloisonné, ou None (vision globale)."""
    if utilisateur is None or not utilisateur.is_authenticated:
        return None
    if utilisateur.role == Utilisateur.Role.ORGANISATION:
        return None
    return utilisateur.commune_id


def cloisonner(queryset, utilisateur, champ="commune"):
    """Restreint `queryset` à la commune de l'utilisateur, s'il y est cloisonné."""
    commune = commune_imposee(utilisateur)
    return queryset.filter(**{champ: commune}) if commune else queryset


class FiltreCommune(django_filters.NumberFilter):
    """
    Paramètre `?commune=<id>` des listes : utile aux organisations et aux admins de la
    plateforme ; ignoré pour les comptes cloisonnés à leur commune.
    """

    def __init__(self, champ="commune", **kwargs):
        kwargs.setdefault(
            "help_text",
            "Limiter à une commune (identifiant). Pour les organisations et les admins de la "
            "plateforme ; ignoré pour les autres comptes, qui ne voient que leur commune.",
        )
        super().__init__(field_name=champ, method=self.filtrer, **kwargs)

    def filtrer(self, queryset, name, valeur):
        utilisateur = getattr(self.parent.request, "user", None)
        if valeur is None or commune_imposee(utilisateur) is not None:
            return queryset
        return queryset.filter(**{self.field_name: valeur})


def commune_d_action(utilisateur, commune_demandee=None):
    """
    Commune d'une création par la mairie (service, agent, réalisation…) : celle de l'admin ;
    pour un admin de la plateforme, celle demandée, ou la seule commune existante.
    """
    from apps.territoire.models import Commune

    if utilisateur.commune_id:
        return utilisateur.commune
    if commune_demandee is not None:
        return commune_demandee
    communes = list(Commune.objects.all()[:2])
    if len(communes) == 1:
        return communes[0]
    raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details={"commune": ["Indiquez la commune."]})


def commune_de_l_auteur(utilisateur):
    """Commune d'un nouveau dossier (signalement, suggestion) : celle du compte, obligatoire."""
    if utilisateur.commune_id is None:
        raise ErreurMetier(CodeErreur.COMMUNE_NON_RENSEIGNEE)
    return utilisateur.commune


def controler_quartier(quartier, commune, champ="quartier"):
    """Le quartier choisi doit appartenir à la commune du dossier."""
    if quartier is not None and quartier.arrondissement.commune_id != commune.pk:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR,
            details={champ: [f"Ce quartier n'est pas dans la commune de {commune.nom}."]},
        )
