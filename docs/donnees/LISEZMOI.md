# Données réelles de Parakou

À charger dans cet ordre, avec un compte admin de la plateforme :

1. `POST /api/v1/communes/` avec le contenu de `parakou_commune.json`.
2. `POST /api/v1/quartiers/import/` avec `parakou_quartiers.csv` (crée les 3 arrondissements
   et les 58 quartiers ; essayer d'abord avec `simulation=true`).

Ou en ligne de commande, une fois la commune créée :
`python manage.py charger_quartiers docs/donnees/parakou_quartiers.csv --commune PKO`.

## Sources

- **Liste des quartiers** : loi n° 2013-05 du 15 février 2013 portant création, organisation,
  attributions et fonctionnement des unités administratives locales (annexe : « Commune de
  Parakou : 58 quartiers de ville » ; 29 dans le 1er arrondissement, 17 dans le 2e, 12 dans
  le 3e), publiée par le Secrétariat général du Gouvernement (sgg.gouv.bj). Noms recopiés
  tels quels, coquilles de numérisation corrigées (ex. « VVoré » → « Woré »).
- **Emprise de la commune** : limite administrative de Parakou dans OpenStreetMap
  (relation 2859964), arrondie à 6 décimales (environ 10 cm).
- **Centres de quartier** : renseignés seulement pour les 15 quartiers présents dans
  OpenStreetMap comme lieux nommés (`place=*`). Les autres sont vides : à compléter avec
  la mairie (le centre sert à `GET /quartiers/proche/`, qui ne propose que les quartiers
  ayant un centre). Données OpenStreetMap © contributeurs OSM, licence ODbL.
