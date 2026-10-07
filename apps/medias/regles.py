"""
Règles des fichiers acceptés (CLAUDE.md § 6 « Médias »).

Le type réel est déterminé par python-magic à partir du contenu, jamais par l'extension
ni par le Content-Type envoyé : l'extension enregistrée est déduite du type réel.
"""

from dataclasses import dataclass

from .models import Media

MO = 1024 * 1024


@dataclass(frozen=True)
class RegleFichier:
    taille_max: int  # octets
    duree_max: int | None  # secondes
    mimes: dict  # type MIME détecté -> extension enregistrée
    formats: str  # libellé pour les messages d'erreur

    @property
    def taille_max_mo(self):
        return self.taille_max // MO


REGLES = {
    Media.Type.IMAGE: RegleFichier(
        taille_max=5 * MO,
        duree_max=None,
        mimes={"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
        formats="JPEG, PNG ou WebP",
    ),
    Media.Type.VIDEO: RegleFichier(
        taille_max=25 * MO,
        duree_max=60,
        mimes={"video/mp4": ".mp4", "video/quicktime": ".mov", "video/3gpp": ".3gp"},
        formats="MP4, MOV ou 3GP",
    ),
    Media.Type.AUDIO: RegleFichier(
        taille_max=3 * MO,
        duree_max=120,
        mimes={
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/m4a": ".m4a",
            # Les enregistrements MPEG-4 d'Android sont souvent détectés comme vidéo.
            "video/mp4": ".m4a",
            "audio/aac": ".aac",
            "audio/x-aac": ".aac",
            "audio/x-hx-aac-adts": ".aac",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/mpeg": ".mp3",
        },
        formats="M4A, AAC, OGG/Opus ou MP3",
    ),
}

# Miniature d'une vidéo, envoyée par le mobile (pas de traitement vidéo côté serveur).
REGLE_MINIATURE = RegleFichier(
    taille_max=5 * MO,
    duree_max=None,
    mimes=REGLES[Media.Type.IMAGE].mimes,
    formats="JPEG, PNG ou WebP",
)

# Côté le plus long des miniatures générées (pixels).
TAILLE_MINIATURE = 480


@dataclass(frozen=True)
class RegleRattachement:
    """Nombre de fichiers autorisés sur un objet (signalement, suggestion, réalisation)."""

    objet: str  # avec son article, pour les messages : « ce signalement »
    images_max: int
    videos_max: int = 0
    minimum: int = 0


RATTACHEMENT_SIGNALEMENT = RegleRattachement("ce signalement", images_max=4, videos_max=1, minimum=1)
RATTACHEMENT_SUGGESTION = RegleRattachement("cette suggestion", images_max=3)
RATTACHEMENT_REALISATION = RegleRattachement("cette réalisation", images_max=10, videos_max=2)
