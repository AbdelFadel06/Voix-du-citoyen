"""
Préproduction sur Render (https://render.com) : `config.settings.preprod` (codes OTP et
notifications dans les **journaux Render**), avec l'adresse publique `*.onrender.com`
acceptée automatiquement.

Ne jamais utiliser ce fichier pour la vraie production. Voir README.md, « Render ».
"""

import os

# Render fournit l'adresse publique du service dans RENDER_EXTERNAL_HOSTNAME.
HOTE_RENDER = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
os.environ.setdefault("ALLOWED_HOSTS", HOTE_RENDER or "localhost")

from .preprod import *  # noqa: E402,F401,F403

if HOTE_RENDER:
    CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, f"https://{HOTE_RENDER}"]  # noqa: F405

# Sous-domaine partagé onrender.com (qui ne nous appartient pas) : HSTS court, sans
# sous-domaines ni préchargement ; les avertissements correspondants sont donc attendus.
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
