"""Données d'exemple affichées dans la documentation Swagger des réalisations."""

from apps.signalements.exemples import MINIATURE, PHOTO

SECTEUR = {"id": 1, "nom": "Voirie", "code": "VOIRIE", "icone": "route", "couleur": "#F57C00"}
QUARTIERS = [
    {"id": 12, "nom": "Togoudo", "arrondissement": "Godomey"},
    {"id": 13, "nom": "Cococodji", "arrondissement": "Godomey"},
]

LISTE = {
    "id": 4,
    "reference": "REA-2026-00004",
    "titre": "Pavage de la rue de l'EPP Togoudo",
    "secteur": SECTEUR,
    "statut": "EN_COURS",
    "taux_avancement": 60,
    "quartiers": QUARTIERS,
    "date_debut_prevue": "2026-09-01",
    "date_fin_prevue": "2026-12-15",
    "couverture": {"phase": "AVANT", "media": MINIATURE},
    "nb_medias": 3,
    "cree_le": "2026-08-20T11:00:00+01:00",
    "maj_le": "2026-10-05T17:30:00+01:00",
}
LISTE_MAIRIE = {**LISTE, "publie": True}
BROUILLON = {
    **LISTE,
    "id": 5,
    "reference": "REA-2026-00005",
    "titre": "Curage des caniveaux de Cococodji",
    "statut": "PLANIFIEE",
    "taux_avancement": 0,
    "couverture": None,
    "nb_medias": 0,
    "publie": False,
}

DETAIL = {
    **LISTE,
    "description": "Pavage de 850 m de rue et pose de caniveaux couverts, suite aux signalements "
    "des parents d'élèves.",
    "date_debut_reelle": "2026-09-08",
    "date_fin_reelle": None,
    "budget": 185000000,
    "source_financement": "Budget communal 2026 et FADeC",
    "prestataire": "Entreprise BTP Bénin SARL",
    "latitude": "6.401234",
    "longitude": "2.341234",
    "medias": [
        {"phase": "AVANT", "legende": "La rue en saison des pluies", "ordre": 0, "media": {**PHOTO, "statut": "ATTACHE"}},
        {"phase": "PENDANT", "legende": "Pose des pavés", "ordre": 1, "media": {**PHOTO, "statut": "ATTACHE"}},
    ],
    "signalements": [{"id": 128, "reference": "SIG-2026-00128", "titre": "Gros nid-de-poule devant l'école", "statut": "RESOLU"}],
    "suggestions": [],
}
DETAIL_MAIRIE = {**DETAIL, "publie": True, "cree_par": {"id": 7, "nom": "Ahouansou", "prenoms": "Rodrigue"}}

REQUETE_CREATION = {
    "titre": "Pavage de la rue de l'EPP Togoudo",
    "description": "Pavage de 850 m de rue et pose de caniveaux couverts.",
    "secteur": 1,
    "quartiers": [12, 13],
    "statut": "PLANIFIEE",
    "date_debut_prevue": "2026-09-01",
    "date_fin_prevue": "2026-12-15",
    "budget": 185000000,
    "source_financement": "Budget communal 2026 et FADeC",
    "prestataire": "Entreprise BTP Bénin SARL",
    "latitude": 6.401234,
    "longitude": 2.341234,
    "signalements": [128],
    "medias": [{"media": PHOTO["id"], "phase": "AVANT", "legende": "La rue en saison des pluies"}],
    "publie": False,
}
REQUETE_AVANCEMENT = {
    "statut": "EN_COURS",
    "taux_avancement": 60,
    "date_debut_reelle": "2026-09-08",
    "medias": [
        {"media": PHOTO["id"], "phase": "AVANT", "legende": "La rue en saison des pluies"},
        {"media": "7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", "phase": "PENDANT", "legende": "Pose des pavés"},
    ],
}
REQUETE_PUBLICATION = {"publie": True}
