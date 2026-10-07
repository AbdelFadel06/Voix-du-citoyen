import logging
import textwrap

from ..base import FournisseurPush

logger = logging.getLogger(__name__)

LARGEUR = 64


class ConsolePush(FournisseurPush):
    """Développement uniquement : affiche la notification dans le terminal au lieu de l'envoyer."""

    def envoyer(self, jeton, titre, message, donnees):
        lignes = [f"Appareil : {jeton[:24]}…", f"Titre    : {titre}", "Message  :"]
        lignes += ["  " + ligne for ligne in textwrap.wrap(message, LARGEUR - 6)]
        lignes.append("Données  : " + ", ".join(f"{k}={v}" for k, v in donnees.items()))
        titre_cadre = " PUSH (backend console, non envoyé) "
        cadre = [
            "╔" + titre_cadre.center(LARGEUR - 2, "═") + "╗",
            *("║ " + ligne[: LARGEUR - 4].ljust(LARGEUR - 4) + " ║" for ligne in lignes),
            "╚" + "═" * (LARGEUR - 2) + "╝",
        ]
        logger.info("\n%s", "\n".join(cadre))
