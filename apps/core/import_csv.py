"""
Base commune des commandes de chargement depuis un fichier CSV
(`charger_quartiers`, `charger_secteurs`…).

Comportement partagé :
- séparateur « ; » ou « , » détecté automatiquement, encodage UTF-8 (BOM d'Excel accepté) ;
- numéros de ligne réels dans les messages d'erreur (l'en-tête est la ligne 1) ;
- tout ou rien : la moindre erreur refuse le fichier entier ;
- `--simulation` : tout est vérifié et compté, puis annulé.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

VALEURS_VRAIES = {"oui", "o", "vrai", "true", "1", "x"}
VALEURS_FAUSSES = {"non", "n", "faux", "false", "0", ""}


class _AnnulationSimulation(Exception):
    pass


class CommandeImportCSV(BaseCommand):
    #: Colonnes qui doivent figurer dans l'en-tête du fichier.
    colonnes_obligatoires = []
    #: Colonnes reconnues en plus des obligatoires.
    colonnes_facultatives = []

    def add_arguments(self, parser):
        parser.add_argument("fichier", type=Path, help="Chemin du fichier CSV (UTF-8, « ; » ou « , »).")
        parser.add_argument(
            "--simulation",
            action="store_true",
            help="Vérifie le fichier et affiche le résultat sans rien enregistrer.",
        )

    # ------------------------------------------------------------------

    def lire(self, chemin):
        """Renvoie [(numéro de ligne, {colonne: valeur nettoyée})] et l'ensemble des colonnes."""
        if not chemin.exists():
            raise CommandError(f"Fichier introuvable : {chemin}")
        texte = chemin.read_text(encoding="utf-8-sig")
        lignes = texte.splitlines()
        if not lignes or not lignes[0].strip():
            raise CommandError("Fichier vide : la première ligne doit contenir les noms des colonnes.")
        try:
            separateur = csv.Sniffer().sniff(lignes[0], delimiters=";,").delimiter
        except csv.Error:
            separateur = ";"  # en-tête d'une seule colonne : rien à détecter
        lecteur = csv.DictReader(lignes, delimiter=separateur)
        colonnes = {colonne.strip() for colonne in lecteur.fieldnames or []}
        manquantes = set(self.colonnes_obligatoires) - colonnes
        if manquantes:
            raise CommandError(f"Colonnes manquantes : {', '.join(sorted(manquantes))}.")
        connues = colonnes & set(self.colonnes_obligatoires + self.colonnes_facultatives)
        resultat = []
        for numero, ligne in enumerate(lecteur, start=2):
            propre = {(cle or "").strip(): (valeur or "").strip() for cle, valeur in ligne.items()}
            resultat.append((numero, {cle: propre.get(cle, "") for cle in connues}))
        return resultat, connues

    def refuser_si_erreurs(self, erreurs):
        if erreurs:
            raise CommandError("Fichier refusé, rien n'a été enregistré :\n" + "\n".join(erreurs))

    def enregistrer_ou_simuler(self, fonction, simulation):
        """Exécute `fonction` dans une transaction, annulée en mode simulation."""
        try:
            with transaction.atomic():
                resultat = fonction()
                if simulation:
                    raise _AnnulationSimulation
        except _AnnulationSimulation:
            self.stdout.write(self.style.WARNING("Simulation : aucune modification enregistrée."))
        return resultat


def lire_booleen(valeur):
    """'oui', 'non', '1', '0', 'x', vide… → True / False ; None si la valeur est inconnue."""
    valeur = valeur.strip().casefold()
    if valeur in VALEURS_VRAIES:
        return True
    if valeur in VALEURS_FAUSSES:
        return False
    return None
