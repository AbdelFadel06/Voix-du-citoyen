"""
Charge (ou met à jour) les arrondissements et quartiers d'une commune depuis un CSV.

Format (séparateur « ; » ou « , », une ligne par quartier) :

    arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude
    GOD;Godomey;TOG;Togoudo;6.401234;2.341234
    GOD;Godomey;CAL;Calavi Centre;;

latitude/longitude (centre du quartier) sont facultatives mais nécessaires pour
/quartiers/proche/. Les lignes sont rattachées par nom : relancer la commande met à jour
les codes et coordonnées sans créer de doublons. Même logique que `POST /quartiers/import/`.
"""

from django.core.management.base import CommandError

from apps.core.import_csv import CommandeImportCSV
from apps.territoire.models import Commune
from apps.territoire.services import importer_quartiers


class Command(CommandeImportCSV):
    help = "Charge les arrondissements et quartiers d'une commune depuis un fichier CSV."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--commune", required=True, help="Code de la commune (créée au préalable).")

    def handle(self, *args, **options):
        try:
            commune = Commune.objects.get(code=options["commune"])
        except Commune.DoesNotExist:
            raise CommandError(
                f"Commune « {options['commune']} » introuvable : créez-la d'abord (avec son emprise lat/lng)."
            )
        texte = self.lire_fichier(options["fichier"])
        bilan = self.importer(
            lambda: importer_quartiers(
                texte, commune, simulation=options["simulation"], desactiver_absents=options["desactiver_absents"]
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{commune.nom} : {bilan['arrondissements_crees']} arrondissement(s) créé(s), "
                f"{bilan['crees']} quartier(s) créé(s), {bilan['mis_a_jour']} mis à jour, "
                f"{bilan['desactives']} désactivé(s)."
            )
        )
