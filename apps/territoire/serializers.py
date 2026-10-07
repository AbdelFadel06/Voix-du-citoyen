from rest_framework import serializers

from apps.core.serializers import BilanImportSerializer, ImportCSVSerializer
from apps.core.visibilite import ChampsMairieMixin

from .models import Arrondissement, Commune, Quartier


class CommuneResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commune
        fields = ["id", "nom"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de la commune."},
            "nom": {"help_text": "Nom de la commune."},
        }


class ArrondissementResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Arrondissement
        fields = ["id", "nom"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'arrondissement (filtre `?arrondissement=`)."},
            "nom": {"help_text": "Nom de l'arrondissement."},
        }


class QuartierSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    champs_mairie = ("actif",)

    arrondissement = ArrondissementResumeSerializer(
        read_only=True, help_text="Arrondissement auquel appartient le quartier."
    )

    class Meta:
        model = Quartier
        fields = ["id", "nom", "code", "arrondissement", "latitude_centre", "longitude_centre", "actif"]
        extra_kwargs = {
            "actif": {"help_text": "Faux si le quartier n'est plus proposé (agents et admins uniquement)."},
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


# ---------------------------------------------------------------------------
# Administration (admins mairie)
# ---------------------------------------------------------------------------


def commune_par_defaut():
    """La plateforme sert une seule commune : elle est choisie quand rien n'est précisé."""
    communes = list(Commune.objects.all()[:2])
    return communes[0] if len(communes) == 1 else None


class CommuneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commune
        fields = ["id", "nom", "code", "departement", "lat_min", "lat_max", "lng_min", "lng_max"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de la commune."},
            "nom": {"help_text": "Nom de la commune, ex. « Parakou »."},
            "code": {"help_text": "Code court et unique, ex. `PKO`."},
            "departement": {"help_text": "Département, ex. « Borgou »."},
            "lat_min": {"help_text": "Latitude la plus au sud de la commune (emprise GPS)."},
            "lat_max": {"help_text": "Latitude la plus au nord de la commune."},
            "lng_min": {"help_text": "Longitude la plus à l'ouest de la commune."},
            "lng_max": {"help_text": "Longitude la plus à l'est de la commune."},
        }

    def validate(self, attrs):
        valeur = lambda champ: attrs.get(champ, getattr(self.instance, champ, None))  # noqa: E731
        erreurs = {}
        for minimum, maximum in (("lat_min", "lat_max"), ("lng_min", "lng_max")):
            if valeur(minimum) is not None and valeur(maximum) is not None and valeur(minimum) >= valeur(maximum):
                erreurs[maximum] = [f"Doit être supérieur à {minimum}."]
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return attrs


class ArrondissementSerializer(serializers.ModelSerializer):
    commune = serializers.PrimaryKeyRelatedField(
        queryset=Commune.objects.all(),
        required=False,
        error_messages={"does_not_exist": "Cette commune n'existe pas."},
        help_text="Commune de l'arrondissement. Uniquement pour un admin de la plateforme (facultatif "
        "s'il n'existe qu'une commune) ; sinon c'est la commune de l'admin connecté.",
    )

    class Meta:
        model = Arrondissement
        fields = ["id", "commune", "nom", "code"]
        validators = []  # unicité (commune, nom) vérifiée ci-dessous avec un message clair
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'arrondissement."},
            "nom": {"help_text": "Nom de l'arrondissement, unique dans la commune."},
            "code": {"help_text": "Code de l'arrondissement (facultatif).", "required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        from apps.core.communes import commune_d_action

        if self.instance is not None:
            commune = self.instance.commune
        else:
            commune = commune_d_action(self.context["request"].user, attrs.get("commune"))
        attrs["commune"] = commune
        nom = attrs.get("nom", getattr(self.instance, "nom", ""))
        doublons = Arrondissement.objects.filter(commune=commune, nom__iexact=nom)
        if self.instance:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise serializers.ValidationError({"nom": ["Cet arrondissement existe déjà dans cette commune."]})
        return attrs


class QuartierEcritureSerializer(serializers.ModelSerializer):
    """Création (`POST`) et modification partielle (`PATCH`) d'un quartier par un admin mairie."""

    arrondissement = serializers.PrimaryKeyRelatedField(
        queryset=Arrondissement.objects.select_related("commune"),
        error_messages={"does_not_exist": "Cet arrondissement n'existe pas."},
        help_text="Identifiant de l'arrondissement (`GET /arrondissements/`).",
    )

    class Meta:
        model = Quartier
        fields = ["arrondissement", "nom", "code", "latitude_centre", "longitude_centre", "actif"]
        validators = []  # unicité (arrondissement, nom) vérifiée ci-dessous avec un message clair
        extra_kwargs = {
            "nom": {"help_text": "Nom du quartier, unique dans l'arrondissement."},
            "code": {"help_text": "Code du quartier (facultatif).", "required": False, "allow_blank": True},
            "latitude_centre": {"help_text": "Latitude du centre (facultative, avec `longitude_centre`)."},
            "longitude_centre": {"help_text": "Longitude du centre (facultative, avec `latitude_centre`)."},
            "actif": {"help_text": "`false` pour ne plus le proposer (rien n'est supprimé)."},
        }

    def validate(self, attrs):
        from apps.core.communes import commune_imposee

        valeur = lambda champ: attrs.get(champ, getattr(self.instance, champ, None))  # noqa: E731
        arrondissement, nom = valeur("arrondissement"), valeur("nom")
        latitude, longitude = valeur("latitude_centre"), valeur("longitude_centre")
        erreurs = {}
        commune_admin = commune_imposee(self.context["request"].user)
        if commune_admin and arrondissement.commune_id != commune_admin:
            raise serializers.ValidationError({"arrondissement": ["Cet arrondissement n'est pas dans votre commune."]})
        if (latitude is None) != (longitude is None):
            erreurs["latitude_centre"] = ["La latitude et la longitude du centre vont ensemble."]
        elif latitude is not None and not arrondissement.commune.contient(latitude, longitude):
            erreurs["latitude_centre"] = [f"Ce point est hors de l'emprise de {arrondissement.commune.nom}."]
        doublons = Quartier.objects.filter(arrondissement=arrondissement, nom__iexact=nom)
        if self.instance:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            erreurs["nom"] = ["Ce quartier existe déjà dans cet arrondissement."]
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return attrs


class ImportCommuneMixin(serializers.Serializer):
    commune = serializers.PrimaryKeyRelatedField(
        queryset=Commune.objects.all(),
        required=False,
        error_messages={"does_not_exist": "Cette commune n'existe pas."},
        help_text="Commune concernée. Uniquement pour un admin de la plateforme (facultatif s'il "
        "n'existe qu'une commune) ; sinon c'est la commune de l'admin connecté.",
    )


class ImportQuartiersSerializer(ImportCommuneMixin, ImportCSVSerializer):
    pass


class BilanImportQuartiersSerializer(BilanImportSerializer):
    arrondissements_crees = serializers.IntegerField(help_text="Arrondissements créés au passage.")
