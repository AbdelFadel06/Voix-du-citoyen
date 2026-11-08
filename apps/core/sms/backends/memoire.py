from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from ..base import Canal, EnvoiSMSEchoue, FournisseurSMS


@dataclass
class SMSEnvoye:
    telephone: str
    message: str
    canal: str = Canal.SMS
    envoye_le: datetime = field(default_factory=timezone.now)


class MemoireSMS(FournisseurSMS):
    """
    Tests uniquement : garde les SMS en mémoire dans `MemoireSMS.boite`.
    Mettre `MemoireSMS.simuler_echec = True` pour tester un fournisseur en panne.
    """

    boite: list[SMSEnvoye] = []
    simuler_echec = False

    @classmethod
    def vider(cls):
        cls.boite.clear()
        cls.simuler_echec = False

    def envoyer(self, telephone, message, canal=Canal.SMS):
        if self.simuler_echec:
            raise EnvoiSMSEchoue("Échec simulé du fournisseur SMS.")
        self.boite.append(SMSEnvoye(telephone, message, canal))
