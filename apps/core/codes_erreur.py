"""
Codes d'erreur de l'API.

Ces codes sont stables : l'application mobile s'en sert pour afficher ses propres
messages. Ne jamais renommer un code existant. Chaque étape ajoute ses codes ici,
avec son statut HTTP et son message par défaut dans INFOS_ERREURS.
"""

from django.db import models


class CodeErreur(models.TextChoices):
    # --- Génériques ---
    VALIDATION_ERREUR = "VALIDATION_ERREUR"
    NON_AUTHENTIFIE = "NON_AUTHENTIFIE"
    JETON_INVALIDE = "JETON_INVALIDE"
    PERMISSION_REFUSEE = "PERMISSION_REFUSEE"
    RESSOURCE_INTROUVABLE = "RESSOURCE_INTROUVABLE"
    METHODE_NON_AUTORISEE = "METHODE_NON_AUTORISEE"
    CONFLIT = "CONFLIT"
    TROP_DE_REQUETES = "TROP_DE_REQUETES"
    ERREUR_SERVEUR = "ERREUR_SERVEUR"
    SERVICE_INDISPONIBLE = "SERVICE_INDISPONIBLE"

    # --- Authentification ---
    TELEPHONE_DEJA_UTILISE = "TELEPHONE_DEJA_UTILISE"
    IDENTIFIANTS_INVALIDES = "IDENTIFIANTS_INVALIDES"
    TELEPHONE_NON_VERIFIE = "TELEPHONE_NON_VERIFIE"
    COMPTE_DESACTIVE = "COMPTE_DESACTIVE"
    ORGANISATION_NON_HABILITEE = "ORGANISATION_NON_HABILITEE"
    OTP_INVALIDE = "OTP_INVALIDE"
    OTP_EXPIRE = "OTP_EXPIRE"
    OTP_TENTATIVES_DEPASSEES = "OTP_TENTATIVES_DEPASSEES"
    SMS_ECHEC = "SMS_ECHEC"

    # --- Territoire ---
    COORDONNEES_HORS_COMMUNE = "COORDONNEES_HORS_COMMUNE"

    # --- Médias ---
    MEDIA_FORMAT_NON_AUTORISE = "MEDIA_FORMAT_NON_AUTORISE"
    MEDIA_TROP_VOLUMINEUX = "MEDIA_TROP_VOLUMINEUX"
    MEDIA_TROP_LONG = "MEDIA_TROP_LONG"
    MEDIA_ILLISIBLE = "MEDIA_ILLISIBLE"
    MEDIA_INTROUVABLE = "MEDIA_INTROUVABLE"
    MEDIA_DEJA_UTILISE = "MEDIA_DEJA_UTILISE"
    MEDIAS_NON_CONFORMES = "MEDIAS_NON_CONFORMES"

    # --- Signalements ---
    TRANSITION_STATUT_INVALIDE = "TRANSITION_STATUT_INVALIDE"
    SIGNALEMENT_CLOTURE = "SIGNALEMENT_CLOTURE"

    # --- Suggestions ---
    SOUTIEN_PROPRE_SUGGESTION = "SOUTIEN_PROPRE_SUGGESTION"


