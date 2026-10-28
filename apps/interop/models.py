from django.conf import settings
from django.db import models

from apps.core.models import ModeleHorodate


class Institution(ModeleHorodate):
    """
    Mairie connectée depuis une application tierce (plateforme IBDC des mairies).

    Table de correspondance entre l'identifiant de l'institution chez IBDC et une commune de
    Voix du Citoyen : IBDC n'envoie que sa clé, l'API en déduit l'institution et la commune.
    Les actions d'IBDC sont enregistrées au nom d'un **compte technique** (admin mairie de la
    commune, sans mot de passe utilisable).
    """

    id_externe = models.CharField(
        "identifiant chez IBDC",
        max_length=64,
        unique=True,
        help_text="Identifiant de l'institution (mairie) dans la plateforme IBDC.",
    )
    nom = models.CharField("nom", max_length=150)
    commune = models.ForeignKey(
        "territoire.Commune", on_delete=models.PROTECT, related_name="institutions", verbose_name="commune"
    )
    compte = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="institution",
        verbose_name="compte technique",
    )
    actif = models.BooleanField("active", default=True, help_text="Décocher coupe immédiatement l'accès par clé.")
    # La clé n'est jamais stockée : seulement son préfixe (pour la retrouver) et son empreinte.
    cle_prefixe = models.CharField("préfixe de la clé", max_length=16, unique=True, editable=False)
    cle_empreinte = models.CharField("empreinte de la clé", max_length=64, editable=False)
    cle_generee_le = models.DateTimeField("clé générée le", null=True, editable=False)

    class Meta:
        verbose_name = "institution"
        verbose_name_plural = "institutions"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.commune})"
