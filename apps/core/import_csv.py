"""
Import de fichiers CSV, partagé par les commandes (`charger_quartiers`, `charger_secteurs`,
`charger_services`) et les endpoints d'import (`POST /…/import/`).

Comportement commun :
- séparateur « ; » ou « , » détecté automatiquement ;
- encodage UTF-8 (avec ou sans BOM), ou Windows-1252 (CSV enregistré par Excel sous Windows) ;
- numéros de ligne réels dans les messages (l'en-tête est la ligne 1) ;
- tout ou rien : la moindre erreur refuse le fichier entier (`ImportRefuse`) ;
- simulation : tout est vérifié et compté, puis annulé.

Les fonctions `importer_…` des services renvoient un bilan (dict) ou lèvent `ImportRefuse`.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

VALEURS_VRAIES = {"oui", "o", "vrai", "true", "1", "x"}
VALEURS_FAUSSES = {"non", "n", "faux", "false", "0", ""}


class ImportRefuse(Exception):
    """Le fichier est refusé ; `erreurs` contient un message par problème (avec la ligne)."""

    def __init__(self, erreurs):
        self.erreurs = list(erreurs)
        super().__init__("\n".join(self.erreurs))


class _AnnulationSimulation(Exception):
    pass


def decoder(octets):
    """Texte du fichier : UTF-8 si possible, sinon Windows-1252 (Excel sous Windows)."""
    try:
        return octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        return octets.decode("cp1252")


def lire_csv(texte, colonnes_obligatoires, colonnes_facultatives=()):
    """
    Renvoie ([(numéro de ligne, {colonne: valeur nettoyée})], colonnes présentes).
    Seules les colonnes connues sont gardées ; lève ImportRefuse si l'en-tête ne convient pas.
    """
    lignes = texte.splitlines()
    if not lignes or not lignes[0].strip():
        raise ImportRefuse(["Fichier vide : la première ligne doit contenir les noms des colonnes."])
    try:
        separateur = csv.Sniffer().sniff(lignes[0], delimiters=";,").delimiter
    except csv.Error:
        separateur = ";"  # en-tête d'une seule colonne : rien à détecter
    lecteur = csv.DictReader(lignes, delimiter=separateur)
    colonnes = {colonne.strip() for colonne in lecteur.fieldnames or []}
    manquantes = set(colonnes_obligatoires) - colonnes
    if manquantes:
        raise ImportRefuse([f"Colonnes manquantes : {', '.join(sorted(manquantes))}."])
    connues = colonnes & {*colonnes_obligatoires, *colonnes_facultatives}
    resultat = []
    for numero, ligne in enumerate(lecteur, start=2):
        propre = {(cle or "").strip(): (valeur or "").strip() for cle, valeur in ligne.items()}
        resultat.append((numero, {cle: propre.get(cle, "") for cle in connues}))
    if not resultat:
        raise ImportRefuse(["Le fichier ne contient aucune ligne de données."])
    return resultat, connues


def lire_booleen(valeur):
    """'oui', 'non', '1', '0', 'x', vide… → True / False ; None si la valeur est inconnue."""
    valeur = valeur.strip().casefold()
    if valeur in VALEURS_VRAIES:
        return True
    if valeur in VALEURS_FAUSSES:
        return False
    return None


def executer(fonction, simulation):
    """Exécute `fonction` (qui renvoie le bilan) dans une transaction, annulée en simulation."""
    resultat = None
    try:
        with transaction.atomic():
            resultat = fonction()
            if simulation:
                raise _AnnulationSimulation
    except _AnnulationSimulation:
        pass
    return {**resultat, "simulation": simulation}


class CommandeImportCSV(BaseCommand):
    """Base des commandes : lit le fichier sur le disque et affiche les erreurs ou le bilan."""

    def add_arguments(self, parser):
        parser.add_argument("fichier", type=Path, help="Chemin du fichier CSV (« ; » ou « , »).")
        parser.add_argument(
            "--simulation",
            action="store_true",
            help="Vérifie le fichier et affiche le résultat sans rien enregistrer.",
        )
        parser.add_argument(
            "--desactiver-absents",
            action="store_true",
            help="Désactive les éléments absents du fichier.",
        )

    def lire_fichier(self, chemin):
        if not chemin.exists():
            raise CommandError(f"Fichier introuvable : {chemin}")
        return decoder(chemin.read_bytes())

    def importer(self, fonction):
        """Appelle la fonction d'import du service ; renvoie le bilan ou une CommandError."""
        try:
            bilan = fonction()
        except ImportRefuse as exc:
            raise CommandError("Fichier refusé, rien n'a été enregistré :\n" + "\n".join(exc.erreurs))
        if bilan["simulation"]:
            self.stdout.write(self.style.WARNING("Simulation : aucune modification enregistrée."))
        return bilan


# ---------------------------------------------------------------------------
# Endpoints d'import (`POST /…/import/`)
# ---------------------------------------------------------------------------

TAILLE_MAX_CSV = 1024 * 1024  # 1 Mo : plusieurs milliers de lignes


def importer_depuis_requete(fichier, fonction):
    """
    Lit le fichier envoyé, appelle `fonction(texte)` du service et renvoie son bilan.
    Toute erreur devient IMPORT_CSV_INVALIDE avec la liste des problèmes dans `details.lignes`.
    """
    from .codes_erreur import CodeErreur
    from .exceptions import ErreurMetier

    if fichier.size > TAILLE_MAX_CSV:
        raise ErreurMetier(
            CodeErreur.IMPORT_CSV_INVALIDE,
            "Le fichier est trop volumineux : 1 Mo au maximum.",
            details={"lignes": ["Le fichier dépasse 1 Mo."]},
        )
    try:
        return fonction(decoder(fichier.read()))
    except ImportRefuse as exc:
        raise ErreurMetier(CodeErreur.IMPORT_CSV_INVALIDE, details={"lignes": exc.erreurs})
