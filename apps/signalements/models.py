from django.conf import settings
from django.db import models

from apps.core.models import ModeleHorodate


class Signalement(ModeleHorodate):
    class ModeLocalisation(models.TextChoices):
        GPS = "GPS", "Position GPS"
        MANUEL = "MANUEL", "Quartier et repère"

    class Statut(models.TextChoices):
        SOUMIS = "SOUMIS", "Soumis"
        RECU = "RECU", "Reçu"
        EN_COURS = "EN_COURS", "En cours de traitement"
        RESOLU = "RESOLU", "Résolu"
        REJETE = "REJETE", "Rejeté"
        DOUBLON = "DOUBLON", "Doublon"

    class Priorite(models.TextChoices):
        BASSE = "BASSE", "Basse"
        NORMALE = "NORMALE", "Normale"
        HAUTE = "HAUTE", "Haute"
        URGENTE = "URGENTE", "Urgente"

    # Statuts après lesquels le dossier est clos.
    STATUTS_CLOTURES = {Statut.RESOLU, Statut.REJETE, Statut.DOUBLON}

    reference = models.CharField("référence", max_length=20, unique=True, editable=False)
    commune = models.ForeignKey(
        "territoire.Commune",
        on_delete=models.PROTECT,
        related_name="signalements",
        verbose_name="commune",
        help_text="Commune de l'auteur au moment de l'envoi (déduite du compte, jamais envoyée).",
    )
    titre = models.CharField("titre", max_length=150, blank=True)
    titre_genere = models.BooleanField("titre généré automatiquement", default=False)
    description_texte = models.TextField("description écrite", blank=True)
    description_audio = models.OneToOneField(
        "medias.Media",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signalement_audio",
        verbose_name="description vocale",
    )
    secteur = models.ForeignKey(
        "referentiel.Secteur",
        on_delete=models.PROTECT,
        related_name="signalements",
        verbose_name="secteur",
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="signalements",
        verbose_name="auteur",
    )
    mode_localisation = models.CharField(
        "mode de localisation", max_length=10, choices=ModeLocalisation.choices
    )
    latitude = models.DecimalField("latitude", max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField("longitude", max_digits=9, decimal_places=6, null=True, blank=True)
    precision_gps = models.PositiveIntegerField("précision GPS (m)", null=True, blank=True)
    quartier = models.ForeignKey(
        "territoire.Quartier",
        on_delete=models.PROTECT,
        related_name="signalements",
        verbose_name="quartier",
    )
    repere = models.CharField("repère", max_length=255, blank=True)
    statut = models.CharField("statut", max_length=20, choices=Statut.choices, default=Statut.SOUMIS)
    priorite = models.CharField(
        "priorité", max_length=10, choices=Priorite.choices, default=Priorite.NORMALE
    )
    service_assigne = models.ForeignKey(
        "accounts.ServiceMunicipal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signalements_assignes",
        verbose_name="service assigné",
    )
    agent_assigne = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signalements_assignes",
        verbose_name="agent assigné",
    )
    doublon_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doublons",
        verbose_name="doublon de",
    )
    medias = models.ManyToManyField(
        "medias.Media", blank=True, related_name="signalements", verbose_name="photos et vidéos"
    )
    date_resolution = models.DateTimeField("date de résolution", null=True, blank=True)

    class Meta:
        verbose_name = "signalement"
        verbose_name_plural = "signalements"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["statut"], name="signalement_statut_idx")]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(description_texte="") | models.Q(description_audio__isnull=False),
                name="signalement_avec_description",
                violation_error_message="Une description écrite ou vocale est obligatoire.",
            ),
            models.CheckConstraint(
                condition=~models.Q(mode_localisation="GPS")
                | models.Q(latitude__isnull=False, longitude__isnull=False, precision_gps__isnull=False),
                name="signalement_gps_complet",
                violation_error_message="La position GPS (latitude, longitude, précision) est incomplète.",
            ),
        ]

    def __str__(self):
        return f"{self.reference} – {self.titre}"

    @property
    def est_cloture(self):
        return self.statut in self.STATUTS_CLOTURES


class SuiviSignalement(ModeleHorodate):
    """Historique d'un signalement : changements de statut, assignations, réponses, notes internes."""

    class TypeEvenement(models.TextChoices):
        CHANGEMENT_STATUT = "CHANGEMENT_STATUT", "Changement de statut"
        ASSIGNATION = "ASSIGNATION", "Assignation"
        REPONSE = "REPONSE", "Réponse de la mairie"
        NOTE_INTERNE = "NOTE_INTERNE", "Note interne"

    signalement = models.ForeignKey(
        Signalement, on_delete=models.CASCADE, related_name="suivis", verbose_name="signalement"
    )
    type_evenement = models.CharField("type d'événement", max_length=20, choices=TypeEvenement.choices)
    ancien_statut = models.CharField(
        "ancien statut", max_length=20, choices=Signalement.Statut.choices, blank=True
    )
    nouveau_statut = models.CharField(
        "nouveau statut", max_length=20, choices=Signalement.Statut.choices, blank=True
    )
    commentaire = models.TextField("commentaire", blank=True)
    visible_citoyen = models.BooleanField("visible par le citoyen", default=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="suivis_signalements",
        verbose_name="auteur",
    )

    class Meta:
        verbose_name = "suivi de signalement"
        verbose_name_plural = "suivis de signalements"
        ordering = ["cree_le", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(type_evenement="NOTE_INTERNE") | models.Q(visible_citoyen=False),
                name="suivi_signalement_note_interne_invisible",
                violation_error_message="Une note interne n'est jamais visible par le citoyen.",
            ),
        ]

    def __str__(self):
        return f"{self.signalement.reference} – {self.get_type_evenement_display()}"
