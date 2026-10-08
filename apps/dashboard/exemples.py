"""Données d'exemple affichées dans la documentation Swagger des tableaux de bord."""

_SIGNALEMENTS = {
    "total": 342,
    "par_statut": {"SOUMIS": 21, "RECU": 34, "EN_COURS": 58, "RESOLU": 201, "REJETE": 17, "DOUBLON": 11},
    "ouverts": 113,
    "resolus": 201,
    "taux_resolution": 58.8,
    "delai_moyen_resolution_jours": 9.4,
}
_REALISATIONS = {
    "total": 27,
    "par_statut": {"PLANIFIEE": 6, "EN_COURS": 9, "TERMINEE": 11, "SUSPENDUE": 1},
    "budget_total": 1265000000,
    "taux_avancement_moyen": 64.3,
}
SYNTHESE_MAIRIE = {
    "signalements": _SIGNALEMENTS,
    "suggestions": {"total": 88, "nb_soutiens": 1742, "pertinentes": 14},
    "realisations": {**_REALISATIONS, "total": 31, "brouillons": 4},
}
SYNTHESE_ORGANISATION = {
    "signalements": _SIGNALEMENTS,
    "realisations": _REALISATIONS,
}

PAR_SECTEUR = [
    {
        "secteur": {"id": 1, "nom": "Voirie", "code": "VOIRIE", "couleur": "#F57C00"},
        "signalements": 128, "signalements_ouverts": 41, "signalements_resolus": 74,
        "taux_resolution": 57.8, "suggestions": 19, "realisations": 12,
    },
    {
        "secteur": {"id": 3, "nom": "Insalubrité", "code": "INSALUBRITE", "couleur": "#6D4C41"},
        "signalements": 96, "signalements_ouverts": 30, "signalements_resolus": 58,
        "taux_resolution": 60.4, "suggestions": 11, "realisations": 4,
    },
]

PAR_QUARTIER = [
    {
        "quartier": {"id": 12, "nom": "Togoudo", "arrondissement": "Godomey"},
        "signalements": 47, "signalements_ouverts": 12, "signalements_resolus": 31,
        "taux_resolution": 66.0, "suggestions": 6, "realisations": 3,
    },
    {
        "quartier": {"id": 15, "nom": "Zogbadjè", "arrondissement": "Abomey-Calavi"},
        "signalements": 39, "signalements_ouverts": 15, "signalements_resolus": 20,
        "taux_resolution": 51.3, "suggestions": 9, "realisations": 2,
    },
]

EVOLUTION = {
    "periode": "mois",
    "date_debut": "2026-08-01",
    "date_fin": "2026-10-06",
    "points": [
        {"periode": "2026-08-01", "signalements_crees": 41, "signalements_resolus": 29, "suggestions_creees": 8},
        {"periode": "2026-09-01", "signalements_crees": 56, "signalements_resolus": 44, "suggestions_creees": 12},
        {"periode": "2026-10-01", "signalements_crees": 9, "signalements_resolus": 7, "suggestions_creees": 2},
    ],
}

CARTE = {
    "signalements": [
        {
            "id": 128, "reference": "SIG-2026-00128", "titre": "Gros nid-de-poule devant l'école",
            "statut": "EN_COURS", "secteur": {"id": 1, "code": "VOIRIE", "couleur": "#F57C00"},
            "latitude": "6.401234", "longitude": "2.341234", "cree_le": "2026-10-06T16:21:40+01:00",
        }
    ],
    "signalements_tronques": False,
    "quartiers": [
        {"quartier": {"id": 12, "nom": "Togoudo", "arrondissement": "Godomey"},
         "latitude": "6.400000", "longitude": "2.340000", "signalements": 47},
    ],
    "realisations": [
        {"id": 4, "reference": "REA-2026-00004", "titre": "Pavage de la rue de l'EPP Togoudo",
         "statut": "EN_COURS", "latitude": "6.401500", "longitude": "2.341800"},
    ],
}
