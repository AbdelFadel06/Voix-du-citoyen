from django.db import models


class ModeleHorodate(models.Model):
    """Ajoute les dates de création et de dernière modification."""

    cree_le = models.DateTimeField("créé le", auto_now_add=True, db_index=True)
    maj_le = models.DateTimeField("mis à jour le", auto_now=True)

    class Meta:
        abstract = True
