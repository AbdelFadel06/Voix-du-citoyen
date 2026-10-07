from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import AgentResumeSerializer
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

from .models import Suggestion, SuiviSuggestion


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------


class SuggestionListSerializer(ChampsMairieMixin, serializers.ModelSerializer):
    champs_mairie = ("est_pertinente",)

    commune = CommuneResumeSerializer(help_text="Commune de la suggestion (celle de son auteur).")
    secteur = SecteurResumeSerializer(help_text="Secteur concerné.")
    quartier = QuartierResumeSerializer(
        allow_null=True, help_text="Quartier concerné, ou `null` si la suggestion concerne toute la commune."
    )
    medias = MediaResumeSerializer(many=True, help_text="Aperçus des photos (miniatures uniquement).")
    auteur = serializers.SerializerMethodField(help_text="Identité de l'auteur, envoyée **seulement à l'auteur lui-même** ; `null` pour tous les autres (mairie comprise).")
    est_auteur = serializers.SerializerMethodField(help_text="Vrai si l'utilisateur connecté est l'auteur.")
    je_soutiens = serializers.SerializerMethodField(
        help_text="Vrai si l'utilisateur connecté soutient cette suggestion."
    )
    a_reponse = serializers.SerializerMethodField(help_text="Vrai si la mairie a publié une réponse officielle.")

    class Meta:
        model = Suggestion
        fields = [
            "id",
            "reference",
            "titre",
            "commune",
            "secteur",
            "quartier",
            "nb_soutiens",
            "je_soutiens",
            "medias",
            "auteur",
            "est_auteur",
            "a_reponse",
            "est_pertinente",
            "cree_le",
            "maj_le",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "est_pertinente": {
                "help_text": "Vrai si la mairie a coché la suggestion comme pertinente "
                "(agents et admins uniquement)."
            },
            "id": {"help_text": "Identifiant de la suggestion (pour `/suggestions/{id}/`)."},
            "reference": {"help_text": "Référence de la suggestion, ex. `SUG-2026-00007`."},
            "titre": {"help_text": "Titre de la suggestion."},
            "nb_soutiens": {"help_text": "Nombre de citoyens qui soutiennent la suggestion."},
            "cree_le": {"help_text": "Date d'envoi."},
            "maj_le": {"help_text": "Date de la dernière mise à jour."},
        }

    @extend_schema_field(AuteurSerializer(allow_null=True))
    def get_auteur(self, suggestion):
        return representer_auteur(suggestion, utilisateur_connecte(self))

    def get_est_auteur(self, suggestion) -> bool:
        viewer = utilisateur_connecte(self)
        return viewer is not None and viewer.pk == suggestion.auteur_id

    def get_je_soutiens(self, suggestion) -> bool:
        # Annoté par la vue (une seule requête pour toute la liste).
        return bool(getattr(suggestion, "je_soutiens", False))

    def get_a_reponse(self, suggestion) -> bool:
        return bool(suggestion.reponse_officielle)


class SuiviSuggestionSerializer(SuiviSerializer):
    class Meta(SuiviSerializer.Meta):
        model = SuiviSuggestion
        # Pas de statut pour les suggestions.
        fields = [f for f in SuiviSerializer.Meta.fields if f not in ("ancien_statut", "nouveau_statut")]
        read_only_fields = fields


class SuggestionDetailSerializer(SuggestionListSerializer):
    champs_mairie = ("est_pertinente", "repondu_par")

    medias = MediaSerializer(many=True, help_text="Photos complètes.")
    repondu_par = AgentResumeSerializer(
        allow_null=True, help_text="Auteur de la réponse officielle (agents et admins uniquement)."
    )
    historique = SuiviSuggestionSerializer(
        source="suivis",
        many=True,
        help_text="Historique chronologique. Les notes internes ne sont visibles que par la mairie.",
    )

    class Meta(SuggestionListSerializer.Meta):
        fields = [
            *SuggestionListSerializer.Meta.fields,
            "description",
            "reponse_officielle",
            "repondu_le",
            "repondu_par",
            "historique",
        ]
        read_only_fields = fields
        extra_kwargs = {
            **SuggestionListSerializer.Meta.extra_kwargs,
            "description": {"help_text": "Description complète de l'idée."},
            "reponse_officielle": {"help_text": "Dernière réponse officielle de la mairie (vide si aucune)."},
            "repondu_le": {"help_text": "Date de la réponse officielle, ou `null`."},
        }


class PertinenceSerializer(serializers.Serializer):
    est_pertinente = serializers.BooleanField(help_text="État de la marque « pertinente » après l'opération.")


class SoutienSerializer(serializers.Serializer):
    nb_soutiens = serializers.IntegerField(help_text="Nombre de soutiens après l'opération.")
    je_soutiens = serializers.BooleanField(help_text="Vrai si le citoyen soutient désormais la suggestion.")


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


class SuggestionCreateSerializer(serializers.Serializer):
    titre = serializers.CharField(max_length=150, help_text="Titre court de l'idée.")
    description = serializers.CharField(help_text="Description de l'idée et de ce qu'elle apporterait.")
    secteur = serializers.PrimaryKeyRelatedField(
        queryset=Secteur.objects.filter(actif=True, pour_suggestion=True),
        error_messages={"does_not_exist": "Ce secteur n'existe pas ou n'est pas proposé pour une suggestion."},
        help_text="Identifiant du secteur (`GET /secteurs/?pour_suggestion=true`).",
    )
    quartier = serializers.PrimaryKeyRelatedField(
        queryset=Quartier.objects.filter(actif=True),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce quartier n'existe pas ou n'est plus actif."},
        help_text="Quartier concerné, dans la commune du citoyen. Laisser vide (ou `null`) si l'idée "
        "concerne toute la commune.",
    )
    medias = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Identifiants de photos envoyées avec `POST /medias/` (facultatif, 3 au maximum).",
    )


class ReponseSuggestionSerializer(serializers.Serializer):
    commentaire = serializers.CharField(help_text="Texte de la réponse ou de la note.")
    interne = serializers.BooleanField(
        default=False,
        help_text="`true` : note interne, visible uniquement par la mairie. "
        "`false` (défaut) : réponse officielle, visible par tous.",
    )
