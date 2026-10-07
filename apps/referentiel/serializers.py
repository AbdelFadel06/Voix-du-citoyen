from rest_framework import serializers

from .models import Secteur


class SecteurSerializer(serializers.ModelSerializer):
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
        ]
        extra_kwargs = {
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
