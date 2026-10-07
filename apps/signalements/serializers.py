from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.accounts.serializers import AgentResumeSerializer, ServiceResumeSerializer
from apps.core.visibilite import (
    AuteurSerializer,
    ChampsMairieMixin,
    SuiviSerializer,
    representer_auteur,
    utilisateur_connecte,
)
from apps.medias.serializers import MediaResumeSerializer, MediaSerializer
from apps.referentiel.models import Secteur
from apps.referentiel.serializers import SecteurResumeSerializer
from apps.territoire.models import Quartier
from apps.territoire.serializers import CommuneResumeSerializer, QuartierResumeSerializer

from .models import Signalement, SuiviSignalement

Mode = Signalement.ModeLocalisation
Statut = Signalement.Statut

# Statuts qu'un agent peut donner (SOUMIS n'est donné qu'à la création).
CHOIX_STATUTS_CIBLES = [choix for choix in Statut.choices if choix[0] != Statut.SOUMIS]


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


class SignalementListSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    champs_mairie = ("priorite", "service_assigne", "agent_assigne")

    commune = CommuneResumeSerializer(help_text="Commune du signalement (celle de son auteur).")
    secteur = SecteurResumeSerializer(help_text="Secteur du problème.")
    quartier = QuartierResumeSerializer(help_text="Quartier du signalement.")
    medias = MediaResumeSerializer(many=True, help_text="Aperçus des photos et vidéos (miniatures uniquement).")
    a_description_audio = serializers.SerializerMethodField(help_text="Vrai si une description vocale est jointe.")
    auteur = serializers.SerializerMethodField(help_text="Identité de l'auteur, envoyée **seulement à l'auteur lui-même** ; `null` pour tous les autres (mairie comprise).")
    est_auteur = serializers.SerializerMethodField(help_text="Vrai si l'utilisateur connecté est l'auteur.")
    service_assigne = ServiceResumeSerializer(
        allow_null=True, help_text="Service chargé du dossier (agents et admins uniquement)."
    )
    agent_assigne = AgentResumeSerializer(
        allow_null=True, help_text="Agent chargé du dossier (agents et admins uniquement)."
    )

    class Meta:
        model = Signalement
        fields = [
            "id",
            "reference",
            "titre",
            "statut",
            "commune",
            "secteur",
            "quartier",
            "mode_localisation",
            "latitude",
            "longitude",
            "repere",
            "medias",
            "a_description_audio",
            "auteur",
            "est_auteur",
            "priorite",
            "service_assigne",
            "agent_assigne",
            "cree_le",
            "maj_le",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant du signalement (pour `/signalements/{id}/`)."},
            "reference": {"help_text": "Référence à communiquer au citoyen, ex. `SIG-2026-00012`."},
            "titre": {"help_text": "Titre saisi, ou généré « Secteur – Quartier »."},
            "statut": {"help_text": "Étape de traitement du signalement."},
            "mode_localisation": {"help_text": "`GPS` (position sur la carte) ou `MANUEL` (quartier et repère)."},
            "latitude": {"help_text": "Latitude (mode GPS), sinon `null`."},
            "longitude": {"help_text": "Longitude (mode GPS), sinon `null`."},
            "repere": {"help_text": "Repère donné par le citoyen, ex. « derrière le marché Dantokpa »."},
            "priorite": {"help_text": "Priorité de traitement (agents et admins uniquement)."},
            "cree_le": {"help_text": "Date d'envoi."},
            "maj_le": {"help_text": "Date de la dernière mise à jour."},
        }

    def get_a_description_audio(self, signalement) -> bool:
        return signalement.description_audio_id is not None

    @extend_schema_field(AuteurSerializer(allow_null=True))
    def get_auteur(self, signalement):
        return representer_auteur(signalement, utilisateur_connecte(self))

    def get_est_auteur(self, signalement) -> bool:
        viewer = utilisateur_connecte(self)
        return viewer is not None and viewer.pk == signalement.auteur_id


class SuiviSignalementSerializer(SuiviSerializer):
    class Meta(SuiviSerializer.Meta):
        model = SuiviSignalement


class SignalementResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Signalement
        fields = ["id", "reference", "titre", "statut"]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant du signalement."},
            "reference": {"help_text": "Référence du signalement."},
            "titre": {"help_text": "Titre du signalement."},
            "statut": {"help_text": "Statut du signalement."},
        }


class SignalementDetailSerializer(SignalementListSerializer):
    medias = MediaSerializer(many=True, help_text="Photos et vidéos complètes.")
    description_audio = MediaSerializer(allow_null=True, help_text="Description vocale, ou `null`.")
    doublon_de = SignalementResumeSerializer(allow_null=True, help_text="Signalement d'origine (statut `DOUBLON`).")
    historique = SuiviSignalementSerializer(
        source="suivis",
        many=True,
        help_text="Historique chronologique. Les notes internes ne sont visibles que par la mairie.",
    )

    class Meta(SignalementListSerializer.Meta):
        fields = [
            *SignalementListSerializer.Meta.fields,
            "titre_genere",
            "description_texte",
            "description_audio",
            "precision_gps",
            "doublon_de",
            "date_resolution",
            "historique",
        ]
        read_only_fields = fields
        extra_kwargs = {
            **SignalementListSerializer.Meta.extra_kwargs,
            "titre_genere": {"help_text": "Vrai si le titre a été généré automatiquement."},
            "description_texte": {"help_text": "Description écrite (peut être vide si audio)."},
            "precision_gps": {"help_text": "Précision de la position GPS en mètres, ou `null`."},
            "date_resolution": {"help_text": "Date de passage au statut `RESOLU`, ou `null`."},
        }


class AvertissementSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Code de l'avertissement, ex. `GPS_IMPRECIS`.")
    message = serializers.CharField(help_text="Message à afficher au citoyen.")


class SignalementCreeSerializer(SignalementDetailSerializer):
    avertissements = AvertissementSerializer(
        many=True, read_only=True, help_text="Points à signaler au citoyen, sans bloquer l'envoi."
    )

    class Meta(SignalementDetailSerializer.Meta):
        fields = [*SignalementDetailSerializer.Meta.fields, "avertissements"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


class SignalementCreateSerializer(serializers.Serializer):
    secteur = serializers.PrimaryKeyRelatedField(
        queryset=Secteur.objects.filter(actif=True, pour_signalement=True),
        error_messages={"does_not_exist": "Ce secteur n'existe pas ou n'est pas proposé pour un signalement."},
        help_text="Identifiant du secteur (`GET /secteurs/?pour_signalement=true`).",
    )
    titre = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Titre court. **Facultatif si une description vocale est jointe** : il est alors "
        "généré « Secteur – Quartier ».",
    )
    description_texte = serializers.CharField(
        required=False, allow_blank=True, help_text="Description écrite du problème."
    )
    description_audio = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Identifiant d'un enregistrement vocal envoyé avec `POST /medias/` (type `AUDIO`). "
        "Une description écrite **ou** vocale est obligatoire (les deux sont possibles).",
    )
    medias = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="Identifiants des photos et vidéos envoyées avec `POST /medias/` : "
        "au moins 1, au plus 4 photos et 1 vidéo.",
    )
    mode_localisation = serializers.ChoiceField(
        choices=Mode.choices,
        help_text="`GPS` : position choisie sur la carte. `MANUEL` : quartier et repère seulement.",
    )
    latitude = serializers.FloatField(
        min_value=-90, max_value=90, required=False, allow_null=True,
        help_text="Latitude (obligatoire en mode GPS).",
    )
    longitude = serializers.FloatField(
        min_value=-180, max_value=180, required=False, allow_null=True,
        help_text="Longitude (obligatoire en mode GPS).",
    )
    precision_gps = serializers.IntegerField(
        min_value=0, required=False, allow_null=True,
        help_text="Précision de la position en mètres (obligatoire en mode GPS). "
        "Au-delà de 100 m, un avertissement est renvoyé.",
    )
    quartier = serializers.PrimaryKeyRelatedField(
        queryset=Quartier.objects.filter(actif=True).select_related("arrondissement__commune"),
        error_messages={"does_not_exist": "Ce quartier n'existe pas ou n'est plus actif."},
        help_text="Identifiant du quartier, **toujours obligatoire**, dans la commune du citoyen. En mode "
        "GPS, utiliser la proposition de `GET /quartiers/proche/`, confirmée par le citoyen.",
    )
    repere = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
        help_text="Lieu connu à proximité, ex. « derrière le marché ». **Obligatoire en mode MANUEL.**",
    )

    def validate(self, attrs):
        erreurs = {}
        if attrs["mode_localisation"] == Mode.GPS:
            for champ in ("latitude", "longitude", "precision_gps"):
                if attrs.get(champ) is None:
                    erreurs[champ] = ["Obligatoire en mode GPS."]
        elif not attrs.get("repere", "").strip():
            erreurs["repere"] = ["Indiquez un repère (lieu connu à proximité) en mode manuel."]

        a_audio = attrs.get("description_audio") is not None
        if not attrs.get("description_texte", "").strip() and not a_audio:
            erreurs["description_texte"] = ["Décrivez le problème par écrit ou par un enregistrement vocal."]
        if not attrs.get("titre", "").strip() and not a_audio:
            erreurs["titre"] = ["Le titre est obligatoire sans description vocale."]
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return attrs


class ChangementStatutSignalementSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=CHOIX_STATUTS_CIBLES,
        help_text="Nouveau statut.",
    )
    commentaire = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Message visible par le citoyen. **Obligatoire pour `REJETE`** (motif du rejet).",
    )
    doublon_de = serializers.PrimaryKeyRelatedField(
        queryset=Signalement.objects.all(),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce signalement n'existe pas."},
        help_text="Identifiant du signalement d'origine. **Obligatoire pour `DOUBLON`.**",
    )


class AssignationSerializer(serializers.Serializer):
    service = serializers.PrimaryKeyRelatedField(
        queryset=ServiceMunicipal.objects.filter(actif=True),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce service n'existe pas ou n'est plus actif."},
        help_text="Service chargé du dossier.",
    )
    agent = serializers.PrimaryKeyRelatedField(
        queryset=Utilisateur.objects.filter(role=Utilisateur.Role.AGENT, is_active=True).select_related("service"),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Cet agent n'existe pas ou n'est plus actif."},
        help_text="Agent chargé du dossier. Son service est alors assigné automatiquement.",
    )

    def validate(self, attrs):
        if not attrs.get("service") and not attrs.get("agent"):
            raise serializers.ValidationError({"service": ["Indiquez un service ou un agent."]})
        return attrs


class ReponseSignalementSerializer(serializers.Serializer):
    commentaire = serializers.CharField(help_text="Texte de la réponse ou de la note.")
    interne = serializers.BooleanField(
        default=False,
        help_text="`true` : note interne, visible uniquement par la mairie. "
        "`false` (défaut) : réponse officielle, visible par le citoyen.",
    )
