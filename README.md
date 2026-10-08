# Voix du Citoyen — API

API du module **Voix du Citoyen** de la plateforme LE BAROMETRE. Les citoyens d'une commune
béninoise signalent des problèmes à leur mairie, proposent des idées et suivent les
réalisations. Une seule API (`/api/v1/`) sert l'application mobile des citoyens et
l'application web de la mairie et des organisations.

Django 5.2 · Django REST Framework · PostgreSQL 17 · authentification JWT.

---

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Installation pas à pas](#2-installation-pas-à-pas)
3. [Charger des données de départ](#3-charger-des-données-de-départ)
4. [Travailler au quotidien](#4-travailler-au-quotidien)
5. [Lancer les tests](#5-lancer-les-tests)
6. [En cas de problème](#6-en-cas-de-problème)
7. [Organisation du code et règles du projet](#7-organisation-du-code-et-règles-du-projet)
8. [Déploiement en production](#8-déploiement-en-production)
9. [Version de test en ligne (Render)](#9-version-de-test-en-ligne-render)
10. [Serveur LE BAROMETRE](#10-serveur-le-barometre)

---

## 1. Prérequis

| Outil | Version | Vérifier avec |
|---|---|---|
| Python | **3.13** | `python3.13 --version` |
| Docker + Docker Compose | récent | `docker compose version` |
| Git | — | `git --version` |
| libmagic (détection du type des fichiers) | — | voir ci-dessous |

Installer **libmagic** selon le système :

```bash
sudo apt install libmagic1          # Ubuntu / Debian
sudo dnf install file-libs          # Fedora
brew install libmagic               # macOS
```

> **Windows** : utiliser **WSL 2** (Ubuntu) et suivre les commandes Ubuntu. Le projet
> n'est pas prévu pour fonctionner directement sous Windows.

PostgreSQL n'a **pas** besoin d'être installé : il tourne dans Docker.

---

## 2. Installation pas à pas

Toutes les commandes se lancent depuis le dossier `backend/`.

### 2.1 Récupérer le code

```bash
git clone <URL_DU_DEPOT> voix-du-citoyen
cd voix-du-citoyen/backend
```

### 2.2 Créer l'environnement Python

```bash
python3.13 -m venv venv
source venv/bin/activate            # à refaire dans chaque nouveau terminal
pip install -r requirements-dev.txt
```

L'invite du terminal commence alors par `(venv)`.

### 2.3 Créer le fichier `.env`

Le fichier `.env` contient la configuration locale. Il n'est **jamais** envoyé sur git :
chacun crée le sien à partir du modèle.

```bash
cp .env.example .env
```

Ouvrir `.env` et remplacer les deux valeurs `changer-moi` :

- `SECRET_KEY` : générer une valeur avec
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(50))"
  ```
- `POSTGRES_PASSWORD` : n'importe quel mot de passe (il ne sert qu'en local).

> ⚠️ Faire cette étape **avant** de démarrer la base (2.4) : le mot de passe est fixé
> au premier démarrage de PostgreSQL.

Les autres valeurs conviennent telles quelles pour le développement.

### 2.4 Démarrer la base de données

```bash
docker compose up -d
docker compose ps                   # la ligne « db » doit indiquer « Up »
```

PostgreSQL écoute sur le port **5433** de votre machine (pour ne pas gêner un éventuel
PostgreSQL déjà installé sur le port 5432). Les données sont conservées entre deux
redémarrages.

#### Sans Docker : utiliser un PostgreSQL installé sur sa machine

Docker n'est pas obligatoire. Il faut en revanche **PostgreSQL 14 ou plus récent** : le
projet utilise des fonctions propres à PostgreSQL (SQLite et MySQL ne fonctionnent pas).

1. Créer l'utilisateur et la base (le droit `CREATEDB` permet aux tests de créer leur base
   temporaire) :
   ```bash
   sudo -u postgres psql
   ```
   ```sql
   CREATE USER voix_citoyen WITH PASSWORD 'votre-mot-de-passe' CREATEDB;
   CREATE DATABASE voix_citoyen OWNER voix_citoyen;
   \q
   ```
2. Dans `.env`, indiquer ce PostgreSQL (port habituel **5432**) :
   ```
   POSTGRES_DB=voix_citoyen
   POSTGRES_USER=voix_citoyen
   POSTGRES_PASSWORD=votre-mot-de-passe
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   ```
3. Ne pas lancer `docker compose` et passer directement à l'étape 2.5.

Une base sur un autre serveur fonctionne de la même façon : il suffit d'adapter
`POSTGRES_HOST` et `POSTGRES_PORT`.

### 2.5 Créer les tables

```bash
python manage.py migrate
```

### 2.6 Créer votre compte administrateur

```bash
python manage.py createsuperuser
```

Saisir un numéro béninois (par exemple `0197000001`), votre **adresse e-mail**, puis nom,
prénoms et mot de passe. **Les comptes de la mairie et des organisations se connectent avec
leur adresse e-mail** ; les citoyens se connectent avec leur numéro de téléphone.

### 2.7 Lancer le serveur

```bash
python manage.py runserver
```

| Adresse | Contenu |
|---|---|
| http://localhost:8000/api/docs/ | **Documentation de l'API** (Swagger) : toutes les routes, avec exemples, à essayer en direct |
| http://localhost:8000/api/redoc/ | La même documentation, en version lecture |
| http://localhost:8000/admin/ | Administration (connexion avec le compte créé en 2.6) |
| http://localhost:8000/api/v1/sante/ | Vérification rapide : l'API et la base répondent |

**L'installation est terminée.** En développement, les SMS (codes de vérification) et les
notifications push ne sont pas envoyés : ils s'affichent, encadrés, dans le terminal où
tourne `runserver`.

---

## 3. Charger des données de départ

Sans commune, quartiers ni secteurs, on ne peut pas créer de signalement. Des fichiers
d'exemple sont fournis dans `docs/exemples/`.

> Les quartiers d'exemple ont des **coordonnées approximatives**, uniquement pour les
> essais. Les vraies données viendront de la mairie.

Tout ce qui suit peut se faire de trois façons, au choix : depuis **Swagger** (ou
l'application web de la mairie) avec un compte admin mairie, dans l'**admin Django**, ou
avec une **commande** dans le terminal.

### 3.1 Créer la commune

Avec `POST /api/v1/communes/` (Swagger) ou dans l'admin : **Territoire → Communes → Ajouter**,
par exemple :

| Champ | Valeur d'exemple |
|---|---|
| Nom | Abomey-Calavi |
| Code | ABC |
| Département | Atlantique |
| Latitude min / max | 6.38 / 6.65 |
| Longitude min / max | 2.23 / 2.45 |

L'emprise (latitudes et longitudes) sert à refuser les positions GPS hors de la commune.

La plateforme peut servir **plusieurs communes** (aujourd'hui Parakou en production). Chaque
commune a ses propres quartiers, services, agents et dossiers ; une mairie ne voit que les
siens. Les secteurs sont communs à toutes les communes. Seul l'**admin de la plateforme**
(compte admin mairie sans commune, par exemple celui créé par `createsuperuser`) peut
ajouter une commune.

### 3.2 Charger les services, les quartiers et les secteurs

Dans le terminal :

```bash
python manage.py charger_services docs/exemples/services.csv --commune ABC
python manage.py charger_quartiers docs/exemples/quartiers.csv --commune ABC
python manage.py charger_secteurs docs/exemples/secteurs.csv
```

Ou depuis Swagger (compte admin mairie), en envoyant le fichier à
`POST /api/v1/services/import/`, `/quartiers/import/` et `/secteurs/import/`. On peut aussi
créer les éléments un par un (`POST /api/v1/secteurs/`, `/quartiers/`, `/services/`…).

- `--simulation` vérifie un fichier sans rien enregistrer.
- Un fichier est accepté en entier ou refusé en entier, avec le numéro des lignes en erreur.
- Relancer la commande met à jour sans créer de doublon.
- `python manage.py charger_quartiers --help` décrit le format attendu.

### 3.3 Créer des comptes pour essayer

- **Citoyen** : depuis Swagger, `POST /auth/register/` (avec `commune` : l'`id` lu dans
  `GET /communes/`, liste publique), puis `POST /auth/otp/verify/` avec
  le code affiché dans le terminal de `runserver`.
- **Agent de la mairie** : avec un compte admin, `POST /api/v1/agents/` (rôle `AGENT`,
  rattaché à un service de la commune), ou dans l'admin Django.
- **Organisation** (ONG, OSC) : créer l'**organisation** dans l'admin, puis un utilisateur
  de rôle `ORGANISATION` rattaché à elle.

Pour appeler les routes protégées dans Swagger : `POST /auth/login/` (`email` + `password`
pour la mairie et les organisations, `telephone` + `password` pour un citoyen), copier le
jeton `access`, cliquer sur **Authorize** et le coller.

---

## 4. Travailler au quotidien

```bash
cd voix-du-citoyen/backend
source venv/bin/activate
docker compose up -d                # si la base n'est pas déjà lancée
python manage.py runserver
```

Après avoir récupéré les modifications des autres (`git pull`) :

```bash
pip install -r requirements-dev.txt # nouvelles dépendances éventuelles
python manage.py migrate            # nouvelles tables ou colonnes éventuelles
```

Arrêter la base : `docker compose down` (les données sont conservées).

---

## 5. Lancer les tests

La base (Docker ou PostgreSQL local) doit être démarrée. Les tests créent leur propre
base temporaire, puis la suppriment : vos données ne sont pas touchées.

Les tests sont rangés dans chaque application, dans `apps/<application>/tests/test_*.py`
(par exemple `apps/signalements/tests/test_creation.py`). Les éléments communs à tous les
tests (création d'utilisateurs, client connecté, SMS et push gardés en mémoire…) sont dans
`conftest.py`, à la racine.

```bash
pytest                              # toute la suite (quelques dizaines de secondes)
pytest apps/signalements            # une seule partie
pytest --cov                        # avec le taux de couverture du code
```

Avant de partager une modification : **tous les tests doivent passer**.

---

## 6. En cas de problème

| Symptôme | Solution |
|---|---|
| `ImportError: failed to find libmagic` | libmagic n'est pas installé : voir [Prérequis](#1-prérequis). |
| `ModuleNotFoundError: No module named 'django'` | L'environnement n'est pas activé : `source venv/bin/activate`. |
| `password authentication failed for user "voix_citoyen"` | Le mot de passe de `.env` a changé après le premier démarrage. Pour repartir d'une base vide : `docker compose down -v` (⚠️ efface les données locales) puis `docker compose up -d` et `python manage.py migrate`. |
| `connection refused` sur le port 5433 | La base n'est pas lancée : `docker compose up -d` (ou démarrer votre PostgreSQL local). |
| `permission denied to create database` en lançant les tests | Sans Docker : donner le droit à l'utilisateur, `ALTER USER voix_citoyen CREATEDB;` |
| `port is already allocated` au démarrage de Docker | Le port 5433 est déjà pris : changer `POSTGRES_PORT` dans `.env` (par exemple 5434), puis `docker compose up -d`. |
| `ImproperlyConfigured: Set the SECRET_KEY environment variable` | Le fichier `.env` manque ou est incomplet : refaire l'étape 2.3. |
| Le code SMS n'arrive pas | Normal en développement : il s'affiche dans le terminal de `runserver`. |

---

## 7. Organisation du code et règles du projet

```
backend/
├── config/            réglages (base, dev, prod), routes principales
├── apps/
│   ├── core/          format des réponses, erreurs, permissions, SMS, push, documentation
│   ├── territoire/    commune, arrondissements, quartiers
│   ├── accounts/      utilisateurs, inscription et connexion, organisations, services
│   ├── referentiel/   secteurs
│   ├── medias/        photos, vidéos, enregistrements vocaux
│   ├── signalements/  signalements des citoyens
│   ├── suggestions/   suggestions et soutiens
│   ├── realisations/  réalisations de la mairie
│   ├── notifications/ notifications et push
│   └── dashboard/     tableaux de bord
├── docs/              structure SQL de la base, fichiers CSV d'exemple
└── deploy/            exemple de configuration nginx
```

Dans chaque application : `models.py` (tables), `serializers.py` (format des données),
`views.py` (routes, sans logique métier), `services.py` (**toute** la logique métier),
`exemples.py` (exemples de la documentation) et `tests/`.

**Règles à respecter**

- **Noms en français** : modèles, champs, valeurs, messages d'erreur.
- **Format de réponse unique** : `{"succes", "message", "donnees"}` en cas de succès,
  `{"succes": false, "erreur": {"code", "message", "details"}}` en cas d'erreur.
  Les erreurs métier se lèvent avec `ErreurMetier(CodeErreur.XXX)` ; les codes sont tous
  dans `apps/core/codes_erreur.py` et ne doivent **jamais** être renommés (l'application
  mobile s'en sert).
- **Documentation obligatoire** : chaque nouvelle route doit être décrite dans Swagger
  (description, exemples, description de chaque champ). Le test
  `apps/core/tests/test_documentation.py` échoue sinon.
- **Un test** pour chaque règle métier et chaque permission.
- Ne jamais envoyer sur git le fichier `.env`, le dossier `venv/` ou `media/`.

---

## 8. Déploiement en production

L'image Docker lance l'API avec gunicorn et les réglages `config.settings.prod`, derrière
nginx en HTTPS (exemple : `deploy/nginx.conf`).

```bash
docker build -t voix-du-citoyen-api .
docker run --env-file .env.production -p 8000:8000 voix-du-citoyen-api
```

- **Variables** : voir la section « Production » de `.env.example`. Le serveur **refuse
  de démarrer** tant que l'envoi des SMS et des notifications push est en mode console
  (`SMS_BACKEND`, `PUSH_BACKEND`).
- **Fichiers envoyés** : stockage objet S3-compatible avec `USE_S3=True`, sinon dossier
  `/app/media` à conserver dans un volume.
- **À chaque mise en production** :
  ```bash
  python manage.py migrate
  python manage.py createcachetable
  python manage.py check --deploy
  ```
- **Tâches quotidiennes** (cron) : `python manage.py purger_medias` et
  `python manage.py flushexpiredtokens`.
- **Supervision** : `GET /api/v1/sante/` répond 200 si l'API et la base fonctionnent.

La structure complète de la base est aussi disponible en SQL dans
`docs/base_de_donnees.sql` (pour la consulter sans le code ; pour installer, `migrate` suffit).

---

## 9. Version de test en ligne (Render)

Une **préproduction** gratuite sur [Render](https://render.com), pour que l'équipe mobile et
web travaille sur une API en ligne. Tout est décrit dans `render.yaml` (API + base PostgreSQL)
et `config/settings/render.py`.

### Mise en place (une seule fois)

1. Pousser le code sur GitHub (le dépôt doit contenir `render.yaml`).
2. Sur Render : **New → Blueprint**, choisir le dépôt, puis **Apply**.
3. Render demande les variables marquées `sync: false` :

   | Variable | Exemple |
   |---|---|
   | `DJANGO_SUPERUSER_TELEPHONE` | `+2290197000001` |
   | `DJANGO_SUPERUSER_EMAIL` | `admin@mairie-parakou.bj` |
   | `DJANGO_SUPERUSER_NOM` / `_PRENOMS` | `Dossou` / `Koffi` |
   | `DJANGO_SUPERUSER_PASSWORD` | un mot de passe solide |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` (client web), ou vide |

4. Au premier démarrage, `deploy/render-start.sh` crée les tables et ce compte admin
   (admin de la plateforme, sans commune). L'API est sur
   `https://voix-du-citoyen-api.onrender.com/api/docs/` (le nom exact est affiché par Render).
5. Se connecter avec l'e-mail admin, puis créer la commune et charger les données de départ
   depuis Swagger : `POST /communes/`, `POST /quartiers/import/`, `POST /services/import/`,
   `POST /secteurs/import/` (fichiers d'exemple dans `docs/exemples/`).

Ensuite, chaque `git push` sur `main` redéploie automatiquement.

### Ce qu'il faut savoir

- **Codes OTP** : aucun SMS n'est envoyé. Le code s'affiche dans **Render → le service →
  Logs** (encadré « SMS »), comme dans le terminal en développement. La personne qui a
  accès à Render le communique au testeur. Même chose pour les notifications push.
- **Mise en veille** : en formule gratuite, l'API s'endort après 15 minutes sans requête ;
  la requête suivante prend environ une minute (réveil).
- **Photos, vidéos, audios** : le disque du service gratuit est **effacé à chaque
  redéploiement ou redémarrage**. Pour les garder, activer le stockage S3 (`USE_S3=True` et
  les variables `AWS_*`, par exemple avec Cloudflare R2, qui a une offre gratuite).
- **Base de données gratuite** : Render la supprime au bout de 30 jours ; il faut alors
  passer à une formule payante ou en recréer une (les données sont perdues).
- **Ce n'est pas la production** : `config.settings.render` autorise l'affichage des codes
  dans les journaux. La vraie production utilise `config.settings.prod`, qui l'interdit.

---

## 10. Serveur LE BAROMETRE

L'API de `api.piecitizenvoice.com` tourne sur le serveur de LE BAROMETRE, qui a ses propres
outils (commande `site`, nginx, PM2). Les accès et la procédure complète sont dans le
**guide de déploiement interne** (confidentiel, non versionné ici).

Le projet lit directement les variables fournies par ce serveur, en plus des siennes :

| Serveur | Équivalent du projet |
|---|---|
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` | `SECRET_KEY`, `DEBUG` |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `POSTGRES_*` |
| `STATIC_ROOT`, `MEDIA_ROOT` | dossiers `staticfiles/` et `media/` par défaut |

Variables à **ajouter** dans `site env api.piecitizenvoice.com` :

```bash
DJANGO_SETTINGS_MODULE=config.settings.preprod
CORS_ALLOWED_ORIGINS=https://piecitizenvoice.com,https://www.piecitizenvoice.com
SMS_BACKEND=apps.core.sms.backends.console.ConsoleSMS
PUSH_BACKEND=apps.core.push.backends.console.ConsolePush
```

`config.settings.preprod` = la production, mais les codes OTP et les notifications
s'affichent dans les journaux (`site logs api.piecitizenvoice.com`) tant qu'aucun vrai
fournisseur SMS / push n'est branché. Ensuite : `config.settings.prod` et les vrais backends.

Après le premier `site deploy`, une seule fois :

```bash
site manage api.piecitizenvoice.com createcachetable
site manage api.piecitizenvoice.com createsuperuser
```

Tâches quotidiennes à faire planifier par l'administration (ou à lancer à la main) :
`site manage api.piecitizenvoice.com purger_medias` et `… flushexpiredtokens`.
