"""
Ce que chaque rôle voit d'un dossier citoyen (signalement, suggestion) — CLAUDE.md § 2.

- Identité de l'auteur : **personne** ne la voit, sauf l'auteur lui-même sur ses propres
  dossiers (ni la mairie, ni les autres citoyens, ni les organisations).
- Agents et admins mairie : champs internes et notes internes.
- Organisations : seulement les signalements de leurs secteurs d'intervention.
"""

from rest_framework import serializers

from apps.accounts.models import Utilisateur

from .permissions import est_personnel_mairie

ROLES_MAIRIE = (Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE)


def secteurs_autorises(utilisateur):
    """
    Secteurs d'intervention d'une organisation (liste d'identifiants, éventuellement vide),
    ou None pour les autres rôles, qui ne sont pas limités par secteur.
    """
    if getattr(utilisateur, "role", None) != Utilisateur.Role.ORGANISATION:
        return None
    if utilisateur.organisation_id is None:
        return []
    return list(utilisateur.organisation.secteurs.values_list("pk", flat=True))


def limiter_aux_secteurs(queryset, secteurs, champ="secteur"):
    """Applique `secteurs_autorises` (None : pas de limite ; liste vide : rien)."""
    return queryset if secteurs is None else queryset.filter(**{f"{champ}__in": secteurs})


def utilisateur_connecte(serializer):
    requete = serializer.context.get("request")
    return getattr(requete, "user", None)


class ChampsMairieMixin:
    """Retire `champs_mairie` de la réponse quand la personne connectée n'est pas de la mairie."""

    champs_mairie = ()

    def to_representation(self, instance):
        donnees = super().to_representation(instance)
        if not est_personnel_mairie(utilisateur_connecte(self)):
            for champ in self.champs_mairie:
                donnees.pop(champ, None)
        return donnees


class AuteurSerializer(serializers.Serializer):
    """Identité de l'auteur, envoyée **uniquement à l'auteur lui-même**."""

    nom_affiche = serializers.CharField(help_text="Prénom et initiale du nom, ex. « Afiavi H. ».")
    id = serializers.IntegerField(help_text="Identifiant du compte.")
    nom = serializers.CharField(help_text="Nom.")
    prenoms = serializers.CharField(help_text="Prénom(s).")
    telephone = serializers.CharField(help_text="Téléphone.")


def representer_auteur(dossier, viewer):
    """Identité de l'auteur si `viewer` est l'auteur ; None pour tous les autres, mairie comprise."""
    auteur = dossier.auteur
    if viewer is None or viewer.pk != auteur.pk:
        return None
    nom_affiche = f"{auteur.prenoms} {auteur.nom[:1]}.".strip()
    return {
        "nom_affiche": nom_affiche,
        "id": auteur.pk,
        "nom": auteur.nom,
        "prenoms": auteur.prenoms,
        "telephone": str(auteur.telephone),
    }


class SuiviSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    """Base des historiques (SuiviSignalement, SuiviSuggestion) : `Meta.model` à définir."""

    champs_mairie = ("auteur_nom", "visible_citoyen")

    par_la_mairie = serializers.SerializerMethodField(help_text="Vrai si l'événement vient de la mairie.")
    auteur_nom = serializers.SerializerMethodField(
        help_text="Nom de l'agent à l'origine de l'événement (agents et admins uniquement) ; `null` "
        "pour un événement du citoyen (ex. le dépôt), dont l'identité n'est jamais montrée."
    )

    class Meta:
        fields = [
            "id",
            "type_evenement",
            "ancien_statut",
            "nouveau_statut",
            "commentaire",
            "par_la_mairie",
            "auteur_nom",
            "visible_citoyen",
            "cree_le",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'événement."},
            "type_evenement": {"help_text": "Nature de l'événement."},
            "ancien_statut": {"help_text": "Statut avant le changement (vide sinon)."},
            "nouveau_statut": {"help_text": "Statut après le changement (vide sinon)."},
            "commentaire": {"help_text": "Message de la mairie ou motif du changement."},
            "visible_citoyen": {"help_text": "Visible par le citoyen (agents et admins uniquement)."},
            "cree_le": {"help_text": "Date de l'événement."},
        }

    def get_par_la_mairie(self, suivi) -> bool:
        return suivi.auteur.role in ROLES_MAIRIE

    def get_auteur_nom(self, suivi) -> str | None:
        if suivi.auteur.role not in ROLES_MAIRIE:
            return None  # le citoyen reste anonyme, y compris pour la mairie
        return f"{suivi.auteur.prenoms} {suivi.auteur.nom}".strip()
