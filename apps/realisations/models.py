from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from apps.core.models import ModeleHorodate


class Realisation(ModeleHorodate):
    """Ce que la mairie a entrepris ou réalisé ; invisible du public tant que `publie` est faux."""

    class Statut(models.TextChoices):
        PLANIFIEE = "PLANIFIEE", "Planifiée"
        EN_COURS = "EN_COURS", "En cours"
        TERMINEE = "TERMINEE", "Terminée"
        SUSPENDUE = "SUSPENDUE", "Suspendue"

    reference = models.CharField("référence", max_length=20, unique=True, editable=False)
    titre = models.CharField("titre", max_length=200)
    description = models.TextField("description")
    secteur = models.ForeignKey(
        "referentiel.Secteur",
        on_delete=models.PROTECT,
        related_name="realisations",
        verbose_name="secteur",
    )
    statut = models.CharField("statut", max_length=20, choices=Statut.choices, default=Statut.PLANIFIEE)
    taux_avancement = models.PositiveSmallIntegerField(
        "taux d'avancement (%)", default=0, validators=[MaxValueValidator(100)]
    )
    date_debut_prevue = models.DateField("début prévu", null=True, blank=True)
    date_fin_prevue = models.DateField("fin prévue", null=True, blank=True)
    date_debut_reelle = models.DateField("début réel", null=True, blank=True)
    date_fin_reelle = models.DateField("fin réelle", null=True, blank=True)
    budget = models.DecimalField("budget (FCFA)", max_digits=14, decimal_places=0, null=True, blank=True)
    source_financement = models.CharField("source de financement", max_length=255, blank=True)
    prestataire = models.CharField("prestataire", max_length=255, blank=True)
    latitude = models.DecimalField("latitude", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("longitude", max_digits=9, decimal_places=6, null=True, blank=True)
    quartiers = models.ManyToManyField(
        "territoire.Quartier", related_name="realisations", verbose_name="quartiers concernés"
    )
    signalements = models.ManyToManyField(
        "signalements.Signalement",
        blank=True,
        related_name="realisations",
        verbose_name="signalements liés",
    )
    suggestions = models.ManyToManyField(
        "suggestions.Suggestion",
        blank=True,
        related_name="realisations",
        verbose_name="suggestions liées",
    )
    publie = models.BooleanField("publiée", default=False)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="realisations_creees",
        verbose_name="créée par",
    )

    class Meta:
        verbose_name = "réalisation"
        verbose_name_plural = "réalisations"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["publie", "statut"], name="realisation_publie_statut_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(taux_avancement__lte=100),
                name="realisation_taux_max_100",
                violation_error_message="Le taux d'avancement ne peut pas dépasser 100 %.",
            ),
            models.CheckConstraint(
                condition=models.Q(date_debut_prevue__isnull=True)
                | models.Q(date_fin_prevue__isnull=True)
                | models.Q(date_fin_prevue__gte=models.F("date_debut_prevue")),
                name="realisation_dates_prevues_ordonnees",
                violation_error_message="La fin prévue ne peut pas précéder le début prévu.",
            ),
            models.CheckConstraint(
                condition=models.Q(date_debut_reelle__isnull=True)
                | models.Q(date_fin_reelle__isnull=True)
                | models.Q(date_fin_reelle__gte=models.F("date_debut_reelle")),
                name="realisation_dates_reelles_ordonnees",
                violation_error_message="La fin réelle ne peut pas précéder le début réel.",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__isnull=True, longitude__isnull=True)
                | models.Q(latitude__isnull=False, longitude__isnull=False),
                name="realisation_position_complete",
                violation_error_message="La latitude et la longitude vont ensemble.",
            ),
            models.CheckConstraint(
                condition=models.Q(budget__isnull=True) | models.Q(budget__gte=0),
                name="realisation_budget_positif",
                violation_error_message="Le budget ne peut pas être négatif.",
            ),
        ]

    def __str__(self):
        return f"{self.reference} – {self.titre}"


class RealisationMedia(ModeleHorodate):
    """Photo ou vidéo d'une réalisation, classée par phase du chantier."""

    class Phase(models.TextChoices):
        AVANT = "AVANT", "Avant les travaux"
        PENDANT = "PENDANT", "Pendant les travaux"
        APRES = "APRES", "Après les travaux"

    realisation = models.ForeignKey(
        Realisation, on_delete=models.CASCADE, related_name="medias", verbose_name="réalisation"
    )
    media = models.OneToOneField(
        "medias.Media", on_delete=models.CASCADE, related_name="realisation_media", verbose_name="média"
    )
    phase = models.CharField("phase", max_length=10, choices=Phase.choices)
    legende = models.CharField("légende", max_length=255, blank=True)
    ordre = models.PositiveSmallIntegerField("ordre d'affichage", default=0)

    class Meta:
        verbose_name = "média de réalisation"
        verbose_name_plural = "médias de réalisation"
        ordering = ["ordre", "id"]

    def __str__(self):
        return f"{self.realisation.reference} – {self.get_phase_display()}"
