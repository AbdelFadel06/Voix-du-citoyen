import io
import logging
import math
import uuid

import magic
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier

from .models import Media
from .regles import REGLE_MINIATURE, REGLES, TAILLE_MINIATURE

logger = logging.getLogger(__name__)

FORMATS_PILLOW = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
OCTETS_DETECTION = 4096


# ---------------------------------------------------------------------------
# Contrôles d'un fichier
# ---------------------------------------------------------------------------


def detecter_mime(fichier):
    """Type MIME réel, lu dans le contenu du fichier (pas l'extension)."""
    fichier.seek(0)
    entete = fichier.read(OCTETS_DETECTION)
    fichier.seek(0)
    return magic.from_buffer(entete, mime=True)


def controler_fichier(fichier, regle, champ="fichier"):
    """Vérifie taille et format ; renvoie le type MIME détecté."""
    if fichier.size > regle.taille_max:
        raise ErreurMetier(
            CodeErreur.MEDIA_TROP_VOLUMINEUX,
            f"Ce fichier est trop volumineux : {regle.taille_max_mo} Mo au maximum.",
            details={champ: [f"{regle.taille_max_mo} Mo au maximum."], "taille_max_octets": regle.taille_max},
        )
    mime = detecter_mime(fichier)
    if mime not in regle.mimes:
        raise ErreurMetier(
            CodeErreur.MEDIA_FORMAT_NON_AUTORISE,
            f"Ce format de fichier n'est pas accepté. Formats acceptés : {regle.formats}.",
            details={champ: [f"Formats acceptés : {regle.formats}."], "type_detecte": mime},
        )
    return mime


def controler_duree(duree_secondes, regle):
    if regle.duree_max is not None and duree_secondes > regle.duree_max:
        limite = _duree_lisible(regle.duree_max)
        raise ErreurMetier(
            CodeErreur.MEDIA_TROP_LONG,
            f"Cet enregistrement est trop long : {limite} au maximum.",
            details={"duree_secondes": [f"{limite} au maximum."], "duree_max_secondes": regle.duree_max},
        )


def _duree_lisible(secondes):
    if secondes % 60 == 0:
        minutes = secondes // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    return f"{secondes} secondes"


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


def ouvrir_image(fichier, champ="fichier"):
    """Ouvre et décode entièrement l'image, redressée selon son orientation EXIF."""
    fichier.seek(0)
    try:
        image = Image.open(fichier)
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError):
        raise ErreurMetier(
            CodeErreur.MEDIA_ILLISIBLE, details={champ: ["L'image est illisible ou endommagée."]}
        )
    return ImageOps.exif_transpose(image)


def image_sans_metadonnees(image, mime):
    """
    Réencode l'image sans aucune métadonnée (EXIF, GPS, commentaires…) : seuls les pixels
    sont conservés. L'orientation a déjà été appliquée par ouvrir_image.
    """
    format_pillow = FORMATS_PILLOW[mime]
    propre = image.copy()
    propre.info = {}  # supprime EXIF, XMP, textes PNG…
    if format_pillow == "JPEG" and propre.mode not in ("RGB", "L"):
        propre = propre.convert("RGB")
    sortie = io.BytesIO()
    options = {"quality": 85, "optimize": True} if format_pillow in ("JPEG", "WEBP") else {"optimize": True}
    propre.save(sortie, format=format_pillow, exif=b"", **options)
    return ContentFile(sortie.getvalue())


def creer_miniature(image):
    """Miniature JPEG (côté le plus long : TAILLE_MINIATURE px), fond blanc si transparence."""
    miniature = image.copy()
    miniature.info = {}
    miniature.thumbnail((TAILLE_MINIATURE, TAILLE_MINIATURE))
    if miniature.mode in ("RGBA", "LA", "P"):
        miniature = miniature.convert("RGBA")
        fond = Image.new("RGB", miniature.size, "white")
        fond.paste(miniature, mask=miniature.getchannel("A"))
        miniature = fond
    elif miniature.mode != "RGB":
        miniature = miniature.convert("RGB")
    sortie = io.BytesIO()
    miniature.save(sortie, format="JPEG", quality=75, optimize=True, exif=b"")
    return ContentFile(sortie.getvalue())


# ---------------------------------------------------------------------------
# Téléversement
# ---------------------------------------------------------------------------


def televerser_media(*, auteur, type, fichier, duree_secondes=None, miniature=None, largeur=None, hauteur=None):
    """
    Contrôle, nettoie et enregistre un fichier envoyé (statut TEMPORAIRE).

    - IMAGE : métadonnées supprimées, dimensions lues, miniature générée.
    - VIDEO : enregistrée telle quelle ; la miniature est fournie par le mobile.
    - AUDIO : enregistré tel quel, sans miniature.
    La durée des vidéos et audios est déclarée par le mobile (pas d'analyse côté serveur).
    """
    regle = REGLES[type]
    mime = controler_fichier(fichier, regle)
    if duree_secondes is not None:
        duree_secondes = math.ceil(duree_secondes)
        controler_duree(duree_secondes, regle)

    media = Media(
        id=uuid.uuid4(),
        auteur=auteur,
        type=type,
        mime_type=mime,
        duree_secondes=duree_secondes if type != Media.Type.IMAGE else None,
    )
    nom = f"{media.id}{regle.mimes[mime]}"

    if type == Media.Type.IMAGE:
        image = ouvrir_image(fichier)
        contenu = image_sans_metadonnees(image, mime)
        media.largeur, media.hauteur = image.size
        apercu = creer_miniature(image)
    elif type == Media.Type.VIDEO:
        controler_fichier(miniature, REGLE_MINIATURE, champ="miniature")
        apercu = creer_miniature(ouvrir_image(miniature, champ="miniature"))
        fichier.seek(0)
        contenu = fichier
        media.largeur, media.hauteur = largeur, hauteur
    else:
        fichier.seek(0)
        contenu = fichier
        apercu = None

    try:
        media.fichier.save(nom, contenu, save=False)
        if apercu is not None:
            media.miniature.save(f"{media.id}.jpg", apercu, save=False)
        media.taille_octets = media.fichier.size
        media.save()
    except Exception:
        _supprimer_fichiers(media)
        raise
    return media


