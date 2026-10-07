from django.db import models

from apps.core.models import ModeleHorodate


class Commune(ModeleHorodate):
    nom = models.CharField("nom", max_length=100)
    code = models.CharField("code", max_length=20, unique=True)
    departement = models.CharField("département", max_length=100)
    # Emprise de la commune : sert à rejeter les coordonnées GPS hors territoire.
    lat_min = models.DecimalField("latitude minimale", max_digits=9, decimal_places=6)
    lat_max = models.DecimalField("latitude maximale", max_digits=9, decimal_places=6)
    lng_min = models.DecimalField("longitude minimale", max_digits=9, decimal_places=6)
    lng_max = models.DecimalField("longitude maximale", max_digits=9, decimal_places=6)

    class Meta:
        verbose_name = "commune"
        verbose_name_plural = "communes"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def contient(self, latitude, longitude):
        """Indique si le point (latitude, longitude) est dans l'emprise de la commune."""
        return (
            self.lat_min <= latitude <= self.lat_max
            and self.lng_min <= longitude <= self.lng_max
        )


class Arrondissement(ModeleHorodate):
    commune = models.ForeignKey(
        Commune,
        on_delete=models.PROTECT,
        related_name="arrondissements",
        verbose_name="commune",
    )
    nom = models.CharField("nom", max_length=100)
    code = models.CharField("code", max_length=20)

    class Meta:
        verbose_name = "arrondissement"
        verbose_name_plural = "arrondissements"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["commune", "nom"],
                name="arrondissement_unique_par_commune",
                violation_error_message="Cet arrondissement existe déjà dans cette commune.",
            ),
        ]

    def __str__(self):
        return self.nom


class Quartier(ModeleHorodate):
    arrondissement = models.ForeignKey(
        Arrondissement,
        on_delete=models.PROTECT,
        related_name="quartiers",
        verbose_name="arrondissement",
    )
    nom = models.CharField("nom", max_length=100)
    code = models.CharField("code", max_length=20)
    latitude_centre = models.DecimalField(
        "latitude du centre", max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude_centre = models.DecimalField(
        "longitude du centre", max_digits=9, decimal_places=6, null=True, blank=True
    )
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "quartier"
        verbose_name_plural = "quartiers"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["arrondissement", "nom"],
                name="quartier_unique_par_arrondissement",
                violation_error_message="Ce quartier existe déjà dans cet arrondissement.",
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.arrondissement.nom})"
