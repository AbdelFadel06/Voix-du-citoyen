from rest_framework import serializers

from apps.accounts.models import Appareil

from .models import Notification


class AppareilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appareil
        fields = ["token_fcm", "plateforme", "actif"]
        read_only_fields = ["actif"]
        extra_kwargs = {
            # L'unicité est gérée par le service (un jeton peut changer de compte).
            "token_fcm": {"validators": [], "help_text": "Jeton d'enregistrement Firebase (FCM) de l'appareil."},
            "plateforme": {"help_text": "Système de l'appareil : `ANDROID` ou `IOS`."},
            "actif": {"help_text": "Vrai tant que l'appareil reçoit les notifications."},
        }


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "titre", "message", "cible_type", "cible_id", "lu", "cree_le"]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant de la notification (pour `/notifications/{id}/lu/`)."},
            "type": {"help_text": "Nature de l'événement."},
            "titre": {"help_text": "Titre court à afficher."},
            "message": {"help_text": "Texte de la notification."},
            "cible_type": {
                "help_text": "Écran à ouvrir : `signalement`, `suggestion` ou `realisation`."
            },
            "cible_id": {"help_text": "Identifiant de l'élément à ouvrir (ex. `/signalements/{cible_id}/`)."},
            "lu": {"help_text": "Vrai une fois la notification lue."},
            "cree_le": {"help_text": "Date de la notification."},
        }


class ToutLuSerializer(serializers.Serializer):
    nb_marquees = serializers.IntegerField(help_text="Nombre de notifications qui viennent d'être marquées lues.")
