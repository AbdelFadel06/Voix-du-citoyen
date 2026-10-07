"""
Charge (ou met à jour) les arrondissements et quartiers d'une commune depuis un CSV.

Format (séparateur « ; » ou « , », encodage UTF-8, une ligne par quartier) :

    arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude
    GOD;Godomey;TOG;Togoudo;6.401234;2.341234
    GOD;Godomey;CAL;Calavi Centre;;

latitude/longitude (centre du quartier) sont facultatives mais nécessaires pour
/quartiers/proche/. Les lignes sont rattachées par nom : relancer la commande met à jour
les codes et coordonnées sans créer de doublons.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import CommandError

from apps.core.import_csv import CommandeImportCSV
from apps.territoire.models import Arrondissement, Commune, Quartier

COLONNES = [
    "arrondissement_code",
    "arrondissement_nom",
    "quartier_code",
    "quartier_nom",
    "latitude",
    "longitude",
]


class Command(CommandeImportCSV):
    help = "Charge les arrondissements et quartiers d'une commune depuis un fichier CSV."
    colonnes_obligatoires = COLONNES

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--commune", required=True, help="Code de la commune (créée au préalable dans l'admin)."
        )
        parser.add_argument(
            "--desactiver-absents",
            action="store_true",
            help="Désactive les quartiers de la commune absents du fichier.",
        )

    def handle(self, *args, **options):
        try:
            commune = Commune.objects.get(code=options["commune"])
        except Commune.DoesNotExist:
            raise CommandError(
                f"Commune « {options['commune']} » introuvable : créez-la d'abord dans l'admin "
                "(avec son emprise lat/lng)."
            )

        lignes, _ = self.lire(options["fichier"])
        erreurs = []
        quartiers = []
        deja_vus = {}
        for numero, ligne in lignes:
            valeurs = self.valider(numero, ligne, commune, erreurs)
            cle = (valeurs["arrondissement_nom"].casefold(), valeurs["quartier_nom"].casefold())
            if cle in deja_vus:
                erreurs.append(
                    f"Ligne {numero} : « {valeurs['quartier_nom']} » apparaît déjà "
                    f"ligne {deja_vus[cle]} pour le même arrondissement."
                )
            deja_vus.setdefault(cle, numero)
            quartiers.append(valeurs)
        self.refuser_si_erreurs(erreurs)

        bilan = {"arrondissements_crees": 0, "quartiers_crees": 0, "quartiers_maj": 0, "desactives": 0}
        self.enregistrer_ou_simuler(
            lambda: self.enregistrer(commune, quartiers, bilan, options["desactiver_absents"]),
            options["simulation"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{commune.nom} : {bilan['arrondissements_crees']} arrondissement(s) créé(s), "
                f"{bilan['quartiers_crees']} quartier(s) créé(s), "
                f"{bilan['quartiers_maj']} mis à jour, {bilan['desactives']} désactivé(s)."
            )
        )

    # ------------------------------------------------------------------

    def valider(self, numero, ligne, commune, erreurs):
        valeurs = dict(ligne)
        for obligatoire in ("arrondissement_nom", "quartier_nom"):
            if not valeurs[obligatoire]:
                erreurs.append(f"Ligne {numero} : « {obligatoire} » est vide.")

        latitude = longitude = None
        if valeurs["latitude"] or valeurs["longitude"]:
            try:
                latitude = Decimal(valeurs["latitude"].replace(",", ".")).quantize(Decimal("0.000001"))
                longitude = Decimal(valeurs["longitude"].replace(",", ".")).quantize(Decimal("0.000001"))
            except InvalidOperation:
                erreurs.append(f"Ligne {numero} : latitude/longitude invalides.")
            else:
                if not commune.contient(latitude, longitude):
                    erreurs.append(
                        f"Ligne {numero} : le centre de « {valeurs['quartier_nom']} » "
                        f"({latitude}, {longitude}) est hors de l'emprise de {commune.nom}."
                    )
        return {**valeurs, "latitude": latitude, "longitude": longitude}

    def enregistrer(self, commune, quartiers, bilan, desactiver_absents):
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
            bilan["quartiers_crees" if cree else "quartiers_maj"] += 1
            vus.add(quartier.pk)

        if desactiver_absents:
            bilan["desactives"] = (
                Quartier.objects.filter(arrondissement__commune=commune, actif=True)
                .exclude(pk__in=vus)
                .update(actif=False)
            )
