from abc import ABC, abstractmethod

from django.db import models


class Canal(models.TextChoices):
    """Canal de réception des codes, choisi par l'utilisateur (l'application présélectionne WhatsApp)."""

    WHATSAPP = "WHATSAPP", "WhatsApp"
    SMS = "SMS", "SMS"


# Quand l'application ne précise pas le canal : SMS, comme avant l'ajout de WhatsApp, pour que les
# versions déjà publiées de l'application mobile continuent de fonctionner à l'identique.
CANAL_PAR_DEFAUT = Canal.SMS


class EnvoiSMSEchoue(Exception):
    """Levée par un fournisseur lorsque le message (SMS ou WhatsApp) n'a pas pu être envoyé."""


class FournisseurSMS(ABC):
    """
    Interface commune à tous les fournisseurs de messages (SMS et WhatsApp).

    Pour brancher un nouveau fournisseur : créer un fichier dans `backends/` avec une
    sous-classe qui implémente `envoyer`, puis renseigner son chemin dans SMS_BACKEND.
    """

    @abstractmethod
    def envoyer(self, telephone: str, message: str, canal: str = Canal.SMS, code: str | None = None) -> None:
        """
        Envoie `message` au numéro `telephone` (format E.164) par `canal`, ou lève EnvoiSMSEchoue.
        `code` (code OTP seul) sert aux fournisseurs dont WhatsApp impose un modèle à variables.
        """
