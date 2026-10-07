from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import AgentResumeSerializer
from apps.core.visibilite import ChampsMairieMixin
from apps.medias.serializers import MediaResumeSerializer, MediaSerializer
from apps.referentiel.models import Secteur
from apps.referentiel.serializers import SecteurResumeSerializer
from apps.signalements.models import Signalement
from apps.signalements.serializers import SignalementResumeSerializer
from apps.suggestions.models import Suggestion
from apps.territoire.models import Quartier
from apps.territoire.serializers import QuartierResumeSerializer

from .models import Realisation, RealisationMedia

MAX_BUDGET = 10**14 - 1


class SuggestionResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Suggestion
        fields = ["id", "reference", "titre"]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant de la suggestion."},
            "reference": {"help_text": "Référence de la suggestion."},
            "titre": {"help_text": "Titre de la suggestion."},
        }


class RealisationMediaSerializer(serializers.ModelSerializer):
    media = MediaSerializer(help_text="Fichier complet (photo ou vidéo).")

    class Meta:
        model = RealisationMedia
        fields = ["phase", "legende", "ordre", "media"]
        read_only_fields = fields
        extra_kwargs = {
            "phase": {"help_text": "Moment du chantier : avant, pendant ou après les travaux."},
            "legende": {"help_text": "Légende de la photo (peut être vide)."},
            "ordre": {"help_text": "Ordre d'affichage (croissant)."},
        }


class CouvertureSerializer(serializers.Serializer):
    phase = serializers.CharField(help_text="Phase du chantier de cette photo.")
    media = MediaResumeSerializer(help_text="Aperçu (miniature uniquement).")


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


class RealisationListSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    champs_mairie = ("publie",)

    secteur = SecteurResumeSerializer(help_text="Secteur de la réalisation.")
    quartiers = QuartierResumeSerializer(many=True, help_text="Quartiers concernés.")
    couverture = serializers.SerializerMethodField(
        help_text="Première photo ou vidéo (miniature), ou `null` s'il n'y en a pas."
    )
    nb_medias = serializers.SerializerMethodField(help_text="Nombre de photos et vidéos.")

    class Meta:
        model = Realisation
        fields = [
            "id",
            "reference",
            "titre",
            "secteur",
            "statut",
            "taux_avancement",
            "quartiers",
            "date_debut_prevue",
            "date_fin_prevue",
            "couverture",
            "nb_medias",
            "publie",
            "cree_le",
            "maj_le",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant de la réalisation (pour `/realisations/{id}/`)."},
            "reference": {"help_text": "Référence de la réalisation, ex. `REA-2026-00004`."},
            "titre": {"help_text": "Titre de la réalisation."},
            "statut": {"help_text": "Avancement du projet."},
            "taux_avancement": {"help_text": "Avancement en pourcentage (0 à 100)."},
            "date_debut_prevue": {"help_text": "Début prévu, ou `null`."},
            "date_fin_prevue": {"help_text": "Fin prévue, ou `null`."},
            "publie": {"help_text": "Vrai si publiée ; faux pour un brouillon (agents et admins uniquement)."},
            "cree_le": {"help_text": "Date de création."},
            "maj_le": {"help_text": "Date de la dernière mise à jour."},
        }

    @extend_schema_field(CouvertureSerializer(allow_null=True))
    def get_couverture(self, realisation):
        premier = next(iter(realisation.medias.all()), None)  # préchargés et triés par la vue
        if premier is None:
            return None
        return {
            "phase": premier.phase,
            "media": MediaResumeSerializer(premier.media, context=self.context).data,
        }

    def get_nb_medias(self, realisation) -> int:
        return len(realisation.medias.all())


class RealisationDetailSerializer(RealisationListSerializer):
    champs_mairie = ("publie", "cree_par")

    medias = RealisationMediaSerializer(many=True, help_text="Photos et vidéos, dans l'ordre d'affichage.")
    signalements = SignalementResumeSerializer(many=True, help_text="Signalements à l'origine des travaux.")
    suggestions = SuggestionResumeSerializer(many=True, help_text="Suggestions à l'origine des travaux.")
    budget = serializers.IntegerField(allow_null=True, help_text="Budget en FCFA, ou `null`.")
    cree_par = AgentResumeSerializer(help_text="Agent qui a créé la fiche (agents et admins uniquement).")

    class Meta(RealisationListSerializer.Meta):
        fields = [
            *RealisationListSerializer.Meta.fields,
            "description",
            "date_debut_reelle",
            "date_fin_reelle",
            "budget",
            "source_financement",
            "prestataire",
            "latitude",
            "longitude",
            "medias",
            "signalements",
            "suggestions",
            "cree_par",
        ]
        read_only_fields = fields
        extra_kwargs = {
            **RealisationListSerializer.Meta.extra_kwargs,
            "description": {"help_text": "Description des travaux."},
            "date_debut_reelle": {"help_text": "Début réel, ou `null`."},
            "date_fin_reelle": {"help_text": "Fin réelle, ou `null`."},
            "source_financement": {"help_text": "Origine du financement (budget communal, FADeC, partenaire…)."},
            "prestataire": {"help_text": "Entreprise chargée des travaux (peut être vide)."},
            "latitude": {"help_text": "Latitude du chantier, ou `null`."},
            "longitude": {"help_text": "Longitude du chantier, ou `null`."},
        }


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