# code -> (statut HTTP, message par défaut)
INFOS_ERREURS = {
    CodeErreur.VALIDATION_ERREUR: (400, "Certaines informations sont invalides."),
    CodeErreur.NON_AUTHENTIFIE: (401, "Vous devez être connecté pour accéder à ce service."),
    CodeErreur.JETON_INVALIDE: (401, "Votre session a expiré. Veuillez vous reconnecter."),
    CodeErreur.PERMISSION_REFUSEE: (403, "Vous n'avez pas le droit d'effectuer cette action."),
    CodeErreur.RESSOURCE_INTROUVABLE: (404, "L'élément demandé est introuvable."),
    CodeErreur.METHODE_NON_AUTORISEE: (405, "Cette action n'est pas autorisée ici."),
    CodeErreur.CONFLIT: (409, "Cette action entre en conflit avec des données existantes."),
    CodeErreur.TROP_DE_REQUETES: (429, "Trop de demandes. Réessayez un peu plus tard."),
    CodeErreur.ERREUR_SERVEUR: (
        500,
        "Une erreur inattendue s'est produite. Veuillez réessayer plus tard.",
    ),
    CodeErreur.SERVICE_INDISPONIBLE: (
        503,
        "Le service est momentanément indisponible. Veuillez réessayer plus tard.",
    ),
    CodeErreur.TELEPHONE_DEJA_UTILISE: (409, "Ce numéro de téléphone est déjà utilisé."),
    CodeErreur.IDENTIFIANTS_INVALIDES: (401, "Numéro de téléphone ou mot de passe incorrect."),
    CodeErreur.TELEPHONE_NON_VERIFIE: (
        403,
        "Votre numéro n'est pas encore vérifié. Saisissez le code reçu par SMS.",
    ),
    CodeErreur.COMPTE_DESACTIVE: (403, "Votre compte est désactivé. Contactez la mairie."),
    CodeErreur.ORGANISATION_NON_HABILITEE: (
        403,
        "L'habilitation de votre organisation n'est pas active ou a expiré.",
    ),
    CodeErreur.OTP_INVALIDE: (400, "Le code saisi est incorrect."),
    CodeErreur.OTP_EXPIRE: (400, "Ce code a expiré. Demandez-en un nouveau."),
    CodeErreur.OTP_TENTATIVES_DEPASSEES: (
        429,
        "Trop d'essais avec ce code. Demandez-en un nouveau.",
    ),
    CodeErreur.SMS_ECHEC: (
        503,
        "Le SMS n'a pas pu être envoyé. Veuillez réessayer dans quelques instants.",
    ),
    CodeErreur.COORDONNEES_HORS_COMMUNE: (
        400,
        "Cette position se trouve en dehors de la commune.",
    ),
    CodeErreur.MEDIA_FORMAT_NON_AUTORISE: (400, "Ce format de fichier n'est pas accepté."),
    CodeErreur.MEDIA_TROP_VOLUMINEUX: (400, "Ce fichier est trop volumineux."),
    CodeErreur.MEDIA_TROP_LONG: (400, "Cet enregistrement est trop long."),
    CodeErreur.MEDIA_ILLISIBLE: (400, "Ce fichier est illisible ou endommagé."),
    CodeErreur.MEDIA_INTROUVABLE: (
        400,
        "Un ou plusieurs fichiers joints sont introuvables. Envoyez-les à nouveau.",
    ),
    CodeErreur.MEDIA_DEJA_UTILISE: (
        409,
        "Un fichier joint est déjà utilisé ailleurs. Envoyez-le à nouveau.",
    ),
    CodeErreur.MEDIAS_NON_CONFORMES: (
        400,
        "Les fichiers joints ne respectent pas les règles de cet envoi.",
    ),
    CodeErreur.TRANSITION_STATUT_INVALIDE: (409, "Ce changement de statut n'est pas possible."),
    CodeErreur.SIGNALEMENT_CLOTURE: (409, "Ce signalement est clôturé : il ne peut plus être modifié."),
    CodeErreur.SOUTIEN_PROPRE_SUGGESTION: (400, "Vous ne pouvez pas soutenir votre propre suggestion."),
}

# Code générique utilisé quand une erreur n'a pas de code plus précis.
CODE_PAR_STATUT = {
    400: CodeErreur.VALIDATION_ERREUR,
    401: CodeErreur.NON_AUTHENTIFIE,
    403: CodeErreur.PERMISSION_REFUSEE,
    404: CodeErreur.RESSOURCE_INTROUVABLE,
    405: CodeErreur.METHODE_NON_AUTORISEE,
    409: CodeErreur.CONFLIT,
    429: CodeErreur.TROP_DE_REQUETES,
    500: CodeErreur.ERREUR_SERVEUR,
    503: CodeErreur.SERVICE_INDISPONIBLE,
}


def code_pour_statut(statut):
    if statut in CODE_PAR_STATUT:
        return CODE_PAR_STATUT[statut]
    return CodeErreur.ERREUR_SERVEUR if statut >= 500 else CodeErreur.VALIDATION_ERREUR


def statut_http(code):
    return INFOS_ERREURS[code][0]


def message_par_defaut(code):
    return INFOS_ERREURS[code][1]
