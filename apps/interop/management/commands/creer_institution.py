"""
Connecte une mairie de la plateforme IBDC à Voix du Citoyen.

    python manage.py creer_institution --id-externe 12 --nom "Mairie de Parakou" --commune PKO \
        --email ibdc-parakou@mairie.bj --telephone +2290196000101

Crée l'institution et son compte technique, puis affiche la clé d'API **une seule fois**.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.interop import services
from apps.interop.models import Institution
from apps.territoire.models import Commune


class Command(BaseCommand):
    help = "Connecte une mairie IBDC (institution) à une commune et affiche sa clé d'API."

    def add_arguments(self, parser):
        parser.add_argument("--id-externe", required=True, help="Identifiant de l'institution chez IBDC.")
        parser.add_argument("--nom", required=True, help="Nom de l'institution, ex. « Mairie de Parakou ».")
        parser.add_argument("--commune", required=True, help="Code de la commune (ex. PKO), créée au préalable.")
        parser.add_argument("--email", required=True, help="E-mail du compte technique (contact technique IBDC).")
        parser.add_argument("--telephone", required=True, help="Téléphone du compte technique (+229…).")

    def handle(self, *args, **options):
        try:
            commune = Commune.objects.get(code=options["commune"])
        except Commune.DoesNotExist:
            raise CommandError(f"Commune « {options['commune']} » introuvable : créez-la d'abord.")
        if Institution.objects.filter(id_externe=options["id_externe"]).exists():
            raise CommandError(f"L'institution « {options['id_externe']} » est déjà connectée.")
        try:
            institution, cle = services.creer_institution(
                id_externe=options["id_externe"],
                nom=options["nom"],
                commune=commune,
                email=options["email"],
                telephone=options["telephone"],
            )
        except (IntegrityError, ValueError) as exc:
            raise CommandError(f"Création impossible (téléphone ou e-mail déjà utilisé ?) : {exc}")
        self.stdout.write(self.style.SUCCESS(f"{institution.nom} connectée à {commune.nom}."))
        self.stdout.write("Clé d'API à transmettre à IBDC (elle ne sera plus jamais affichée) :")
        self.stdout.write(cle)
