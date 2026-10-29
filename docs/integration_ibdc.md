# Intégration IBDC ↔ Voix du Citoyen — guide pour le module « Voix du Citoyen » des mairies

*Version du 29/10/2026 · API Voix du Citoyen v1 · documentation interactive :
https://api.piecitizenvoice.com/api/docs/ (Swagger) et `/api/redoc/`.*

Ce guide indique, **page par page** du module « Voix du Citoyen » de la plateforme IBDC, quels
appels faire à l'API Voix du Citoyen, avec quels paramètres, et ce que l'on reçoit. Le détail
de chaque champ et de chaque erreur est dans Swagger.

---

## 1. Principes

### 1.1 Authentification : une clé par mairie

- Chaque mairie (institution IBDC) reçoit **une clé d'API**, fournie par l'équipe Voix du
  Citoyen (`vdc_…`). Elle est liée à **une commune** : vous n'envoyez jamais d'identifiant de
  commune.
- À envoyer **depuis votre serveur uniquement** (jamais dans le navigateur ni l'application) :

  ```http
  GET https://api.piecitizenvoice.com/api/v1/mairie/signalements/
  X-Api-Key: vdc_a3f9c2e1b7d4_…
  X-Agent: Rodrigue%20Ahouansou
  ```

- **Espace mairie** : tous les appels du module passent par **`/api/v1/mairie/…`**
  (signalements, suggestions, réalisations, tableaux de bord, secteurs, quartiers,
  organisations : liste complète au § 1.5). La commune vient de la clé : elle n'est **ni un paramètre ni une
  partie de l'adresse**. Les adresses sans `/mairie/` répondent `403 ESPACE_MAIRIE_REQUIS`.
  Restent hors de cet espace : `GET /api/v1/auth/me/` et `POST /api/v1/medias/`.
- **Droits** : ceux d'un administrateur de la mairie, **limités à sa commune** (les dossiers
  des autres communes répondent 404).
- **`X-Agent`** (recommandé) : nom de l'agent IBDC qui agit, encodé en URL. Il apparaît dans
  l'historique des dossiers (« Rodrigue Ahouansou (IBDC) »).
- Vérifier une clé : `GET /api/v1/auth/me/` renvoie le compte technique de la mairie, avec sa
  `commune` et `commune_nom`.
- **Limite** : 600 appels par minute et par clé (au-delà : `429 TROP_DE_REQUETES`, en-tête
  `Retry-After`). Envois de photos et vidéos : 60 par heure pour la mairie.

### 1.2 Format des réponses

Toutes les réponses ont la même enveloppe :

```json
{ "succes": true, "message": "Statut mis à jour : Reçu par la mairie.", "donnees": { … } }
```

Listes paginées : en plus, un bloc `pagination` :

```json
"pagination": { "total": 128, "page": 1, "pages": 7, "taille": 20, "suivant": "…?page=2", "precedent": null }
```

Paramètres communs des listes : `page`, `taille` (taille de page), `tri` (champ, préfixe `-` pour
décroissant), `recherche` (texte).

Erreurs :

```json
{ "succes": false, "erreur": { "code": "VALIDATION_ERREUR", "message": "…", "details": { "commentaire": ["…"] } } }
```

Utilisez le **`code`** (stable) dans votre logique et affichez le **`message`** (en français).

### 1.3 Données et identifiants

- Les identifiants (`id`) de signalements, quartiers, secteurs, services, agents, organisations
  sont **ceux de Voix du Citoyen** : récupérez-les dans nos réponses, sans table de
  correspondance.
- Dates au format ISO 8601 (`2026-10-27T09:15:00+01:00`), dates simples `AAAA-MM-JJ`.
- **Anonymat des citoyens** : l'auteur d'un signalement ou d'une suggestion n'est **jamais**
  transmis (`auteur: null`), même à la mairie. Ne le cherchez pas.
