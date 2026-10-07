import logging
import textwrap

from django.utils import timezone

from ..base import FournisseurSMS

logger = logging.getLogger(__name__)

LARGEUR = 64


class ConsoleSMS(FournisseurSMS):
    """Développement uniquement : affiche le SMS dans le terminal au lieu de l'envoyer."""

    def envoyer(self, telephone, message):
        heure = timezone.localtime().strftime("%d/%m/%Y %H:%M:%S")
        lignes = [f"À       : {telephone}", f"Heure   : {heure}", "Message :"]
        lignes += ["  " + ligne for ligne in textwrap.wrap(message, LARGEUR - 6)]
        titre = " SMS (backend console, non envoyé) "
        cadre = [
            "╔" + titre.center(LARGEUR - 2, "═") + "╗",
            *("║ " + ligne.ljust(LARGEUR - 4) + " ║" for ligne in lignes),
            "╚" + "═" * (LARGEUR - 2) + "╝",
        ]
        logger.info("\n%s", "\n".join(cadre))
