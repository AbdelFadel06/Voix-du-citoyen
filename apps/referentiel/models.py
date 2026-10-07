from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import ModeleHorodate

valider_couleur = RegexValidator(
    r"^#[0-9A-Fa-f]{6}$", "La couleur doit être au format hexadécimal, par exemple #1E88E5."
)


class Secteur(ModeleHorodate):
    nom = models.CharField(
        "nom",
        max_length=100,
        unique=True,
        error_messages={"unique": "Un secteur porte déjà ce nom."},
    )
    code = models.CharField(
        "code",
        max_length=30,
        unique=True,
        error_messages={"unique": "Un secteur utilise déjà ce code."},
    )
    description = models.TextField("description", blank=True)
    icone = models.CharField(
        "icône", max_length=50, blank=True, help_text="Nom de l'icône affichée par les applications."
    )
    couleur = models.CharField("couleur", max_length=7, blank=True, validators=[valider_couleur])
    pour_signalement = models.BooleanField("utilisable pour les signalements", default=False)
    pour_suggestion = models.BooleanField("utilisable pour les suggestions", default=False)
    pour_realisation = models.BooleanField("utilisable pour les réalisations", default=False)
    service_par_defaut = models.ForeignKey(
        "accounts.ServiceMunicipal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secteurs",
        verbose_name="service par défaut",
        help_text="Service auquel les nouveaux signalements de ce secteur sont assignés.",
    )
    ordre = models.PositiveSmallIntegerField("ordre d'affichage", default=0)
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "secteur"
        verbose_name_plural = "secteurs"
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom
