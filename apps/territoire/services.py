import math

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier

from .models import Commune, Quartier

RAYON_TERRE_METRES = 6_371_000


def distance_metres(lat1, lng1, lat2, lng2):
    """Distance à vol d'oiseau (formule de haversine), en mètres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * RAYON_TERRE_METRES * math.asin(math.sqrt(a))


def commune_contenant(latitude, longitude):
    """Renvoie la commune dont l'emprise contient le point, ou lève COORDONNEES_HORS_COMMUNE."""
    for commune in Commune.objects.all():
        if commune.contient(latitude, longitude):
            return commune
    raise ErreurMetier(CodeErreur.COORDONNEES_HORS_COMMUNE)


def quartier_le_plus_proche(latitude, longitude):
    """
    Propose le quartier actif dont le centre est le plus proche du point.
    Renvoie (quartier, distance en mètres). Le citoyen confirme ou corrige ensuite.
    """
    commune = commune_contenant(latitude, longitude)
    quartiers = Quartier.objects.select_related("arrondissement").filter(
        arrondissement__commune=commune,
        actif=True,
        latitude_centre__isnull=False,
        longitude_centre__isnull=False,
    )
    proches = [
        (q, distance_metres(latitude, longitude, float(q.latitude_centre), float(q.longitude_centre)))
        for q in quartiers
    ]
    if not proches:
        raise ErreurMetier(
            CodeErreur.RESSOURCE_INTROUVABLE,
            "Aucun quartier localisé n'est disponible. Choisissez votre quartier dans la liste.",
        )
    return min(proches, key=lambda element: element[1])
