"""
Charge (ou met à jour) les secteurs depuis un fichier CSV.

Seules les colonnes `code` et `nom` sont obligatoires ; une colonne absente du fichier
laisse la valeur actuelle inchangée (ou la valeur par défaut pour un nouveau secteur).

    code;nom;description;icone;couleur;pour_signalement;pour_suggestion;pour_realisation;service_par_defaut;ordre
    VOIRIE;Voirie;Routes, nids-de-poule;route;#F57C00;oui;oui;oui;Voirie et assainissement;1
    ECLAIRAGE;Éclairage public;;lampadaire;#FBC02D;oui;non;oui;;2

- Les secteurs sont reconnus par leur `code` : relancer la commande les met à jour.
- Booléens : oui/non, 1/0, vrai/faux, x ; une cellule vide vaut « non ».
- `service_par_defaut` : nom exact d'un service municipal existant, ou vide.
- Les secteurs présents dans le fichier sont (ré)activés.
Même logique que `POST /secteurs/import/`.
"""

from apps.core.import_csv import CommandeImportCSV
from apps.referentiel.services import importer_secteurs


class Command(CommandeImportCSV):
    help = "Charge ou met à jour les secteurs depuis un fichier CSV."

    def handle(self, *args, **options):
        texte = self.lire_fichier(options["fichier"])
        bilan = self.importer(
            lambda: importer_secteurs(
                texte, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Secteurs : {bilan['crees']} créé(s), {bilan['mis_a_jour']} mis à jour, "
                f"{bilan['desactives']} désactivé(s)."
            )
        )