- Photos, vidéos et audios : les listes donnent des **miniatures**, le détail les fichiers complets
  (URL à afficher telles quelles).

### 1.4 Rafraîchissement (pas de webhooks)

Rechargez les données à l'ouverture d'une page et après chaque action. Pour une actualisation
automatique légère, les listes de signalements, suggestions et réalisations acceptent
`modifie_depuis=<date ISO>` : seulement ce qui a été créé ou modifié depuis cet instant.

### 1.5 Liste des adresses de l'espace mairie

Toutes commencent par `https://api.piecitizenvoice.com/api/v1/mairie/` et s'appellent avec la clé.

| Volet | Méthode | Adresse | Rôle |
|---|---|---|---|
| Tableau de bord | GET | `dashboard/synthese/` | Récapitulatif complet : chiffres globaux, par secteur, par quartier (§ 2) |
| | GET | `dashboard/evolution/` | Courbe dans le temps (`periode=jour\|semaine\|mois`) |
| | GET | `dashboard/carte/` | Points de la carte |
| Signalements | GET | `signalements/` · `signalements/{id}/` | Liste filtrable, détail avec historique (§ 3) |
| | POST | `signalements/{id}/changer-statut/` | Faire avancer, rejeter, marquer doublon (§ 4) |
| | POST | `signalements/{id}/repondre/` | Réponse au citoyen ou note interne (§ 4) |
| | POST | `signalements/{id}/affecter-organisation/` | Confier le dossier à une ONG, la remplacer ou la retirer (§ 5) |
| Suggestions | GET | `suggestions/` · `suggestions/{id}/` | Liste filtrable, détail (§ 6) |
| | POST | `suggestions/{id}/repondre/` | Réponse officielle ou note interne (§ 6) |
| | POST, DELETE | `suggestions/{id}/pertinente/` | Marquer / retirer « pertinente » (§ 7) |
| Réalisations | GET, POST | `realisations/` | Liste (brouillons compris), création (§ 8) |
| | GET, PATCH | `realisations/{id}/` | Détail, mise à jour, publication (§ 8) |
| Organisations (ONG) | GET, POST | `organisations/` | Liste avec statistiques, enregistrement (§ 10) |
| | GET, PATCH | `organisations/{id}/` | Détail, modification (§ 10) |
| | POST | `organisations/{id}/retirer-commune/` | Ne plus travailler avec l'ONG dans la commune (§ 10) |
| | GET, POST · PATCH | `organisations/{id}/membres/` · `…/membres/{membre_id}/` | Comptes des membres de l'ONG (§ 10) |
| Référentiel | GET, POST · GET, PATCH | `secteurs/` · `secteurs/{id}/` | Secteurs (voirie, santé…) ; `POST secteurs/import/` (CSV) |
| | GET, POST · GET, PATCH | `quartiers/` · `quartiers/{id}/` | Quartiers de la commune ; `GET quartiers/proche/`, `POST quartiers/import/` |
| | GET, POST · GET, PATCH | `arrondissements/` · `arrondissements/{id}/` | Arrondissements de la commune |
| | GET · PATCH | `communes/` · `communes/{id}/` | La commune de la clé |

Hors de l'espace mairie, communs à tous : `GET /api/v1/auth/me/` (vérifier la clé) et
`POST /api/v1/medias/` (envoi des photos et vidéos des réalisations).

Les agents et services de la mairie restent gérés **dans IBDC** : vous n'avez à créer ni agent
ni service chez nous. Le nom de l'agent qui agit est transmis par `X-Agent`.

---

## 2. Page « Tableau de bord » (statistiques)