# ---------------------------------------------------------------------------
# Rattachement à un objet (signalement, suggestion, réalisation)
# ---------------------------------------------------------------------------


def verrouiller_temporaires(auteur, ids):
    """
    Médias TEMPORAIRE de `auteur` demandés, verrouillés jusqu'à la fin de la transaction.
    Un média inconnu ou d'un autre auteur donne MEDIA_INTROUVABLE (sans distinction),
    un média déjà rattaché MEDIA_DEJA_UTILISE.
    """
    try:
        ids = list(dict.fromkeys(str(uuid.UUID(str(i))) for i in ids))  # sans doublons, ordre conservé
    except ValueError:
        raise ErreurMetier(CodeErreur.MEDIA_INTROUVABLE)
    medias = {str(m.id): m for m in Media.objects.select_for_update().filter(id__in=ids, auteur=auteur)}
    if len(medias) != len(ids):
        # Inconnu ou appartenant à quelqu'un d'autre : même réponse, rien n'est révélé.
        raise ErreurMetier(CodeErreur.MEDIA_INTROUVABLE)
    if any(m.statut != Media.Statut.TEMPORAIRE for m in medias.values()):
        raise ErreurMetier(CodeErreur.MEDIA_DEJA_UTILISE)
    return [medias[i] for i in ids]


def controler_rattachement(medias, regle):
    """Vérifie le nombre et le type des médias d'un objet selon `regle` (RegleRattachement)."""
    images = sum(m.type == Media.Type.IMAGE for m in medias)
    videos = sum(m.type == Media.Type.VIDEO for m in medias)
    audios = sum(m.type == Media.Type.AUDIO for m in medias)
    problemes = []
    if len(medias) < regle.minimum:
        problemes.append(f"Au moins {regle.minimum} photo ou vidéo est obligatoire.")
    if images > regle.images_max:
        problemes.append(f"{regle.images_max} photo(s) au maximum.")
    if videos > regle.videos_max:
        problemes.append(
            f"{regle.videos_max} vidéo(s) au maximum." if regle.videos_max else "Les vidéos ne sont pas acceptées ici."
        )
    if audios:
        problemes.append("Les enregistrements vocaux ne sont pas acceptés dans les photos et vidéos.")
    if problemes:
        raise ErreurMetier(
            CodeErreur.MEDIAS_NON_CONFORMES,
            f"Les fichiers joints à {regle.objet} ne respectent pas les règles.",
            details={"medias": problemes},
        )
    return medias


def verifier_medias(auteur, ids, regle):
    """
    Vérifie les nouveaux médias joints à un objet et les renvoie. À appeler dans une
    transaction, avant de créer l'objet, puis appeler `attacher()`.
    """
    return controler_rattachement(verrouiller_temporaires(auteur, ids), regle)


def verifier_audio(auteur, media_id):
    """Vérifie un enregistrement vocal joint (ex. description audio d'un signalement)."""
    (media,) = verrouiller_temporaires(auteur, [media_id])
    if media.type != Media.Type.AUDIO:
        raise ErreurMetier(
            CodeErreur.MEDIAS_NON_CONFORMES,
            details={"description_audio": ["Ce fichier n'est pas un enregistrement vocal."]},
        )
    return media


def attacher(medias):
    """Marque les médias comme utilisés : ils ne seront plus purgés ni réutilisables."""
    Media.objects.filter(id__in=[m.id for m in medias]).update(statut=Media.Statut.ATTACHE)
    for media in medias:
        media.statut = Media.Statut.ATTACHE


# ---------------------------------------------------------------------------
# Suppression / purge
# ---------------------------------------------------------------------------


def _supprimer_fichiers(media):
    for champ in (media.fichier, media.miniature):
        if champ:
            try:
                champ.storage.delete(champ.name)
            except Exception:
                logger.exception("Impossible de supprimer le fichier %s", champ.name)


def supprimer_media(media):
    """Supprime le média puis ses fichiers, une fois la suppression validée en base."""
    media.delete()
    # Les FieldFile gardent nom et stockage après delete() : les fichiers restent supprimables.
    transaction.on_commit(lambda: _supprimer_fichiers(media))


def purger_medias_temporaires(avant, simulation=False):
    """Supprime les médias TEMPORAIRE créés avant `avant`. Renvoie leur nombre."""
    medias = Media.objects.filter(statut=Media.Statut.TEMPORAIRE, cree_le__lt=avant)
    if simulation:
        return medias.count()
    nombre = 0
    for media in medias.iterator():
        with transaction.atomic():
            supprimer_media(media)
        nombre += 1
    return nombre
