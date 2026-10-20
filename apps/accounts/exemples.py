"""Données d'exemple affichées dans la documentation Swagger de l'authentification."""

TELEPHONE = "+2290197123456"

ACCESS = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwidXNlcl9pZCI6IjQyIn0"
    ".exemple-de-signature-access"
)
REFRESH = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsInVzZXJfaWQiOiI0MiJ9"
    ".exemple-de-signature-refresh"
)

CITOYEN = {
    "id": 42,
    "telephone": TELEPHONE,
    "nom": "Hounkpatin",
    "prenoms": "Afiavi",
    "email": None,
    "role": "CITOYEN",
    "quartier_residence": 12,
    "organisation": None,
    "service": None,
    "telephone_verifie": True,
    "date_joined": "2026-10-06T15:58:21+01:00",
}

AGENT = {
    **CITOYEN,
    "id": 7,
    "telephone": "+2290196000007",
    "nom": "Ahouansou",
    "prenoms": "Rodrigue",
    "email": "r.ahouansou@mairie.bj",
    "role": "AGENT",
    "quartier_residence": None,
    "service": {"id": 3, "nom": "Voirie et assainissement"},
}

ORGANISATION = {
    **CITOYEN,
    "id": 15,
    "telephone": "+2290195000015",
    "nom": "Dossou",
    "prenoms": "Mireille",
    "email": "contact@ong-eau.bj",
    "role": "ORGANISATION",
    "quartier_residence": None,
    "organisation": {
        "id": 2,
        "nom": "ONG Eau Pour Tous",
        "sigle": "EPT",
        "communes": [{"id": 1, "nom": "Parakou"}],
        "secteurs": [{"id": 4, "nom": "Eau et assainissement", "code": "EAU"}],
    },
}

JETONS = {"access": ACCESS, "refresh": REFRESH, "utilisateur": CITOYEN}

# Organisations et statistiques (vues par la mairie).
STATISTIQUES = {
    "signalements": 48,
    "en_attente": 6,
    "en_cours": 12,
    "ouverts": 18,
    "resolus": 27,
    "rejetes": 3,
    "taux_resolution": 56.3,
    "delai_moyen_resolution_jours": 9.4,
}
STATISTIQUES_GLOBALES = {**STATISTIQUES, "pris_en_charge": 11, "resolus_pris_en_charge": 7, "realisations_publiees": 2}
ORGANISATION_LISTE = {
    "id": 2,
    "nom": "ONG Eau Pour Tous",
    "sigle": "EPT",
    "type": "ONG",
    "statut_habilitation": "HABILITEE",
    "date_expiration": "2027-12-31",
    "acces_actif": True,
    "communes": [{"id": 1, "nom": "Parakou"}],
    "secteurs": [
        {"id": 4, "nom": "Eau et assainissement", "code": "EAU"},
        {"id": 2, "nom": "Santé", "code": "SANTE"},
    ],
    "nb_comptes": 3,
    "statistiques": STATISTIQUES_GLOBALES,
}
ORGANISATION_DETAIL = {
    **ORGANISATION_LISTE,
    "numero_enregistrement": "2019/0457/MISP/DC/SG",
    "email": "contact@ong-eau.bj",
    "telephone": "+2290195000015",
    "adresse": "Quartier Banikanni, Parakou",
    "date_habilitation": "2026-10-08",
    "motif_suspension": "",
    "statistiques_par_commune": [{"commune": {"id": 1, "nom": "Parakou"}, **STATISTIQUES}],
    "statistiques_par_secteur": [
        {
            "secteur": {"id": 4, "nom": "Eau et assainissement", "code": "EAU"},
            "signalements": 30, "en_attente": 4, "en_cours": 8, "ouverts": 12, "resolus": 16, "rejetes": 2,
            "taux_resolution": 53.3, "delai_moyen_resolution_jours": 11.2,
        },
        {
            "secteur": {"id": 2, "nom": "Santé", "code": "SANTE"},
            "signalements": 18, "en_attente": 2, "en_cours": 4, "ouverts": 6, "resolus": 11, "rejetes": 1,
            "taux_resolution": 61.1, "delai_moyen_resolution_jours": 6.5,
        },
    ],
}
