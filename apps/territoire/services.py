import math
from decimal import Decimal, InvalidOperation

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.import_csv import ImportRefuse, executer, lire_csv

from .models import Arrondissement, Commune, Quartier

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


def quartier_le_plus_proche(latitude, longitude, commune_id=None):
    """
    Propose le quartier actif dont le centre est le plus proche du point, dans la commune de
    l'utilisateur (`commune_id`) ou, à défaut, dans la commune qui contient le point.
    Renvoie (quartier, distance en mètres). Le citoyen confirme ou corrige ensuite.
    """
    if commune_id is not None:
        commune = Commune.objects.get(pk=commune_id)
        if not commune.contient(latitude, longitude):
            raise ErreurMetier(CodeErreur.COORDONNEES_HORS_COMMUNE)
    else:
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


# ---------------------------------------------------------------------------
# Import CSV des quartiers (commande `charger_quartiers` et `POST /quartiers/import/`)
# ---------------------------------------------------------------------------

COLONNES_QUARTIERS = [
    "arrondissement_code",
    "arrondissement_nom",
    "quartier_code",
    "quartier_nom",
    "latitude",
    "longitude",
]


def _lire_coordonnees(numero, valeurs, commune, erreurs):
    if not (valeurs["latitude"] or valeurs["longitude"]):
        return None, None
    try:
        latitude = Decimal(valeurs["latitude"].replace(",", ".")).quantize(Decimal("0.000001"))
        longitude = Decimal(valeurs["longitude"].replace(",", ".")).quantize(Decimal("0.000001"))
    except InvalidOperation:
        erreurs.append(f"Ligne {numero} : latitude/longitude invalides.")
        return None, None
    if not commune.contient(latitude, longitude):
        erreurs.append(
            f"Ligne {numero} : le centre de « {valeurs['quartier_nom']} » "
            f"({latitude}, {longitude}) est hors de l'emprise de {commune.nom}."
        )
    return latitude, longitude


def importer_quartiers(texte, commune, *, simulation=False, desactiver_absents=False):
    """
    Crée ou met à jour les arrondissements et quartiers de `commune` depuis le texte d'un CSV
    (une ligne par quartier, rattachée par nom). Renvoie le bilan ou lève ImportRefuse.
    """
    lignes, _ = lire_csv(texte, COLONNES_QUARTIERS)
    erreurs, quartiers, deja_vus = [], [], {}
    for numero, valeurs in lignes:
        for obligatoire in ("arrondissement_nom", "quartier_nom"):
            if not valeurs[obligatoire]:
                erreurs.append(f"Ligne {numero} : « {obligatoire} » est vide.")
        valeurs["latitude"], valeurs["longitude"] = _lire_coordonnees(numero, valeurs, commune, erreurs)
        cle = (valeurs["arrondissement_nom"].casefold(), valeurs["quartier_nom"].casefold())
        if cle in deja_vus:
            erreurs.append(
                f"Ligne {numero} : « {valeurs['quartier_nom']} » apparaît déjà "
                f"ligne {deja_vus[cle]} pour le même arrondissement."
            )
        deja_vus.setdefault(cle, numero)
        quartiers.append(valeurs)
    if erreurs:
        raise ImportRefuse(erreurs)

    def enregistrer():
        bilan = {"arrondissements_crees": 0, "crees": 0, "mis_a_jour": 0, "desactives": 0}
        vus = set()
        for valeurs in quartiers:
            arrondissement, cree = Arrondissement.objects.get_or_create(
                commune=commune,
                nom=valeurs["arrondissement_nom"],
                defaults={"code": valeurs["arrondissement_code"]},
            )
            bilan["arrondissements_crees"] += cree
            if not cree and valeurs["arrondissement_code"] and arrondissement.code != valeurs["arrondissement_code"]:
                arrondissement.code = valeurs["arrondissement_code"]
                arrondissement.save(update_fields=["code", "maj_le"])
            quartier, cree = Quartier.objects.update_or_create(
                arrondissement=arrondissement,
                nom=valeurs["quartier_nom"],
                defaults={
                    "code": valeurs["quartier_code"],
                    "latitude_centre": valeurs["latitude"],
                    "longitude_centre": valeurs["longitude"],
                    "actif": True,
                },
            )
            bilan["crees" if cree else "mis_a_jour"] += 1
            vus.add(quartier.pk)
        if desactiver_absents:
            bilan["desactives"] = (
                Quartier.objects.filter(arrondissement__commune=commune, actif=True).exclude(pk__in=vus).update(actif=False)
            )
        return bilan

    return executer(enregistrer, simulation)
