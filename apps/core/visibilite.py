"""
Ce que chaque rôle voit d'un dossier citoyen (signalement, suggestion) — CLAUDE.md § 2.

- Agents et admins mairie : tout (identité de l'auteur, champs internes, notes internes).
- L'auteur : sa propre identité complète.
- Autres citoyens : « Prénom N. », ou rien si le dossier est anonyme.
- Organisations : jamais l'auteur.
"""

from rest_framework import serializers

from apps.accounts.models import Utilisateur

from .permissions import est_personnel_mairie

ROLES_MAIRIE = (Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE)


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
    """`nom_affiche` pour le public ; identité complète pour la mairie et l'auteur lui-même."""

    nom_affiche = serializers.CharField(help_text="Prénom et initiale du nom, ex. « Afiavi H. ».")
    id = serializers.IntegerField(allow_null=True, help_text="Identifiant (mairie et auteur uniquement).")
    nom = serializers.CharField(allow_null=True, help_text="Nom (mairie et auteur uniquement).")
    prenoms = serializers.CharField(allow_null=True, help_text="Prénom(s) (mairie et auteur uniquement).")
    telephone = serializers.CharField(allow_null=True, help_text="Téléphone (mairie et auteur uniquement).")


def representer_auteur(dossier, viewer):
    """Auteur de `dossier` tel que `viewer` a le droit de le voir (ou None)."""
    auteur = dossier.auteur
    complet = est_personnel_mairie(viewer) or (viewer is not None and viewer.pk == auteur.pk)
    if not complet:
        anonyme = getattr(dossier, "anonyme", False)
        if viewer is None or viewer.role == Utilisateur.Role.ORGANISATION or anonyme:
            return None
    nom_affiche = f"{auteur.prenoms} {auteur.nom[:1]}.".strip()
    if not complet:
        return {"nom_affiche": nom_affiche, "id": None, "nom": None, "prenoms": None, "telephone": None}
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
        help_text="Nom de la personne à l'origine de l'événement (agents et admins uniquement)."
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

    def get_auteur_nom(self, suivi) -> str:
        return f"{suivi.auteur.prenoms} {suivi.auteur.nom}".strip()
