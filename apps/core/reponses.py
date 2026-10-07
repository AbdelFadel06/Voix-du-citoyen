"""
Construction des réponses au format commun de l'API.

Succès : {"succes": true,  "message": str | null, "donnees": ...}
Erreur : {"succes": false, "erreur": {"code": str, "message": str, "details": ... | null}}
"""

from rest_framework import status
from rest_framework.response import Response


def corps_succes(donnees=None, message=None):
    return {"succes": True, "message": message, "donnees": donnees}


def corps_erreur(code, message, details=None):
    return {"succes": False, "erreur": {"code": str(code), "message": message, "details": details}}


def est_enveloppe(donnees):
    return isinstance(donnees, dict) and "succes" in donnees


def reponse_succes(donnees=None, message=None, status=status.HTTP_200_OK, **kwargs):
    """À utiliser dans les vues pour renvoyer un succès avec un message à afficher."""
    return Response(corps_succes(donnees, message), status=status, **kwargs)
