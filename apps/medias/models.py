import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ModeleHorodate


def _chemin(dossier, filename):
    return f"medias/{dossier}/{timezone.now():%Y/%m}/{filename}"


def chemin_fichier(instance, filename):
    # Le nom est construit par le service (uuid + extension déduite du type réel).
    return _chemin(instance.type.lower(), filename)


def chemin_miniature(instance, filename):
    return _chemin("miniatures", filename)


class Media(ModeleHorodate):
    """
    Fichier envoyé par un utilisateur (photo, vidéo, enregistrement vocal).
    Envoyé seul d'abord (statut TEMPORAIRE), puis rattaché à un signalement, une
    suggestion ou une réalisation (statut ATTACHE). Les TEMPORAIRE de plus de 24 h sont purgés.
    """

    class Type(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Vidéo"
        AUDIO = "AUDIO", "Audio"

    class Statut(models.TextChoices):
        TEMPORAIRE = "TEMPORAIRE", "Temporaire"
        ATTACHE = "ATTACHE", "Attaché"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="medias",
        verbose_name="auteur",
    )
    type = models.CharField("type", max_length=10, choices=Type.choices)
    fichier = models.FileField("fichier", upload_to=chemin_fichier, max_length=255)
    miniature = models.ImageField(
        "miniature", upload_to=chemin_miniature, max_length=255, null=True, blank=True
    )
    mime_type = models.CharField("type MIME", max_length=100)
    taille_octets = models.PositiveIntegerField("taille (octets)")
    duree_secondes = models.PositiveIntegerField("durée (secondes)", null=True, blank=True)
    largeur = models.PositiveIntegerField("largeur (px)", null=True, blank=True)
    hauteur = models.PositiveIntegerField("hauteur (px)", null=True, blank=True)
    statut = models.CharField(
        "statut", max_length=20, choices=Statut.choices, default=Statut.TEMPORAIRE
    )

    class Meta:
        verbose_name = "média"
        verbose_name_plural = "médias"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["statut", "cree_le"], name="media_statut_cree_le_idx")]

    def __str__(self):
        return f"{self.get_type_display()} {self.id}"
