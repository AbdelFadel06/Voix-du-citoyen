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

Le **téléphone** sert d'identifiant : saisir un numéro béninois, par exemple `0197000001`
(il est enregistré au format `+2290197000001`). Puis nom, prénoms et mot de passe.

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

### 3.1 Créer la commune

Dans l'admin : **Territoire → Communes → Ajouter**, par exemple :

| Champ | Valeur d'exemple |
|---|---|
| Nom | Abomey-Calavi |
| Code | ABC |
| Département | Atlantique |
| Latitude min / max | 6.38 / 6.65 |
| Longitude min / max | 2.23 / 2.45 |

L'emprise (latitudes et longitudes) sert à refuser les positions GPS hors de la commune.

### 3.2 Charger les quartiers et les secteurs

```bash
python manage.py charger_quartiers docs/exemples/quartiers.csv --commune ABC
python manage.py charger_secteurs docs/exemples/secteurs.csv
```

- `--simulation` vérifie un fichier sans rien enregistrer.
- Un fichier est accepté en entier ou refusé en entier, avec le numéro des lignes en erreur.
- Relancer la commande met à jour sans créer de doublon.
- `python manage.py charger_quartiers --help` décrit le format attendu.

### 3.3 Créer des comptes pour essayer

- **Citoyen** : depuis Swagger, `POST /auth/register/`, puis `POST /auth/otp/verify/` avec
  le code affiché dans le terminal de `runserver`.
- **Agent de la mairie** : dans l'admin, créer d'abord un **service municipal**, puis un
  **utilisateur** de rôle `AGENT` rattaché à ce service.
- **Organisation** (ONG, OSC) : créer l'**organisation** dans l'admin, puis un utilisateur
  de rôle `ORGANISATION` rattaché à elle.

Pour appeler les routes protégées dans Swagger : `POST /auth/login/`, copier le jeton
`access`, cliquer sur **Authorize** et le coller.

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
