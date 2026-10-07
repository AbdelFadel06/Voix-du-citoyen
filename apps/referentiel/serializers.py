from rest_framework import serializers

from apps.accounts.models import ServiceMunicipal
from apps.accounts.serializers import ServiceResumeSerializer
from apps.core.visibilite import ChampsMairieMixin

from .models import Secteur


class SecteurSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    champs_mairie = ("actif", "service_par_defaut")

    service_par_defaut = ServiceResumeSerializer(
        allow_null=True,
        help_text="Service qui reçoit automatiquement les signalements de ce secteur "
        "(agents et admins uniquement).",
    )

    class Meta:
        model = Secteur
        fields = [
            "id",
            "nom",
            "code",
            "description",
            "icone",
            "couleur",
            "pour_signalement",
            "pour_suggestion",
            "pour_realisation",
            "ordre",
            "service_par_defaut",
            "actif",
        ]
        extra_kwargs = {
            "actif": {"help_text": "Faux si le secteur n'est plus proposé (agents et admins uniquement)."},
            "id": {"help_text": "Identifiant du secteur, à envoyer dans les signalements, suggestions…"},
            "nom": {"help_text": "Nom affiché du secteur."},
            "code": {"help_text": "Code stable du secteur (ex. `VOIRIE`), utilisable par les applications."},
            "description": {"help_text": "Description du secteur (peut être vide)."},
            "icone": {"help_text": "Nom de l'icône à afficher (peut être vide)."},
            "couleur": {"help_text": "Couleur d'affichage au format `#RRGGBB` (peut être vide)."},
            "pour_signalement": {"help_text": "Proposé lors d'un signalement."},
            "pour_suggestion": {"help_text": "Proposé lors d'une suggestion."},
            "pour_realisation": {"help_text": "Utilisé pour classer les réalisations de la mairie."},
            "ordre": {"help_text": "Ordre d'affichage (croissant)."},
        }


class SecteurResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Secteur
        fields = ["id", "nom", "code", "icone", "couleur"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant du secteur."},
            "nom": {"help_text": "Nom du secteur."},
            "code": {"help_text": "Code stable du secteur."},
            "icone": {"help_text": "Icône d'affichage."},
            "couleur": {"help_text": "Couleur d'affichage `#RRGGBB`."},
        }


class SecteurEcritureSerializer(serializers.ModelSerializer):
    """Création (`POST`) et modification partielle (`PATCH`) d'un secteur par un admin mairie."""

    service_par_defaut = serializers.PrimaryKeyRelatedField(
        queryset=ServiceMunicipal.objects.filter(actif=True),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce service n'existe pas ou n'est plus actif."},
        help_text="Identifiant du service qui recevra automatiquement les signalements de ce secteur.",
    )

    class Meta:
        model = Secteur
        fields = [
            "nom",
            "code",
            "description",
            "icone",
            "couleur",
            "pour_signalement",
            "pour_suggestion",
            "pour_realisation",
            "service_par_defaut",
            "ordre",
            "actif",
        ]
        extra_kwargs = {
            "nom": {"help_text": "Nom affiché, unique."},
            "code": {"help_text": "Code court et stable, unique (ex. `VOIRIE`)."},
            "description": {"help_text": "Description (facultative)."},
            "icone": {"help_text": "Nom de l'icône (facultatif)."},
            "couleur": {"help_text": "Couleur `#RRGGBB` (facultative)."},
            "pour_signalement": {"help_text": "Proposer ce secteur lors d'un signalement (`false` par défaut)."},
            "pour_suggestion": {"help_text": "Proposer ce secteur lors d'une suggestion (`false` par défaut)."},
            "pour_realisation": {"help_text": "Utiliser ce secteur pour les réalisations (`false` par défaut)."},
            "ordre": {"help_text": "Ordre d'affichage (0 par défaut)."},
            "actif": {"help_text": "`false` pour ne plus le proposer (rien n'est supprimé)."},
        }

    def validate_code(self, valeur):
        return valeur.strip().upper()
