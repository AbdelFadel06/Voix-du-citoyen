"""
Charge (ou met à jour) les services municipaux d'une commune depuis un fichier CSV.

    python manage.py charger_services services.csv --commune PKO

    nom;description
    Voirie et assainissement;Routes, caniveaux, ponts et dalots
    Hygiène et salubrité;Ramassage des ordures, dépôts sauvages

Les services sont reconnus par leur nom dans la commune : relancer la commande les met à jour.
Même logique que `POST /services/import/`.
"""

from django.core.management.base import CommandError

from apps.accounts.services import importer_services
from apps.core.import_csv import CommandeImportCSV
from apps.territoire.models import Commune


class Command(CommandeImportCSV):
    help = "Charge ou met à jour les services municipaux d'une commune depuis un fichier CSV."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--commune", required=True, help="Code de la commune (créée au préalable).")

    def handle(self, *args, **options):
        try:
            commune = Commune.objects.get(code=options["commune"])
        except Commune.DoesNotExist:
            raise CommandError(f"Commune « {options['commune']} » introuvable : créez-la d'abord.")
        texte = self.lire_fichier(options["fichier"])
        bilan = self.importer(
            lambda: importer_services(
                texte, commune, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{commune.nom} — services : {bilan['crees']} créé(s), {bilan['mis_a_jour']} mis à jour, "
                f"{bilan['desactives']} désactivé(s)."
            )
        )
