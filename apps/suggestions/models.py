from django.conf import settings
from django.db import models

from apps.core.models import ModeleHorodate


class Suggestion(ModeleHorodate):
    """
    Idée d'un citoyen. Pas de statut : la mairie coche celles qu'elle juge pertinentes
    (`est_pertinente`, visible uniquement par la mairie) pour les retrouver lors des décisions.
    """

    reference = models.CharField("référence", max_length=20, unique=True, editable=False)
    titre = models.CharField("titre", max_length=150)
    description = models.TextField("description")
    secteur = models.ForeignKey(
        "referentiel.Secteur",
        on_delete=models.PROTECT,
        related_name="suggestions",
        verbose_name="secteur",
    )
    quartier = models.ForeignKey(
        "territoire.Quartier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="suggestions",
        verbose_name="quartier",
        help_text="Vide : la suggestion concerne toute la commune.",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="suggestions",
        verbose_name="auteur",
    )
    est_pertinente = models.BooleanField("jugée pertinente par la mairie", default=False, db_index=True)
    nb_soutiens = models.PositiveIntegerField("nombre de soutiens", default=0)
    medias = models.ManyToManyField(
        "medias.Media", blank=True, related_name="suggestions", verbose_name="photos"
    )
    reponse_officielle = models.TextField("réponse officielle", blank=True)
    repondu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suggestions_repondues",
        verbose_name="répondu par",
    )
    repondu_le = models.DateTimeField("répondu le", null=True, blank=True)

    class Meta:
        verbose_name = "suggestion"
        verbose_name_plural = "suggestions"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.reference} – {self.titre}"


class Soutien(ModeleHorodate):
    suggestion = models.ForeignKey(
        Suggestion, on_delete=models.CASCADE, related_name="soutiens", verbose_name="suggestion"
    )
    citoyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="soutiens",
        verbose_name="citoyen",
    )

    class Meta:
        verbose_name = "soutien"
        verbose_name_plural = "soutiens"
        constraints = [
            models.UniqueConstraint(
                fields=["suggestion", "citoyen"],
                name="soutien_unique_par_citoyen",
                violation_error_message="Vous soutenez déjà cette suggestion.",
            ),
        ]

    def __str__(self):
        return f"{self.citoyen} soutient {self.suggestion.reference}"


class SuiviSuggestion(ModeleHorodate):
    """Historique d'une suggestion : réponses officielles et notes internes."""

    class TypeEvenement(models.TextChoices):
        REPONSE = "REPONSE", "Réponse de la mairie"
        NOTE_INTERNE = "NOTE_INTERNE", "Note interne"

    suggestion = models.ForeignKey(
        Suggestion, on_delete=models.CASCADE, related_name="suivis", verbose_name="suggestion"
    )
    type_evenement = models.CharField("type d'événement", max_length=20, choices=TypeEvenement.choices)
    commentaire = models.TextField("commentaire", blank=True)
    visible_citoyen = models.BooleanField("visible par le citoyen", default=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="suivis_suggestions",
        verbose_name="auteur",
    )

    class Meta:
        verbose_name = "suivi de suggestion"
        verbose_name_plural = "suivis de suggestions"
        ordering = ["cree_le", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(type_evenement="NOTE_INTERNE") | models.Q(visible_citoyen=False),
                name="suivi_suggestion_note_interne_invisible",
                violation_error_message="Une note interne n'est jamais visible par le citoyen.",
            ),
        ]

    def __str__(self):
        return f"{self.suggestion.reference} – {self.get_type_evenement_display()}"
