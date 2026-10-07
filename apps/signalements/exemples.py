"""Données d'exemple affichées dans la documentation Swagger des signalements."""

URL = "https://api.exemple.bj/media/medias"
ID_PHOTO = "3f6c1a2e-8b4d-4c1e-9a7f-2d5e6b8c9a01"
ID_AUDIO = "c4d5e6f7-a8b9-4c0d-9e1f-2a3b4c5d6e7f"

SECTEUR = {"id": 1, "nom": "Voirie", "code": "VOIRIE", "icone": "route", "couleur": "#F57C00"}
QUARTIER = {"id": 12, "nom": "Togoudo", "arrondissement": "Godomey"}
MINIATURE = {
    "id": ID_PHOTO,
    "type": "IMAGE",
    "miniature": f"{URL}/miniatures/2026/10/{ID_PHOTO}.jpg",
    "duree_secondes": None,
}
PHOTO = {
    **MINIATURE,
    "statut": "ATTACHE",
    "fichier": f"{URL}/image/2026/10/{ID_PHOTO}.jpg",
    "mime_type": "image/jpeg",
    "taille_octets": 1843200,
    "largeur": 3000,
    "hauteur": 4000,
    "cree_le": "2026-10-06T16:20:11+01:00",
}
AUDIO = {
    **PHOTO,
    "id": ID_AUDIO,
    "type": "AUDIO",
    "fichier": f"{URL}/audio/2026/10/{ID_AUDIO}.m4a",
    "miniature": None,
    "mime_type": "audio/x-m4a",
    "taille_octets": 958464,
    "duree_secondes": 47,
    "largeur": None,
    "hauteur": None,
}

AUTEUR_COMPLET = {
    "nom_affiche": "Afiavi H.",
    "id": 42,
    "nom": "Hounkpatin",
    "prenoms": "Afiavi",
    "telephone": "+2290197123456",
}
AUTEUR_PUBLIC = {**AUTEUR_COMPLET, "id": None, "nom": None, "prenoms": None, "telephone": None}

# Vu par un citoyen qui n'est pas l'auteur.
LISTE_CITOYEN = {
    "id": 128,
    "reference": "SIG-2026-00128",
    "titre": "Gros nid-de-poule devant l'école",
    "statut": "EN_COURS",
    "secteur": SECTEUR,
    "quartier": QUARTIER,
    "mode_localisation": "GPS",
    "latitude": "6.401234",
    "longitude": "2.341234",
    "repere": "Devant l'EPP Togoudo",
    "medias": [MINIATURE],
    "a_description_audio": True,
    "anonyme": False,
    "auteur": AUTEUR_PUBLIC,
    "est_auteur": False,
    "cree_le": "2026-10-06T16:21:40+01:00",
    "maj_le": "2026-10-07T09:02:13+01:00",
}

# Vu par un agent ou un admin mairie.
LISTE_MAIRIE = {
    **LISTE_CITOYEN,
    "auteur": AUTEUR_COMPLET,
    "priorite": "HAUTE",
    "service_assigne": {"id": 3, "nom": "Voirie et assainissement"},
    "agent_assigne": {"id": 7, "nom": "Ahouansou", "prenoms": "Rodrigue"},
}

HISTORIQUE_CITOYEN = [
    {
        "id": 501,
        "type_evenement": "CHANGEMENT_STATUT",
        "ancien_statut": "",
        "nouveau_statut": "SOUMIS",
        "commentaire": "Signalement envoyé à la mairie.",
        "par_la_mairie": False,
        "cree_le": "2026-10-06T16:21:40+01:00",
    },
    {
        "id": 502,
        "type_evenement": "ASSIGNATION",
        "ancien_statut": "",
        "nouveau_statut": "",
        "commentaire": "Dossier confié au service « Voirie et assainissement ».",
        "par_la_mairie": True,
        "cree_le": "2026-10-07T08:45:02+01:00",
    },
    {
        "id": 503,
        "type_evenement": "CHANGEMENT_STATUT",
        "ancien_statut": "RECU",
        "nouveau_statut": "EN_COURS",
        "commentaire": "Une équipe interviendra cette semaine.",
        "par_la_mairie": True,
        "cree_le": "2026-10-07T09:02:13+01:00",
    },
]

HISTORIQUE_MAIRIE = [
    {**evenement, "auteur_nom": nom, "visible_citoyen": True}
    for evenement, nom in zip(HISTORIQUE_CITOYEN, ["Afiavi Hounkpatin", "Rodrigue Ahouansou", "Rodrigue Ahouansou"])
] + [
    {
        "id": 504,
        "type_evenement": "NOTE_INTERNE",
        "ancien_statut": "",
        "nouveau_statut": "",
        "commentaire": "Prévoir 2 m³ de latérite, camion disponible jeudi.",
        "par_la_mairie": True,
        "auteur_nom": "Rodrigue Ahouansou",
        "visible_citoyen": False,
        "cree_le": "2026-10-07T09:05:30+01:00",
    }
]

_DETAIL = {
    "titre_genere": False,
    "description_texte": "Le trou fait presque un mètre, les zémidjans l'évitent en roulant sur le trottoir.",
    "description_audio": AUDIO,
    "medias": [PHOTO],
    "precision_gps": 12,
    "doublon_de": None,
    "date_resolution": None,
}
DETAIL_CITOYEN = {**LISTE_CITOYEN, **_DETAIL, "historique": HISTORIQUE_CITOYEN}
DETAIL_MAIRIE = {**LISTE_MAIRIE, **_DETAIL, "historique": HISTORIQUE_MAIRIE}

CREE = {
    **LISTE_CITOYEN,
    **_DETAIL,
    "auteur": AUTEUR_COMPLET,
    "est_auteur": True,
    "statut": "SOUMIS",
    "historique": HISTORIQUE_CITOYEN[:1],
    "avertissements": [],
}
CREE_GPS_IMPRECIS = {
    **CREE,
    "precision_gps": 150,
    "avertissements": [
        {
            "code": "GPS_IMPRECIS",
            "message": "La position GPS est imprécise (± 150 m). Vérifiez que le quartier indiqué est le bon.",
        }
    ],
}

REQUETE_GPS = {
    "secteur": 1,
    "titre": "Gros nid-de-poule devant l'école",
    "description_texte": "Le trou fait presque un mètre, les zémidjans l'évitent en roulant sur le trottoir.",
    "medias": [ID_PHOTO],
    "mode_localisation": "GPS",
    "latitude": 6.4012345,
    "longitude": 2.3412345,
    "precision_gps": 12,
    "quartier": 12,
    "repere": "Devant l'EPP Togoudo",
}
REQUETE_VOCALE = {
    "secteur": 2,
    "description_audio": ID_AUDIO,
    "medias": [ID_PHOTO],
    "mode_localisation": "MANUEL",
    "quartier": 12,
    "repere": "Derrière le marché de Godomey",
    "anonyme": True,
}
