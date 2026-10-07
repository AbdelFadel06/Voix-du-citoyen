from rest_framework import serializers

from .models import Media


class TeleversementSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=Media.Type.choices,
        help_text="Nature du fichier : `IMAGE` (photo), `VIDEO` ou `AUDIO` (enregistrement vocal).",
    )
    fichier = serializers.FileField(
        allow_empty_file=False,
        help_text="Le fichier, un seul par requête. Photo : JPEG, PNG ou WebP, 5 Mo max. "
        "Vidéo : MP4, MOV ou 3GP, 25 Mo et 60 s max. Audio : M4A, AAC, OGG/Opus ou MP3, "
        "3 Mo et 2 min max.",
    )
    duree_secondes = serializers.FloatField(
        min_value=0,
        required=False,
        help_text="Durée en secondes, **obligatoire** pour une vidéo ou un audio "
        "(arrondie à la seconde supérieure).",
    )
    miniature = serializers.FileField(
        required=False,
        allow_empty_file=False,
        help_text="Image d'aperçu (JPEG, PNG ou WebP, 5 Mo max), **obligatoire** pour une vidéo "
        "et refusée sinon. Pour une photo, la miniature est générée par le serveur.",
    )
    largeur = serializers.IntegerField(
        min_value=1, required=False, help_text="Largeur de la vidéo en pixels (facultatif)."
    )
    hauteur = serializers.IntegerField(
        min_value=1, required=False, help_text="Hauteur de la vidéo en pixels (facultatif)."
    )

    def validate(self, attrs):
        type_media = attrs["type"]
        erreurs = {}
        if type_media in (Media.Type.VIDEO, Media.Type.AUDIO) and attrs.get("duree_secondes") is None:
            erreurs["duree_secondes"] = ["La durée est obligatoire pour une vidéo ou un enregistrement vocal."]
        if type_media == Media.Type.VIDEO and not attrs.get("miniature"):
            erreurs["miniature"] = ["Une image d'aperçu est obligatoire pour une vidéo."]
        if type_media != Media.Type.VIDEO:
            if attrs.get("miniature"):
                erreurs["miniature"] = ["L'image d'aperçu n'est acceptée que pour une vidéo."]
            attrs.pop("largeur", None)
            attrs.pop("hauteur", None)
        if erreurs:
            raise serializers.ValidationError(erreurs)
        return attrs


class MediaSerializer(serializers.ModelSerializer):
    """Détail complet d'un média (fichier original compris)."""

    class Meta:
        model = Media
        fields = [
            "id",
            "type",
            "statut",
            "fichier",
            "miniature",
            "mime_type",
            "taille_octets",
            "duree_secondes",
            "largeur",
            "hauteur",
            "cree_le",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant du média, à envoyer ensuite dans `medias` ou `description_audio`."},
            "type": {"help_text": "Nature du fichier."},
            "statut": {
                "help_text": "`TEMPORAIRE` tant qu'il n'est rattaché à rien (supprimé après 24 h), "
                "puis `ATTACHE`."
            },
            "fichier": {"help_text": "Adresse du fichier complet (photo sans métadonnées)."},
            "miniature": {"help_text": "Adresse de l'aperçu JPEG (480 px max), ou `null` pour un audio."},
            "mime_type": {"help_text": "Type réel du fichier, détecté par le serveur."},
            "taille_octets": {"help_text": "Taille du fichier enregistré, en octets."},
            "duree_secondes": {"help_text": "Durée (vidéo, audio), ou `null` pour une photo."},
            "largeur": {"help_text": "Largeur en pixels, ou `null` si inconnue."},
            "hauteur": {"help_text": "Hauteur en pixels, ou `null` si inconnue."},
            "cree_le": {"help_text": "Date d'envoi."},
        }


class MediaResumeSerializer(serializers.ModelSerializer):
    """Version légère pour les listes : aperçu seulement, jamais le fichier complet."""

    class Meta:
        model = Media
        fields = ["id", "type", "miniature", "duree_secondes"]
        read_only_fields = fields
        extra_kwargs = MediaSerializer.Meta.extra_kwargs


