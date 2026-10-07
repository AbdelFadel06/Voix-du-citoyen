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
    "organisation": {"id": 2, "nom": "ONG Eau Pour Tous", "sigle": "EPT"},
}

JETONS = {"access": ACCESS, "refresh": REFRESH, "utilisateur": CITOYEN}
