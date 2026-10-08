"""
Préproduction : la configuration de production (HTTPS, sécurité, cache partagé…), mais
**sans vrai fournisseur SMS ni push** pour l'instant : les codes OTP et les notifications
sont affichés dans les journaux du serveur (backends console) au lieu d'être envoyés.

Utilisé sur le serveur LE BAROMETRE (api.piecitizenvoice.com) et sur Render tant que les
fournisseurs ne sont pas choisis. Une fois branchés, passer à `config.settings.prod`, qui
refuse de démarrer avec les backends console (checks core.E001 / core.E002).
"""

from .prod import *  # noqa: F401,F403

EST_PRODUCTION = False
EST_PREPRODUCTION = True