Filtres communs : `date_debut`, `date_fin` (date d'envoi des dossiers), `secteur`, `quartier`.
Tous les chiffres sont ceux de la commune de la clé (aucun paramètre `commune`).

| Bloc de la page | Appel | Contenu |
|---|---|---|
| **Récapitulatif complet** : chiffres clés, par secteur, par quartier | `GET /api/v1/mairie/dashboard/synthese/` (+ `arrondissement`, qui ne limite que `par_quartier`) | `globales` · `par_secteur` · `par_quartier` (détail ci-dessous) |
| Évolution dans le temps (courbe) | `GET /api/v1/mairie/dashboard/evolution/?periode=jour\|semaine\|mois` | `points` : `periode` (date), `signalements_crees`, `signalements_resolus`, `suggestions_creees` ; série sans trou (0 si rien) |
| Carte | `GET /api/v1/mairie/dashboard/carte/` (+ `statut`) | Points GPS des signalements (2 000 max, `signalements_tronques`), nombre de signalements par quartier (au centre du quartier), réalisations localisées |
| Organisations partenaires (ONG) | `GET /api/v1/mairie/organisations/` | Pour chaque ONG de la commune : périmètre, comptes actifs et `statistiques` (signalements, en attente, en cours, résolus, taux et délai de résolution, dossiers pris en charge, réalisations publiées) |

Contenu du récapitulatif :

1. **`globales`** — `signalements` : `total`, `par_statut` (un compteur par statut), `ouverts`,
   `resolus`, `taux_resolution` (%), `delai_moyen_resolution_jours` · `suggestions` : `total`,
   `nb_soutiens`, `pertinentes` · `realisations` : `total`, `par_statut`, `budget_total` (FCFA),
   `taux_avancement_moyen`, `brouillons` ;
2. **`par_secteur`** — une ligne par secteur, du plus grand nombre de signalements au plus petit :
   `secteur {id, nom, code, couleur}`, `signalements`, `signalements_ouverts`,
   `signalements_resolus`, `taux_resolution`, `suggestions`, `realisations` ;
3. **`par_quartier`** — une ligne par quartier ayant au moins un dossier : `quartier {id, nom,
   arrondissement}` et les mêmes compteurs.

Exemple :

```http
GET /api/v1/mairie/dashboard/synthese/?date_debut=2026-10-01&date_fin=2026-10-31
```

```json
{ "succes": true, "message": null, "donnees": {
  "globales": {
    "signalements": { "total": 128, "par_statut": { "SOUMIS": 12, "RECU": 18, "EN_COURS": 25, "RESOLU": 61, "REJETE": 8, "DOUBLON": 4 },
                      "ouverts": 55, "resolus": 61, "taux_resolution": 47.7, "delai_moyen_resolution_jours": 9.4 },
    "suggestions": { "total": 88, "nb_soutiens": 1742, "pertinentes": 14 },
    "realisations": { "total": 31, "par_statut": { "PLANIFIEE": 6, "EN_COURS": 9, "TERMINEE": 15, "SUSPENDUE": 1 },
                      "budget_total": 845000000, "taux_avancement_moyen": 62.5, "brouillons": 4 } },
  "par_secteur": [
    { "secteur": { "id": 1, "nom": "Voirie", "code": "VOIRIE", "couleur": "#F57C00" },
      "signalements": 54, "signalements_ouverts": 21, "signalements_resolus": 29, "taux_resolution": 53.7,
      "suggestions": 19, "realisations": 12 } ],
  "par_quartier": [
    { "quartier": { "id": 12, "nom": "Banikanni", "arrondissement": "1er arrondissement" },
      "signalements": 23, "signalements_ouverts": 9, "signalements_resolus": 12, "taux_resolution": 52.2,
      "suggestions": 6, "realisations": 3 } ] } }
```

---

## 3. Page « Signalements » (liste)

```http
GET /api/v1/mairie/signalements/?statut=SOUMIS&secteur=3&tri=-cree_le&page=1&taille=20
```

| Filtre | Valeurs |
|---|---|
| `statut` | `SOUMIS`, `RECU`, `EN_COURS`, `RESOLU`, `REJETE`, `DOUBLON` |
| `secteur`, `quartier` | identifiants (voir § 9) |
| `date_debut`, `date_fin` | date d'envoi (`AAAA-MM-JJ`) |
| `organisation` / `pris_en_charge` | dossiers d'une ONG / `true` pris en charge par une ONG, `false` aucune |
| `recherche` | référence, titre, description, repère |
| `tri` | `cree_le`, `maj_le`, `reference` (`-` décroissant) |

Champs utiles pour chaque ligne : `id`, `reference` (`SIG-2026-00128`), `titre`, `statut`,
`secteur {id, nom, code, icone, couleur}`, `quartier {id, nom, arrondissement}`, `repere`,
`latitude` / `longitude` (mode GPS), `medias` (miniatures), `a_description_audio`,
`organisation_assignee` (ONG en charge, `null` sinon), `cree_le`, `maj_le`.

**Détail d'un signalement** : `GET /api/v1/mairie/signalements/{id}/` ajoute `description_texte`,
`description_audio` (fichier vocal, langue libre), photos et vidéo en taille réelle,
`precision_gps`, `doublon_de`, `date_resolution` et l'**`historique`** complet (changements de
statut, assignations, réponses, notes internes ; `auteur_nom` = agent, `organisation` = ONG,
`visible_citoyen`).

