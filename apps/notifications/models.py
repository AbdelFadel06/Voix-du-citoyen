from django.conf import settings
from django.db import models

from apps.core.models import ModeleHorodate


class Notification(ModeleHorodate):
    class Type(models.TextChoices):
        STATUT_SIGNALEMENT = "STATUT_SIGNALEMENT", "Changement de statut d'un signalement"
        REPONSE_SIGNALEMENT = "REPONSE_SIGNALEMENT", "Réponse de la mairie à un signalement"
        REPONSE_SUGGESTION = "REPONSE_SUGGESTION", "Réponse de la mairie à une suggestion"
        NOUVELLE_REALISATION = "NOUVELLE_REALISATION", "Nouvelle réalisation publiée"

    class Cible(models.TextChoices):
        SIGNALEMENT = "signalement", "Signalement"
        SUGGESTION = "suggestion", "Suggestion"
        REALISATION = "realisation", "Réalisation"

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="destinataire",
    )
    type = models.CharField("type", max_length=30, choices=Type.choices)
    titre = models.CharField("titre", max_length=150)
    message = models.TextField("message")
    # Écran à ouvrir dans l'application mobile.
    cible_type = models.CharField("type de cible", max_length=20, choices=Cible.choices)
    cible_id = models.BigIntegerField("identifiant de la cible")
    lu = models.BooleanField("lue", default=False)
    envoye_push = models.BooleanField("envoyée en push", default=False)

    class Meta:
        verbose_name = "notification"
        verbose_name_plural = "notifications"
        ordering = ["-cree_le", "-id"]
        indexes = [models.Index(fields=["destinataire", "lu"], name="notification_destinataire_lu")]

    def __str__(self):
        return f"{self.get_type_display()} → {self.destinataire}"
