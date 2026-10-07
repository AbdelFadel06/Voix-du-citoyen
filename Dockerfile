# Image de production de l'API Voix du Citoyen.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# libmagic : détection du type réel des fichiers envoyés (python-magic).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

# Fichiers statiques (admin, Swagger) rassemblés dans /app/staticfiles, servis par nginx.
# Les valeurs ci-dessous ne servent qu'à charger les settings pendant la construction.
RUN SECRET_KEY=construction ALLOWED_HOSTS=localhost POSTGRES_DB=x POSTGRES_USER=x \
    POSTGRES_PASSWORD=x POSTGRES_HOST=x POSTGRES_PORT=5432 \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown app:app /app/media /app/staticfiles

USER app
EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "config.wsgi:application"]
