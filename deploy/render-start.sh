#!/bin/sh
# Démarrage du service sur Render : la formule gratuite n'a ni console (shell), ni commande
# avant déploiement, ni tâches planifiées. Tout est donc fait ici, à chaque démarrage.
set -e

python manage.py migrate --noinput
python manage.py createcachetable

# Premier compte admin (admin de la plateforme), créé une seule fois à partir des variables
# DJANGO_SUPERUSER_TELEPHONE, _EMAIL, _NOM, _PRENOMS et _PASSWORD.
if [ -n "$DJANGO_SUPERUSER_TELEPHONE" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput \
        && echo "Compte admin créé." \
        || echo "Compte admin déjà présent (ou variables incomplètes) : rien à faire."
fi

# Tâches quotidiennes de la production, lancées à chaque démarrage (le service gratuit
# redémarre souvent, après chaque mise en veille).
python manage.py purger_medias || true
python manage.py flushexpiredtokens || true

export GUNICORN_BIND="0.0.0.0:${PORT:-8000}"
exec gunicorn -c gunicorn.conf.py config.wsgi:application
