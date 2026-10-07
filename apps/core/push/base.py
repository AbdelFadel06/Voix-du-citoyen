from abc import ABC, abstractmethod


class EnvoiPushEchoue(Exception):
    """Levée par un fournisseur lorsque la notification push n'a pas pu être envoyée."""


class JetonPushInvalide(EnvoiPushEchoue):
    """Le jeton de l'appareil n'est plus valide (application désinstallée…) : désactiver l'appareil."""


class FournisseurPush(ABC):
    """
    Interface commune à tous les fournisseurs de notifications push.

    Pour brancher un nouveau fournisseur (ex. Firebase Cloud Messaging) : créer un fichier
    dans `backends/` avec une sous-classe qui implémente `envoyer`, puis renseigner son
    chemin dans PUSH_BACKEND.
    """

    @abstractmethod
    def envoyer(self, jeton: str, titre: str, message: str, donnees: dict[str, str]) -> None:
        """
        Envoie la notification à l'appareil `jeton`. `donnees` (valeurs texte) permet à
        l'application d'ouvrir le bon écran. Lève JetonPushInvalide ou EnvoiPushEchoue.
        """
