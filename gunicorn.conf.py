"""Configuration de gunicorn en production (valeurs réglables par variables d'environnement)."""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
# Large marge pour le traitement des photos ; les envois lents sont mis en tampon par nginx.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
# Redémarre régulièrement chaque processus (protège contre les fuites de mémoire).
max_requests = 1000
max_requests_jitter = 100
# Journaux sur la sortie standard.
accesslog = "-"
errorlog = "-"
# Adresse du reverse proxy autorisé à transmettre X-Forwarded-Proto.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
