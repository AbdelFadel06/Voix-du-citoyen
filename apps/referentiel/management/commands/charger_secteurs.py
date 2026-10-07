"""
Charge (ou met à jour) les secteurs depuis un fichier CSV.

Seules les colonnes `code` et `nom` sont obligatoires ; une colonne absente du fichier
laisse la valeur actuelle inchangée (ou la valeur par défaut pour un nouveau secteur).

    code;nom;description;icone;couleur;pour_signalement;pour_suggestion;pour_realisation;service_par_defaut;ordre
    VOIRIE;Voirie;Routes, nids-de-poule;route;#F57C00;oui;oui;oui;Voirie et assainissement;1
    ECLAIRAGE;Éclairage public;;lampadaire;#FBC02D;oui;non;oui;;2

- Les secteurs sont reconnus par leur `code` : relancer la commande les met à jour.
- Booléens : oui/non, 1/0, vrai/faux, x ; une cellule vide vaut « non ».
- `service_par_defaut` : nom exact d'un service municipal existant (créé dans l'admin), ou vide.
- Les secteurs présents dans le fichier sont (ré)activés.
"""

from django.core.exceptions import ValidationError

from apps.accounts.models import ServiceMunicipal
from apps.core.import_csv import CommandeImportCSV, lire_booleen
from apps.referentiel.models import Secteur, valider_couleur

BOOLEENS = ["pour_signalement", "pour_suggestion", "pour_realisation"]
TEXTES = ["description", "icone", "couleur"]


class Command(CommandeImportCSV):
    help = "Charge ou met à jour les secteurs depuis un fichier CSV."
    colonnes_obligatoires = ["code", "nom"]
    colonnes_facultatives = [*TEXTES, *BOOLEENS, "service_par_defaut", "ordre"]

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--desactiver-absents",
            action="store_true",
            help="Désactive les secteurs absents du fichier.",
        )

    def handle(self, *args, **options):
        lignes, colonnes = self.lire(options["fichier"])
        services = {s.nom.casefold(): s for s in ServiceMunicipal.objects.all()}
        existants = {s.code: s for s in Secteur.objects.all()}
        erreurs = []
        secteurs = []
        codes_vus, noms_vus = {}, {}

        for numero, ligne in lignes:
            valeurs = self.valider(numero, ligne, colonnes, services, erreurs)
            code, nom = valeurs["code"], valeurs["nom"]
            if code in codes_vus:
                erreurs.append(f"Ligne {numero} : le code « {code} » apparaît déjà ligne {codes_vus[code]}.")
            if nom.casefold() in noms_vus:
                erreurs.append(
                    f"Ligne {numero} : le nom « {nom} » apparaît déjà ligne {noms_vus[nom.casefold()]}."
                )
            codes_vus.setdefault(code, numero)
            noms_vus.setdefault(nom.casefold(), numero)
            secteurs.append(valeurs)

        # Un nom déjà pris en base par un secteur d'un autre code violerait l'unicité.
        for valeurs in secteurs:
            for autre in existants.values():
                if autre.nom.casefold() == valeurs["nom"].casefold() and autre.code != valeurs["code"]:
                    erreurs.append(
                        f"Le nom « {valeurs['nom']} » est déjà utilisé par le secteur « {autre.code} »."
                    )
        self.refuser_si_erreurs(erreurs)

        bilan = self.enregistrer_ou_simuler(
            lambda: self.enregistrer(secteurs, existants, options["desactiver_absents"]),
            options["simulation"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Secteurs : {bilan['crees']} créé(s), {bilan['maj']} mis à jour, "
                f"{bilan['desactives']} désactivé(s)."
            )
        )

    # ------------------------------------------------------------------

    def valider(self, numero, ligne, colonnes, services, erreurs):
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
                erreurs.append(
                    f"Ligne {numero} : service « {nom_service} » introuvable "
                    "(créez-le d'abord dans l'admin)."
                )
            valeurs["service_par_defaut"] = service

        if "ordre" in colonnes:
            texte = ligne["ordre"] or "0"
            if not texte.isdigit():
                erreurs.append(f"Ligne {numero} : « ordre » doit être un nombre entier positif.")
            else:
                valeurs["ordre"] = int(texte)
        return valeurs

    def enregistrer(self, secteurs, existants, desactiver_absents):
        bilan = {"crees": 0, "maj": 0, "desactives": 0}
        for valeurs in secteurs:
            secteur = existants.get(valeurs["code"]) or Secteur(code=valeurs["code"])
            bilan["maj" if secteur.pk else "crees"] += 1
            for champ, valeur in valeurs.items():
                setattr(secteur, champ, valeur)
            secteur.actif = True
            secteur.save()

        if desactiver_absents:
            codes = [valeurs["code"] for valeurs in secteurs]
            bilan["desactives"] = Secteur.objects.filter(actif=True).exclude(code__in=codes).update(actif=False)
        return bilan
