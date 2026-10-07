"""
Supprime les médias TEMPORAIRE jamais rattachés (fichier et miniature compris).

À planifier une fois par jour (cron, timer systemd…) :

    python manage.py purger_medias
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.medias.services import purger_medias_temporaires


class Command(BaseCommand):
    help = "Supprime les médias temporaires (jamais rattachés) plus anciens que 24 h."

    def add_arguments(self, parser):
        parser.add_argument(
            "--heures",
            type=int,
            default=24,
            help="Âge minimal, en heures, des médias temporaires à supprimer (défaut : 24).",
        )
        parser.add_argument(
            "--simulation",
            action="store_true",
            help="Affiche le nombre de médias concernés sans rien supprimer.",
        )

    def handle(self, *args, **options):
        avant = timezone.now() - timedelta(hours=options["heures"])
        nombre = purger_medias_temporaires(avant, simulation=options["simulation"])
        if options["simulation"]:
            self.stdout.write(self.style.WARNING(f"Simulation : {nombre} média(s) temporaire(s) à supprimer."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{nombre} média(s) temporaire(s) supprimé(s)."))