---

## 4. Traitement des signalements (statuts)

```http
POST /api/v1/mairie/signalements/{id}/changer-statut/
{ "statut": "EN_COURS", "commentaire": "Une équipe interviendra cette semaine." }
```

| Statut actuel | Statuts possibles |
|---|---|
| `SOUMIS` (envoyé par le citoyen) | `RECU`, `REJETE`, `DOUBLON` |
| `RECU` (reçu par la mairie) | `EN_COURS`, `REJETE`, `DOUBLON` |
| `EN_COURS` (en traitement) | `RESOLU`, `REJETE`, `DOUBLON` |
| `RESOLU`, `REJETE`, `DOUBLON` | aucun : dossier clos |

- `commentaire` : visible par le citoyen ; **obligatoire pour `REJETE`** (motif).
- `DOUBLON` : `doublon_de` obligatoire (id du signalement d'origine, même commune).
- Chaque changement est inscrit dans l'historique et **notifié au citoyen**.
- Transition impossible : `409 TRANSITION_STATUT_INVALIDE`, avec `details.statuts_possibles`
  (utile pour n'afficher que les boutons autorisés).

**Répondre au citoyen ou ajouter une note interne** :

```http
POST /api/v1/mairie/signalements/{id}/repondre/
{ "commentaire": "Les travaux sont prévus lundi.", "interne": false }
```

`interne: true` = note visible uniquement par la mairie.

---

## 5. Confier un signalement à une organisation (ONG)

La répartition du travail entre les agents et services de la mairie se fait **dans IBDC**. Côté
Voix du Citoyen, on confie seulement un dossier à une ONG partenaire :

```http
POST /api/v1/mairie/signalements/{id}/affecter-organisation/
{ "organisation": 2 }       (null pour la retirer)
```

L'ONG doit intervenir dans la commune et le secteur du dossier
(`GET /api/v1/mairie/organisations/?secteur=…`). Elle est notifiée et peut ensuite faire avancer le
statut (`RECU`, `EN_COURS`, `RESOLU`). Une ONG peut aussi prendre en charge elle-même un dossier
libre : `organisation_assignee` l'indique. Pour remplacer l'ONG en charge, renvoyer l'appel avec
une autre `organisation`. Dossier clos : `409 SIGNALEMENT_CLOTURE`.

---

## 6. Page « Suggestions »

```http
GET /api/v1/mairie/suggestions/?tri=-nb_soutiens&secteur=4
```

Filtres : `secteur`, `quartier`, `date_debut`, `date_fin`, `est_pertinente`, `recherche`,
`tri` (`cree_le`, `maj_le`, `nb_soutiens`, `reference`).

Champs : `id`, `reference` (`SUG-2026-00042`), `titre`, `secteur`, `quartier` (`null` = toute la
commune), `nb_soutiens`, `medias`, `a_reponse`, `est_pertinente`, `cree_le`.
Détail `GET /api/v1/mairie/suggestions/{id}/` : `description`, `reponse_officielle`, `repondu_le`,
`repondu_par`, `historique`.

Les suggestions **n'ont pas de statut**. Réponse officielle (notifiée au citoyen, la dernière
remplace la précédente) ou note interne :

```http
POST /api/v1/mairie/suggestions/{id}/repondre/
{ "commentaire": "Merci : 10 bancs sont prévus au budget 2027.", "interne": false }
```

---

## 7. Marquer une suggestion comme pertinente

```http
POST   /api/v1/mairie/suggestions/{id}/pertinente/     → marquer
DELETE /api/v1/mairie/suggestions/{id}/pertinente/     → retirer la marque
```

Réponse : `{ "est_pertinente": true|false }`. Renvoyer la même requête est sans effet. Retrouver
les suggestions retenues : `GET /api/v1/mairie/suggestions/?est_pertinente=true`. Cette marque n'est
**jamais** montrée aux citoyens.

---

## 8. Page « Réalisations » de la mairie

**Liste** (réalisations de la mairie, brouillons compris) :

```http
GET /api/v1/mairie/realisations/?par_la_mairie=true
GET /api/v1/mairie/realisations/?par_la_mairie=true&publie=false     → uniquement les brouillons
```

`par_la_mairie=false` donne celles des ONG (publiées) ; `organisation=<id>` celles d'une ONG.
Champs : `id`, `reference` (`REA-2026-00004`), `titre`, `secteur`, `statut` (`PLANIFIEE`,
`EN_COURS`, `TERMINEE`, `SUSPENDUE`), `taux_avancement`, `quartiers`, dates prévues,
`couverture` (miniature), `nb_medias`, `organisation` (`null` = mairie), `publie`,
`peut_modifier` (afficher le bouton « Modifier »). Détail `GET /api/v1/mairie/realisations/{id}/` :
description, budget, financement, prestataire, position, photos par phase, signalements et
suggestions liés.

**Créer une réalisation** : envoi en deux temps.

1. Envoyer chaque photo ou vidéo, une par requête (multipart) :

   ```http
   POST /api/v1/medias/          (multipart/form-data)
   type=IMAGE   fichier=@chantier.jpg
   ```

   → `{ "id": "3f6c1a2e-…" }`. Vidéos : `type=VIDEO`, `duree_secondes` et `miniature`
   (image) obligatoires. Formats : JPEG, PNG, WebP ; MP4, MOV, 3GP. Photo : 5 Mo max.

2. Créer la fiche en JSON avec ces identifiants :

   ```http
   POST /api/v1/mairie/realisations/
   {
     "titre": "Pavage de la rue de l'école",
     "description": "850 m de pavés et des caniveaux couverts.",
     "secteur": 1,
     "quartiers": [12],
     "statut": "EN_COURS",
     "taux_avancement": 40,
     "date_debut_prevue": "2026-09-01",
     "date_fin_prevue": "2026-12-15",
     "budget": 45000000,
     "source_financement": "Budget communal 2026",
     "prestataire": "Entreprise BTP Borgou",
     "signalements": [128],
     "suggestions": [42],
     "medias": [{ "media": "3f6c1a2e-…", "phase": "AVANT", "legende": "Avant les travaux" }],
     "publie": false
   }
   ```

   Obligatoires : `titre`, `description`, `secteur` (`GET /mairie/secteurs/?pour_realisation=true`),
   `quartiers`. Phases : `AVANT`, `PENDANT`, `APRES` (10 photos et 2 vidéos max).

**Mettre à jour ou publier** : `PATCH /api/v1/mairie/realisations/{id}/` avec seulement les champs à
changer, par exemple `{ "taux_avancement": 70 }` ou `{ "publie": true }`. À la publication, les
habitants des quartiers concernés et les auteurs des signalements liés sont notifiés. En
`PATCH`, `medias` **remplace** la liste complète (renvoyer celles à garder). Une réalisation
d'ONG ne peut pas être modifiée par la mairie (`403`).

---

## 9. Listes de référence (filtres et formulaires)

| Besoin | Appel |
|---|---|
| Secteurs (voirie, santé…) | `GET /api/v1/mairie/secteurs/` (`pour_signalement`, `pour_suggestion`, `pour_realisation`) |
| Quartiers de la commune | `GET /api/v1/mairie/quartiers/` (`arrondissement`, `recherche`) |
| Arrondissements | `GET /api/v1/mairie/arrondissements/` |
| Organisations partenaires | `GET /api/v1/mairie/organisations/` (`secteur`, `type`, `statut_habilitation`) |

---

## 10. Gestion des organisations (ONG) par la mairie

| Action | Appel |
|---|---|
| Enregistrer une ONG (habilitée tout de suite, dans votre commune) | `POST /api/v1/mairie/organisations/` — `nom`, `type` (`ONG`, `OSC`, `AUTRE`), `sigle`, `numero_enregistrement` (facultatif, recommandé : évite les doublons entre mairies), contacts, `date_expiration`, `secteurs` |
| Modifier | `PATCH /api/v1/mairie/organisations/{id}/` |
| Ne plus travailler avec elle dans votre commune | `POST /api/v1/mairie/organisations/{id}/retirer-commune/` |
| Comptes de ses membres | `GET` / `POST /api/v1/mairie/organisations/{id}/membres/`, `PATCH …/membres/{membre_id}/` (`actif: false` pour désactiver) |

Conservez l'`id` renvoyé. Si une autre mairie a déjà enregistré l'ONG avec le même numéro, la
réponse est `200` (et non `201`) avec la même fiche : votre commune a été ajoutée à son périmètre.
Les membres se connectent à l'interface des ONG avec leur e-mail et le mot de passe fourni
(provisoire : il leur est demandé de le changer).

---

## 11. Erreurs les plus fréquentes

| Code | HTTP | Que faire |
|---|---|---|
| `CLE_API_INVALIDE` | 401 | Clé fausse, remplacée ou institution désactivée : contacter l'équipe Voix du Citoyen |
| `ESPACE_MAIRIE_REQUIS` | 403 | Adresse sans `/mairie/` : utiliser `/api/v1/mairie/…` |
| `PERMISSION_REFUSEE` | 403 | Action non autorisée (ex. modifier une réalisation d'ONG) |
| `RESSOURCE_INTROUVABLE` | 404 | Élément inexistant ou d'une autre commune |
| `VALIDATION_ERREUR` | 400 | Afficher `details` champ par champ |
| `TRANSITION_STATUT_INVALIDE` | 409 | Proposer seulement `details.statuts_possibles` |
| `SIGNALEMENT_CLOTURE` | 409 | Dossier clos : plus d'assignation ni de changement de statut |
| `CONFLIT` | 409 | Ex. numéro d'enregistrement d'ONG déjà pris |
| `TROP_DE_REQUETES` | 429 | Attendre `details.attente_secondes` |
| `ERREUR_SERVEUR` | 500 | Réessayer plus tard ; nous signaler l'heure de l'appel |

La liste complète est en tête de Swagger.

---

## 12. Pour démarrer

1. Nous transmettre l'identifiant IBDC de la mairie, un e-mail et un téléphone pour le compte
   technique ; nous vous remettons la clé par un canal sûr. Aucun compte d'agent ni service n'est
   à créer chez nous.
2. Vérifier la clé : `GET /api/v1/auth/me/` (doit renvoyer la commune attendue).
3. Explorer chaque appel dans Swagger : bouton **Authorize**, champ `cleApi`, coller la clé.
4. Envoyer `X-Agent` dans chaque appel fait au nom d'un agent.
