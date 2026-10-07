"""Logique métier du référentiel : import CSV des secteurs."""

from django.core.exceptions import ValidationError

from apps.accounts.models import ServiceMunicipal
from apps.core.import_csv import ImportRefuse, executer, lire_booleen, lire_csv

from .models import Secteur, valider_couleur

BOOLEENS = ["pour_signalement", "pour_suggestion", "pour_realisation"]
TEXTES = ["description", "icone", "couleur"]
COLONNES_OBLIGATOIRES = ["code", "nom"]
COLONNES_FACULTATIVES = [*TEXTES, *BOOLEENS, "service_par_defaut", "ordre"]


def _valider_ligne(numero, ligne, colonnes, services, erreurs):
    valeurs = {"code": ligne["code"], "nom": ligne["nom"]}
    for obligatoire in ("code", "nom"):
        if not ligne[obligatoire]:
            erreurs.append(f"Ligne {numero} : « {obligatoire} » est vide.")

    for champ in TEXTES:
        if champ in colonnes:
            valeurs[champ] = ligne[champ]
    if valeurs.get("couleur"):
        try:
            valider_couleur(valeurs["couleur"])
        except ValidationError:
            erreurs.append(f"Ligne {numero} : couleur « {valeurs['couleur']} » invalide (attendu #RRGGBB).")

    for champ in BOOLEENS:
        if champ in colonnes:
            valeur = lire_booleen(ligne[champ])
            if valeur is None:
                erreurs.append(f"Ligne {numero} : « {champ} » doit valoir oui ou non (reçu « {ligne[champ]} »).")
            valeurs[champ] = bool(valeur)

    if "service_par_defaut" in colonnes:
        nom_service = ligne["service_par_defaut"]
        service = services.get(nom_service.casefold()) if nom_service else None
        if nom_service and service is None:
            erreurs.append(f"Ligne {numero} : service « {nom_service} » introuvable (créez-le d'abord).")
        valeurs["service_par_defaut"] = service

    if "ordre" in colonnes:
        texte = ligne["ordre"] or "0"
        if not texte.isdigit():
            erreurs.append(f"Ligne {numero} : « ordre » doit être un nombre entier positif.")
        else:
            valeurs["ordre"] = int(texte)
    return valeurs


def importer_secteurs(texte, *, simulation=False, desactiver_absents=False):
    """
    Crée ou met à jour les secteurs depuis le texte d'un CSV (reconnus par leur `code`).
    Une colonne facultative absente laisse la valeur actuelle. Renvoie le bilan ou lève ImportRefuse.
    """
    lignes, colonnes = lire_csv(texte, COLONNES_OBLIGATOIRES, COLONNES_FACULTATIVES)
    services = {s.nom.casefold(): s for s in ServiceMunicipal.objects.all()}
    existants = {s.code: s for s in Secteur.objects.all()}
    erreurs, secteurs, codes_vus, noms_vus = [], [], {}, {}

    for numero, ligne in lignes:
        valeurs = _valider_ligne(numero, ligne, colonnes, services, erreurs)
        code, nom = valeurs["code"], valeurs["nom"]
        if code in codes_vus:
            erreurs.append(f"Ligne {numero} : le code « {code} » apparaît déjà ligne {codes_vus[code]}.")
        if nom.casefold() in noms_vus:
            erreurs.append(f"Ligne {numero} : le nom « {nom} » apparaît déjà ligne {noms_vus[nom.casefold()]}.")
        codes_vus.setdefault(code, numero)
        noms_vus.setdefault(nom.casefold(), numero)
        secteurs.append(valeurs)

    # Un nom déjà pris en base par un secteur d'un autre code violerait l'unicité.
    for valeurs in secteurs:
        for autre in existants.values():
            if autre.nom.casefold() == valeurs["nom"].casefold() and autre.code != valeurs["code"]:
                erreurs.append(f"Le nom « {valeurs['nom']} » est déjà utilisé par le secteur « {autre.code} ».")
    if erreurs:
        raise ImportRefuse(erreurs)

    def enregistrer():
        bilan = {"crees": 0, "mis_a_jour": 0, "desactives": 0}
        for valeurs in secteurs:
            secteur = existants.get(valeurs["code"]) or Secteur(code=valeurs["code"])
            bilan["mis_a_jour" if secteur.pk else "crees"] += 1
            for champ, valeur in valeurs.items():
                setattr(secteur, champ, valeur)
            secteur.actif = True
            secteur.save()
        if desactiver_absents:
            codes = [valeurs["code"] for valeurs in secteurs]
            bilan["desactives"] = Secteur.objects.filter(actif=True).exclude(code__in=codes).update(actif=False)
        return bilan

    return executer(enregistrer, simulation)
