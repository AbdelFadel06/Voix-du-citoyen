"""
Introduction générale de la documentation Swagger (/api/docs/ et /api/redoc/).

Le tableau des codes d'erreur est généré depuis codes_erreur.py : il reste à jour
automatiquement quand une étape ajoute ses codes.
"""

from .codes_erreur import INFOS_ERREURS

INTRODUCTION = """
API du module **Voix du Citoyen** de la plateforme LE BAROMETRE : les populations d'une
commune béninoise dialoguent avec leur mairie (signalements, suggestions, réalisations).

Une seule API sert deux clients : l'**application mobile** des citoyens et l'**application
web** de la mairie et des organisations (ONG, OSC). Les réponses s'adaptent au rôle de
l'utilisateur connecté.

---

## Démarrage rapide

### Créer un compte citoyen

1. `POST /api/v1/auth/register/` avec le téléphone, le nom, les prénoms et le mot de passe.
   Le compte est créé **non vérifié** et un **code à 6 chiffres** est envoyé par SMS.
2. `POST /api/v1/auth/otp/verify/` avec le téléphone et le code reçu.
   Le numéro est vérifié et la réponse contient directement les jetons de connexion.
3. SMS non reçu ? `POST /api/v1/auth/otp/resend/` envoie un nouveau code (l'ancien ne
   fonctionne plus).

### Se connecter et appeler l'API

1. `POST /api/v1/auth/login/` — les **citoyens** avec `telephone` + `password`, la **mairie
   et les organisations** avec `email` + `password` — renvoie deux jetons :
   - `access` : à envoyer dans chaque requête, valable **30 minutes** ;
   - `refresh` : sert à obtenir de nouveaux jetons, valable **30 jours**.
2. Envoyer l'en-tête `Authorization: Bearer <access>` sur les endpoints protégés.
   Dans cette page, cliquez sur **Authorize** et collez le jeton `access`.
3. Quand l'API répond `JETON_INVALIDE`, appeler `POST /api/v1/auth/refresh/`.
   Chaque rafraîchissement renvoie un **nouveau** `refresh` : l'ancien devient inutilisable,
   il faut donc toujours conserver le dernier reçu.
4. `POST /api/v1/auth/logout/` invalide le jeton `refresh` à la déconnexion.

### Envoyer un signalement avec photos et enregistrement vocal

1. `POST /api/v1/medias/` pour **chaque** fichier, un par requête (`multipart/form-data`) :
   la réponse donne son `id`. En cas de coupure réseau, seul le fichier en cours est à renvoyer.
2. `GET /api/v1/quartiers/proche/?lat=&lng=` propose le quartier à faire confirmer.
3. `POST /api/v1/signalements/` en JSON avec `medias: [id, …]` et `description_audio: id`.

Les fichiers envoyés mais jamais utilisés sont supprimés au bout de 24 h. Le même principe
vaut pour les suggestions et les réalisations.

### Recevoir les notifications

1. Après la connexion (et à chaque nouveau jeton Firebase) : `POST /api/v1/appareils/`.
2. Les notifications push contiennent `notification_id`, `type`, `cible_type` et `cible_id`
   pour ouvrir le bon écran ; la liste complète est dans `GET /api/v1/notifications/`.
3. À la déconnexion : envoyer `token_fcm` à `POST /api/v1/auth/logout/`.

---

## Format des réponses

Toutes les réponses de `/api/v1/` ont la même forme. Il suffit de tester `succes`.

**Succès**

```json
{
  "succes": true,
  "message": "Compte créé. Un code de vérification vous a été envoyé par SMS.",
  "donnees": { "telephone": "+2290197123456" }
}
```

`message` est un texte de confirmation à afficher, ou `null`. `donnees` contient le résultat.
Une réponse **204** (ex. déconnexion) n'a pas de contenu.

**Liste paginée**

```json
{
  "succes": true,
  "message": null,
  "donnees": [ … ],
  "pagination": {
    "total": 134, "page": 2, "pages": 7, "taille": 20,
    "suivant": "https://…/?page=3", "precedent": "https://…/?page=1"
  }
}
```

Certaines listes de référence (secteurs, quartiers) sont renvoyées **en entier**, sans bloc
`pagination`, pour être gardées en cache par les applications.

**Erreur**

```json
{
  "succes": false,
  "erreur": {
    "code": "VALIDATION_ERREUR",
    "message": "Certaines informations sont invalides.",
    "details": { "telephone": ["Saisissez un numéro de téléphone valide."] }
  }
}
```

- `code` : **stable**, à utiliser par les applications pour réagir (afficher un écran,
  proposer une action). Il ne change jamais.
- `message` : en français, compréhensible par un citoyen, affichable tel quel.
- `details` : `null` en général ; erreurs par champ pour `VALIDATION_ERREUR` ;
  `{"attente_secondes": n}` pour `TROP_DE_REQUETES` (avec l'en-tête `Retry-After`).

Une erreur 500 ne révèle jamais de détail technique.

---

## Codes d'erreur

{tableau_codes}

---

## Rôles

| Rôle | Client | Droits |
|---|---|---|
| `CITOYEN` | Mobile | Créer un compte, signaler, suggérer, soutenir une suggestion, suivre ses dossiers, voir les réalisations |
| `AGENT` | Web | Traiter les signalements et suggestions, publier des réalisations |
| `ADMIN_MAIRIE` | Web | Tout ce que fait l'agent + gestion des agents, services, secteurs, quartiers et organisations |
| `ORGANISATION` | Web | **Lecture seule** : signalements, suggestions, réalisations, tableaux de bord |

- Une organisation **suspendue** ou dont l'habilitation a **expiré** perd l'accès
  immédiatement, même avec un jeton encore valide (`ORGANISATION_NON_HABILITEE`).
- **Les citoyens restent anonymes** : personne (ni la mairie, ni les organisations, ni les
  autres citoyens) ne reçoit le nom ou le téléphone de l'auteur d'un signalement ou d'une
  suggestion. Seul l'auteur voit son identité sur ses propres dossiers.

---

## Conventions

- **Téléphones** : numéros béninois. Saisie acceptée au format national (`0197123456`)
  ou international (`+229 01 97 12 34 56`) ; toujours renvoyés au format `+2290197123456`.
- **Dates** : ISO 8601 avec fuseau horaire (`2026-10-06T15:58:21+01:00`, heure de Porto-Novo).
- **Coordonnées GPS** : degrés décimaux (WGS 84), 6 décimales.
- **Pagination** : `?page=` (à partir de 1) et `?taille=` (20 par défaut, 100 au maximum).
- **Recherche et tri** : `?recherche=` et `?tri=` (préfixe `-` pour l'ordre décroissant),
  sur les listes qui les proposent.
- **Limitation de débit** : au-delà, l'API répond `TROP_DE_REQUETES` (429).
  Demandes de code SMS (inscription + renvoi) : **5 par heure et par numéro** ;
  signalements : **10 par jour et par citoyen** ; envois de fichiers : **60 par heure**.
- **Réalisations** : consultables **sans compte** (`GET /api/v1/realisations/`).
- **Tableaux de bord** (`/api/v1/dashboard/…`) : mairie et organisations habilitées.
- **Langue** : tous les messages sont en français.
"""


def tableau_codes():
    lignes = ["| Code | HTTP | Message par défaut |", "|---|---|---|"]
    for code, (statut, message) in INFOS_ERREURS.items():
        lignes.append(f"| `{code.value}` | {statut} | {message} |")
    return "\n".join(lignes)


def introduction():
    return INTRODUCTION.replace("{tableau_codes}", tableau_codes()).strip()
