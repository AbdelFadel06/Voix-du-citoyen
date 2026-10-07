from rest_framework import serializers

from .models import Arrondissement, Quartier


class ArrondissementResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arrondissement
        fields = ["id", "nom"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'arrondissement (filtre `?arrondissement=`)."},
            "nom": {"help_text": "Nom de l'arrondissement."},
        }


class QuartierSerializer(serializers.ModelSerializer):
    arrondissement = ArrondissementResumeSerializer(
        read_only=True, help_text="Arrondissement auquel appartient le quartier."
    )

    class Meta:
        model = Quartier
        fields = ["id", "nom", "code", "arrondissement", "latitude_centre", "longitude_centre"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant du quartier, à envoyer dans les signalements."},
            "nom": {"help_text": "Nom du quartier."},
            "code": {"help_text": "Code administratif du quartier (peut être vide)."},
            "latitude_centre": {
                "help_text": "Latitude du centre du quartier (degrés décimaux), ou `null` si inconnue."
            },
            "longitude_centre": {
                "help_text": "Longitude du centre du quartier (degrés décimaux), ou `null` si inconnue."
            },
        }


class PositionSerializer(serializers.Serializer):
    lat = serializers.FloatField(
        min_value=-90, max_value=90, help_text="Latitude de la position, en degrés décimaux (ex. `6.4012`)."
    )
    lng = serializers.FloatField(
        min_value=-180,
        max_value=180,
        help_text="Longitude de la position, en degrés décimaux (ex. `2.3415`).",
    )


class QuartierProcheSerializer(serializers.Serializer):
    quartier = QuartierSerializer(help_text="Quartier proposé, à faire confirmer par le citoyen.")
    distance_metres = serializers.IntegerField(
        help_text="Distance à vol d'oiseau entre la position et le centre du quartier, en mètres."
    )


class QuartierResumeSerializer(serializers.ModelSerializer):
    arrondissement = serializers.CharField(source="arrondissement.nom", help_text="Nom de l'arrondissement.")

    class Meta:
        model = Quartier
        fields = ["id", "nom", "arrondissement"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant du quartier."},
            "nom": {"help_text": "Nom du quartier."},
        }
