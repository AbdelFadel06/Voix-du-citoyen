from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.permissions import LectureSeuleOrganisation
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_MEDIAS,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_succes,
    exemple_trop_de_requetes,
)

from . import services
from .serializers import MediaSerializer, TeleversementSerializer

MESSAGE_ENVOI = "Fichier envoyé."
URL = "https://api.exemple.bj/media/medias"
PHOTO = {
    "id": "3f6c1a2e-8b4d-4c1e-9a7f-2d5e6b8c9a01",
    "type": "IMAGE",
    "statut": "TEMPORAIRE",
    "fichier": f"{URL}/image/2026/10/3f6c1a2e-8b4d-4c1e-9a7f-2d5e6b8c9a01.jpg",
    "miniature": f"{URL}/miniatures/2026/10/3f6c1a2e-8b4d-4c1e-9a7f-2d5e6b8c9a01.jpg",
    "mime_type": "image/jpeg",
    "taille_octets": 1843200,
    "duree_secondes": None,
    "largeur": 3000,
    "hauteur": 4000,
    "cree_le": "2026-10-06T16:20:11+01:00",
}
VIDEO = {
    **PHOTO,
    "id": "9b2d4e6f-1a3c-4b5d-8e7f-0a1b2c3d4e5f",
    "type": "VIDEO",
    "fichier": f"{URL}/video/2026/10/9b2d4e6f-1a3c-4b5d-8e7f-0a1b2c3d4e5f.mp4",
    "miniature": f"{URL}/miniatures/2026/10/9b2d4e6f-1a3c-4b5d-8e7f-0a1b2c3d4e5f.jpg",
    "mime_type": "video/mp4",
    "taille_octets": 14680064,
    "duree_secondes": 38,
    "largeur": 1280,
    "hauteur": 720,
}
AUDIO = {
    **PHOTO,
    "id": "c4d5e6f7-a8b9-4c0d-9e1f-2a3b4c5d6e7f",
    "type": "AUDIO",
    "fichier": f"{URL}/audio/2026/10/c4d5e6f7-a8b9-4c0d-9e1f-2a3b4c5d6e7f.m4a",
    "miniature": None,
    "mime_type": "audio/x-m4a",
    "taille_octets": 958464,
    "duree_secondes": 47,
    "largeur": None,
    "hauteur": None,
}


class TeleversementView(APIView):
    permission_classes = [IsAuthenticated, LectureSeuleOrganisation]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "televersement"

    @extend_schema(
        tags=[TAG_MEDIAS],
        summary="Envoyer un fichier (photo, vidéo, audio)",
        description="""
**Première étape de l'envoi en deux temps.** Les fichiers sont envoyés **un par un**, avant
le signalement (ou la suggestion, la réalisation) :

1. `POST /medias/` pour chaque fichier (requête `multipart/form-data`) → la réponse donne
   l'`id` du média, au statut `TEMPORAIRE`. En cas de coupure réseau, seul le fichier en
   cours est à renvoyer.
2. Créer ensuite l'objet en JSON avec la liste des `id` (`medias`, `description_audio`).
   Les médias passent alors au statut `ATTACHE`.

Un média `TEMPORAIRE` qui n'est rattaché à rien est **supprimé au bout de 24 h**.
Un média ne peut servir qu'**une seule fois**, et uniquement à son auteur.

**Contrôles**
| Type | Formats | Taille max | Durée max |
|---|---|---|---|
| `IMAGE` | JPEG, PNG, WebP | 5 Mo | — |
| `VIDEO` | MP4, MOV, 3GP | 25 Mo | 60 s |
| `AUDIO` | M4A, AAC, OGG/Opus, MP3 | 3 Mo | 2 min |

- Le format est vérifié sur le **contenu réel** du fichier, pas sur son extension.
- Photos : les **métadonnées (EXIF, position GPS…) sont supprimées**, l'orientation est
  corrigée et une miniature est générée.
- Vidéos : la **miniature est fournie par l'application** (champ `miniature`).
- Vidéos et audios : la durée est déclarée par l'application (`duree_secondes`).

**Limitation** : 60 envois par heure et par utilisateur.

**Connecté** : citoyens, agents et admins mairie (les organisations sont en lecture seule).
""",
        request={"multipart/form-data": TeleversementSerializer},
        responses={201: enveloppe(MediaSerializer), **erreurs(400, 401, 403, 429)},
        examples=[
            exemple_succes("Photo envoyée", PHOTO, MESSAGE_ENVOI, statut=201),
            exemple_succes("Vidéo envoyée", VIDEO, MESSAGE_ENVOI, statut=201),
            exemple_succes("Enregistrement vocal envoyé", AUDIO, MESSAGE_ENVOI, statut=201),
            exemple_erreur(
                CodeErreur.MEDIA_FORMAT_NON_AUTORISE,
                "Ce format de fichier n'est pas accepté. Formats acceptés : JPEG, PNG ou WebP.",
                details={"fichier": ["Formats acceptés : JPEG, PNG ou WebP."], "type_detecte": "application/pdf"},
            ),
            exemple_erreur(
                CodeErreur.MEDIA_TROP_VOLUMINEUX,
                "Ce fichier est trop volumineux : 5 Mo au maximum.",
                details={"fichier": ["5 Mo au maximum."], "taille_max_octets": 5242880},
            ),
            exemple_erreur(
                CodeErreur.MEDIA_TROP_LONG,
                "Cet enregistrement est trop long : 1 minute au maximum.",
                details={"duree_secondes": ["1 minute au maximum."], "duree_max_secondes": 60},
            ),
            exemple_erreur(
                CodeErreur.MEDIA_ILLISIBLE, details={"fichier": ["L'image est illisible ou endommagée."]}
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={
                    "duree_secondes": ["La durée est obligatoire pour une vidéo ou un enregistrement vocal."],
                    "miniature": ["Une image d'aperçu est obligatoire pour une vidéo."],
                },
                nom="Vidéo sans durée ni miniature",
            ),
            exemple_erreur(
                CodeErreur.PERMISSION_REFUSEE,
                "Les organisations ont un accès en lecture seule.",
                nom="Compte organisation",
            ),
            exemple_trop_de_requetes(1200),
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def post(self, request):
        serializer = TeleversementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = services.televerser_media(auteur=request.user, **serializer.validated_data)
        return reponse_succes(
            MediaSerializer(media, context={"request": request}).data,
            MESSAGE_ENVOI,
            status=status.HTTP_201_CREATED,
        )
