"""
Préproduction sur Render (https://render.com) : la configuration de production, avec deux
différences tant que les vrais fournisseurs ne sont pas choisis :

- les SMS (codes OTP) et les notifications push sont affichés dans les **journaux Render**
  (backends console), au lieu d'être envoyés ;
- l'adresse publique `*.onrender.com` est acceptée automatiquement.

Ne jamais utiliser ce fichier pour la vraie production. Voir README.md, « Render ».
"""

import os

# Render fournit l'adresse publique du service dans RENDER_EXTERNAL_HOSTNAME.
HOTE_RENDER = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
os.environ.setdefault("ALLOWED_HOSTS", HOTE_RENDER or "localhost")

from .prod import *  # noqa: E402,F401,F403

# Pas de vrai fournisseur SMS / push pour l'instant : les checks core.E001 / core.E002 ne
# s'appliquent pas à la préproduction.
EST_PRODUCTION = False
EST_PREPRODUCTION = True

if HOTE_RENDER:
    CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, f"https://{HOTE_RENDER}"]  # noqa: F405

# Sous-domaine partagé onrender.com (qui ne nous appartient pas) : HSTS court, sans
# sous-domaines ni préchargement ; les avertissements correspondants sont donc attendus.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