class RealisationMediaEntreeSerializer(serializers.Serializer):
    media = serializers.UUIDField(help_text="Identifiant d'une photo ou vidéo envoyée avec `POST /medias/`.")
    phase = serializers.ChoiceField(
        choices=RealisationMedia.Phase.choices, help_text="Moment du chantier : `AVANT`, `PENDANT` ou `APRES`."
    )
    legende = serializers.CharField(
        max_length=255, required=False, allow_blank=True, help_text="Légende affichée sous la photo."
    )
    ordre = serializers.IntegerField(
        min_value=0, max_value=32767, required=False,
        help_text="Ordre d'affichage. Par défaut : la position dans la liste.",
    )


class RealisationEcritureSerializer(serializers.Serializer):
    """Création (`POST`) et modification partielle (`PATCH`) d'une réalisation."""

    titre = serializers.CharField(max_length=200, help_text="Titre de la réalisation.")
    description = serializers.CharField(help_text="Description des travaux.")
    secteur = serializers.PrimaryKeyRelatedField(
        queryset=Secteur.objects.filter(actif=True, pour_realisation=True),
        error_messages={"does_not_exist": "Ce secteur n'existe pas ou n'est pas utilisé pour les réalisations."},
        help_text="Identifiant du secteur (`GET /secteurs/?pour_realisation=true`).",
    )
    quartiers = serializers.PrimaryKeyRelatedField(
        queryset=Quartier.objects.filter(actif=True),
        many=True,
        allow_empty=False,
        error_messages={"does_not_exist": "Ce quartier n'existe pas ou n'est plus actif."},
        help_text="Identifiants des quartiers concernés (au moins un).",
    )
    statut = serializers.ChoiceField(
        choices=Realisation.Statut.choices, required=False, help_text="Avancement du projet (`PLANIFIEE` par défaut)."
    )
    taux_avancement = serializers.IntegerField(
        min_value=0, max_value=100, required=False, help_text="Avancement en pourcentage (0 par défaut)."
    )
    date_debut_prevue = serializers.DateField(required=False, allow_null=True, help_text="Début prévu (AAAA-MM-JJ).")
    date_fin_prevue = serializers.DateField(
        required=False, allow_null=True, help_text="Fin prévue, après le début prévu."
    )
    date_debut_reelle = serializers.DateField(required=False, allow_null=True, help_text="Début réel.")
    date_fin_reelle = serializers.DateField(required=False, allow_null=True, help_text="Fin réelle, après le début réel.")
    budget = serializers.IntegerField(
        min_value=0, max_value=MAX_BUDGET, required=False, allow_null=True, help_text="Budget en FCFA (nombre entier)."
    )
    source_financement = serializers.CharField(
        max_length=255, required=False, allow_blank=True, help_text="Origine du financement."
    )
    prestataire = serializers.CharField(
        max_length=255, required=False, allow_blank=True, help_text="Entreprise chargée des travaux."
    )
    latitude = serializers.FloatField(
        min_value=-90, max_value=90, required=False, allow_null=True,
        help_text="Latitude du chantier (avec `longitude`, dans la commune).",
    )
    longitude = serializers.FloatField(
        min_value=-180, max_value=180, required=False, allow_null=True, help_text="Longitude du chantier."
    )
    signalements = serializers.PrimaryKeyRelatedField(
        queryset=Signalement.objects.all(),
        many=True,
        required=False,
        error_messages={"does_not_exist": "Ce signalement n'existe pas."},
        help_text="Identifiants des signalements traités par ces travaux.",
    )
    suggestions = serializers.PrimaryKeyRelatedField(
        queryset=Suggestion.objects.all(),
        many=True,
        required=False,
        error_messages={"does_not_exist": "Cette suggestion n'existe pas."},
        help_text="Identifiants des suggestions mises en œuvre par ces travaux.",
    )
    medias = RealisationMediaEntreeSerializer(
        many=True,
        required=False,
        help_text="Photos et vidéos (10 photos et 2 vidéos au maximum). En `PATCH`, la liste "
        "**remplace** la précédente : les médias absents sont supprimés.",
    )
    publie = serializers.BooleanField(
        required=False,
        help_text="`true` pour rendre la réalisation visible du public ; `false` (défaut) : brouillon.",
    )

    def validate_medias(self, elements):
        ids = [str(e["media"]) for e in elements]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Un même fichier apparaît plusieurs fois.")
        return elements
