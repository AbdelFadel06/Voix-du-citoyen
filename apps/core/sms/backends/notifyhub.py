"""
NotifyHub (GROUP DEV) : codes par WhatsApp et par SMS.

API : `POST {NOTIFYHUB_URL}/messages/whatsapp` et `/messages/sms`, en-tête
`Authorization: Bearer <clé>`. Une clé Sandbox (`gd_test_…`) n'envoie rien réellement ; l'envoi
réel demande une clé de production (compte vérifié chez NotifyHub).

- **WhatsApp** : un code d'authentification part avec un **modèle approuvé par Meta**
  (`NOTIFYHUB_WHATSAPP_MODELE`, langue `NOTIFYHUB_WHATSAPP_LANGUE`), dont la seule variable est
  le code. Le texte libre n'est accepté que 24 h après un message du contact : inutilisable ici.
- **SMS** : `NOTIFYHUB_SMS_EXPEDITEUR` (Sender ID approuvé). Vide = canal SMS indisponible
  (`EnvoiSMSEchoue`, donc `SMS_ECHEC` : l'application propose WhatsApp).

L'en-tête `Idempotency-Key` évite un double envoi si NotifyHub rejoue la requête. Ni le code ni le
texte du message n'apparaissent dans les journaux : seulement le code d'erreur de NotifyHub.
"""

import json
import logging
import urllib.error
import urllib.request
import uuid

from django.conf import settings

from ..base import Canal, EnvoiSMSEchoue, FournisseurSMS

logger = logging.getLogger(__name__)


class NotifyHubSMS(FournisseurSMS):
    def envoyer(self, telephone, message, canal=Canal.SMS, code=None):
        if canal == Canal.WHATSAPP:
            modele = settings.NOTIFYHUB_WHATSAPP_MODELE
            if not modele or code is None:
                raise EnvoiSMSEchoue("Modèle WhatsApp NotifyHub non configuré (NOTIFYHUB_WHATSAPP_MODELE).")
            chemin = "messages/whatsapp"
            corps = {
                "to": telephone,
                "template": {"name": modele, "language": settings.NOTIFYHUB_WHATSAPP_LANGUE, "variables": [code]},
            }
        else:
            if not settings.NOTIFYHUB_SMS_EXPEDITEUR:
                raise EnvoiSMSEchoue("Expéditeur SMS NotifyHub non configuré (NOTIFYHUB_SMS_EXPEDITEUR).")
            chemin = "messages/sms"
            corps = {"from": settings.NOTIFYHUB_SMS_EXPEDITEUR, "to": telephone, "message": message, "type": "otp"}
        self._poster(chemin, corps, canal)

    def _poster(self, chemin, corps, canal):
        requete = urllib.request.Request(
            f"{settings.NOTIFYHUB_URL.rstrip('/')}/{chemin}",
            data=json.dumps(corps).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {settings.NOTIFYHUB_CLE}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        try:
            with urllib.request.urlopen(requete, timeout=settings.NOTIFYHUB_DELAI) as reponse:
                donnees = _json(reponse.read())
        except urllib.error.HTTPError as erreur:
            code = (_json(erreur.read()).get("error") or {}).get("code", "?")
            logger.error("NotifyHub a refusé l'envoi %s : HTTP %s, code %s.", canal, erreur.code, code)
            raise EnvoiSMSEchoue(f"NotifyHub : {code}") from erreur
        except (urllib.error.URLError, TimeoutError, OSError) as erreur:
            logger.error("NotifyHub injoignable pour l'envoi %s : %s.", canal, type(erreur).__name__)
            raise EnvoiSMSEchoue("NotifyHub injoignable.") from erreur
        if donnees.get("success") is False:
            code = (donnees.get("error") or {}).get("code", "?")
            logger.error("NotifyHub a refusé l'envoi %s : code %s.", canal, code)
            raise EnvoiSMSEchoue(f"NotifyHub : {code}")


def _json(contenu):
    try:
        donnees = json.loads(contenu or b"{}")
    except ValueError:
        return {}
    return donnees if isinstance(donnees, dict) else {}
