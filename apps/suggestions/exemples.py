"""Données d'exemple affichées dans la documentation Swagger des suggestions."""

from apps.signalements.exemples import AUTEUR_COMPLET, AUTEUR_PUBLIC, MINIATURE, PHOTO

SECTEUR = {"id": 4, "nom": "Cadre de vie", "code": "CADRE_VIE", "icone": "arbre", "couleur": "#43A047"}
QUARTIER = {"id": 15, "nom": "Zogbadjè", "arrondissement": "Abomey-Calavi"}

# Vue par un citoyen (ni `est_pertinente` ni identité complète de l'auteur).
LISTE = {
    "id": 31,
    "reference": "SUG-2026-00031",
    "titre": "Installer des bancs à l'ombre au marché de Zogbadjè",
    "secteur": SECTEUR,
    "quartier": QUARTIER,
    "nb_soutiens": 57,
    "je_soutiens": True,
    "medias": [MINIATURE],
    "auteur": AUTEUR_PUBLIC,
    "est_auteur": False,
    "a_reponse": True,
    "cree_le": "2026-09-14T10:12:00+01:00",
    "maj_le": "2026-10-02T15:40:00+01:00",
}
LISTE_COMMUNE = {
    **LISTE,
    "id": 32,
    "reference": "SUG-2026-00032",
    "titre": "Une journée de salubrité chaque premier samedi du mois",
    "quartier": None,
    "nb_soutiens": 12,
    "je_soutiens": False,
    "medias": [],
    "a_reponse": False,
}
LISTE_MAIRIE = {**LISTE, "auteur": AUTEUR_COMPLET, "je_soutiens": False, "est_pertinente": True}

HISTORIQUE = [
    {
        "id": 803,
        "type_evenement": "REPONSE",
        "commentaire": "Merci : 10 bancs sont prévus au budget 2027.",
        "par_la_mairie": True,
        "cree_le": "2026-10-02T15:40:00+01:00",
    },
]
HISTORIQUE_MAIRIE = [
    {
        "id": 802,
        "type_evenement": "NOTE_INTERNE",
        "commentaire": "Voir le devis du menuisier de Zogbadjè.",
        "par_la_mairie": True,
        "auteur_nom": "Rodrigue Ahouansou",
        "visible_citoyen": False,
        "cree_le": "2026-09-20T09:00:00+01:00",
    },
    {**HISTORIQUE[0], "auteur_nom": "Rodrigue Ahouansou", "visible_citoyen": True},
]

DETAIL = {
    **LISTE,
    "medias": [PHOTO],
    "description": "Les vendeuses et les clients attendent debout en plein soleil. Quelques bancs "
    "sous les arbres près de l'entrée rendraient le marché plus agréable.",
    "reponse_officielle": "Merci : 10 bancs sont prévus au budget 2027.",
    "repondu_le": "2026-10-02T15:40:00+01:00",
    "historique": HISTORIQUE,
}
DETAIL_MAIRIE = {
    **DETAIL,
    **{k: LISTE_MAIRIE[k] for k in ("auteur", "je_soutiens", "est_pertinente")},
    "repondu_par": {"id": 7, "nom": "Ahouansou", "prenoms": "Rodrigue"},
    "historique": HISTORIQUE_MAIRIE,
}
CREEE = {
    **DETAIL,
    "nb_soutiens": 0,
    "je_soutiens": False,
    "auteur": AUTEUR_COMPLET,
    "est_auteur": True,
    "a_reponse": False,
    "reponse_officielle": "",
    "repondu_le": None,
    "historique": [],
}

REQUETE = {
    "titre": "Installer des bancs à l'ombre au marché de Zogbadjè",
    "description": "Les vendeuses et les clients attendent debout en plein soleil.",
    "secteur": 4,
    "quartier": 15,
    "medias": [PHOTO["id"]],
}
REQUETE_COMMUNE = {
    "titre": "Une journée de salubrité chaque premier samedi du mois",
    "description": "Chaque quartier nettoierait ses rues et ses caniveaux le même jour.",
    "secteur": 4,
}
