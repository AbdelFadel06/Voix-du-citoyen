"""Remplace la clé d'API d'une institution (l'ancienne cesse aussitôt de fonctionner)."""

from django.core.management.base import BaseCommand, CommandError

from apps.interop import services
from apps.interop.models import Institution


class Command(BaseCommand):
    help = "Génère une nouvelle clé d'API pour une institution et l'affiche une seule fois."

    def add_arguments(self, parser):
        parser.add_argument("--id-externe", required=True, help="Identifiant de l'institution chez IBDC.")

    def handle(self, *args, **options):
        try:
            institution = Institution.objects.get(id_externe=options["id_externe"])
        except Institution.DoesNotExist:
            raise CommandError(f"Aucune institution « {options['id_externe']} ».")
        cle = services.generer_cle(institution)
        self.stdout.write(self.style.SUCCESS(f"Nouvelle clé de {institution.nom} (l'ancienne ne fonctionne plus) :"))
        self.stdout.write(cle)
