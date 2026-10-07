from abc import ABC, abstractmethod


class EnvoiSMSEchoue(Exception):
    """Levée par un fournisseur lorsque le SMS n'a pas pu être envoyé."""


class FournisseurSMS(ABC):
    """
    Interface commune à tous les fournisseurs SMS.

    Pour brancher un nouveau fournisseur : créer un fichier dans `backends/` avec une
    sous-classe qui implémente `envoyer`, puis renseigner son chemin dans SMS_BACKEND.
    """

    @abstractmethod
    def envoyer(self, telephone: str, message: str) -> None:
        """Envoie `message` au numéro `telephone` (format E.164) ou lève EnvoiSMSEchoue."""
