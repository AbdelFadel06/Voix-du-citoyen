"""
Logique métier des signalements (CLAUDE.md § 6).

L'auteur est notifié à chaque changement de statut et à chaque réponse officielle.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.references import prochaine_reference
from apps.medias import services as medias
from apps.medias.regles import RATTACHEMENT_SIGNALEMENT
from apps.notifications import services as notifications

from .models import Signalement, SuiviSignalement

Statut = Signalement.Statut
TypeEvenement = SuiviSignalement.TypeEvenement

PREFIXE_REFERENCE = "SIG"
SEUIL_PRECISION_GPS_METRES = 100
LONGUEUR_TITRE = Signalement._meta.get_field("titre").max_length

# Transitions autorisées : la chaîne SOUMIS → RECU → EN_COURS → RESOLU, et les sorties
# REJETE / DOUBLON tant que le dossier n'est pas clos. Les statuts clos sont définitifs.
TRANSITIONS = {
    Statut.SOUMIS: {Statut.RECU, Statut.REJETE, Statut.DOUBLON},
    Statut.RECU: {Statut.EN_COURS, Statut.REJETE, Statut.DOUBLON},
    Statut.EN_COURS: {Statut.RESOLU, Statut.REJETE, Statut.DOUBLON},
    Statut.RESOLU: set(),
    Statut.REJETE: set(),
    Statut.DOUBLON: set(),
}


def _coordonnee(valeur):
    return Decimal(str(round(valeur, 6)))


def titre_genere(secteur, quartier):
    return f"{secteur.nom} – {quartier.nom}"[:LONGUEUR_TITRE]


# ---------------------------------------------------------------------------
# Création
# ---------------------------------------------------------------------------


@transaction.atomic
def creer_signalement(
    *,
    auteur,
    secteur,
    quartier,
    mode_localisation,
    medias_ids,
    titre="",
    description_texte="",
    description_audio_id=None,
    anonyme=False,
    latitude=None,
    longitude=None,
    precision_gps=None,
    repere="",
):
    """
    Crée un signalement (statut SOUMIS) et rattache ses médias.
    Renvoie (signalement, avertissements) ; les avertissements n'empêchent pas la création.
    """
    avertissements = []
    if mode_localisation == Signalement.ModeLocalisation.GPS:
        latitude, longitude = _coordonnee(latitude), _coordonnee(longitude)
        if not quartier.arrondissement.commune.contient(latitude, longitude):
            raise ErreurMetier(CodeErreur.COORDONNEES_HORS_COMMUNE)
        if precision_gps > SEUIL_PRECISION_GPS_METRES:
            avertissements.append(
                {
                    "code": "GPS_IMPRECIS",
                    "message": f"La position GPS est imprécise (± {precision_gps} m). "
                    "Vérifiez que le quartier indiqué est le bon.",
                }
            )
    else:
        latitude = longitude = precision_gps = None

    photos_videos = medias.verifier_medias(auteur, medias_ids, RATTACHEMENT_SIGNALEMENT)
    audio = medias.verifier_audio(auteur, description_audio_id) if description_audio_id else None

    titre = titre.strip()
    signalement = Signalement.objects.create(
        reference=prochaine_reference(Signalement, PREFIXE_REFERENCE),
        titre=titre or titre_genere(secteur, quartier),
        titre_genere=not titre,
        description_texte=description_texte.strip(),
        description_audio=audio,
        secteur=secteur,
        auteur=auteur,
        anonyme=anonyme,
        mode_localisation=mode_localisation,
        latitude=latitude,
        longitude=longitude,
        precision_gps=precision_gps,
        quartier=quartier,
        repere=repere.strip(),
        service_assigne=secteur.service_par_defaut,
    )
    signalement.medias.set(photos_videos)
    medias.attacher([*photos_videos, *([audio] if audio else [])])
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.CHANGEMENT_STATUT,
        nouveau_statut=Statut.SOUMIS,
        commentaire="Signalement envoyé à la mairie.",
        auteur=auteur,
    )
    return signalement, avertissements


# ---------------------------------------------------------------------------
# Traitement par la mairie
# ---------------------------------------------------------------------------


def _verrouiller(signalement):
    return Signalement.objects.select_for_update().get(pk=signalement.pk)


@transaction.atomic
def changer_statut(signalement, *, par, statut, commentaire="", doublon_de=None):
    signalement = _verrouiller(signalement)
    ancien = signalement.statut
    possibles = TRANSITIONS[ancien]
    if statut not in possibles:
        raise ErreurMetier(
            CodeErreur.TRANSITION_STATUT_INVALIDE,
            f"Impossible de passer de « {Statut(ancien).label} » à « {Statut(statut).label} ».",
            details={"statut_actuel": ancien, "statuts_possibles": sorted(possibles)},
        )
    commentaire = commentaire.strip()
    if statut == Statut.REJETE and not commentaire:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR,
            details={"commentaire": ["Le motif du rejet est obligatoire."]},
        )
    if statut == Statut.DOUBLON:
        if doublon_de is None:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={"doublon_de": ["Indiquez le signalement d'origine."]},
            )
        if doublon_de.pk == signalement.pk or doublon_de.statut == Statut.DOUBLON:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={"doublon_de": ["Indiquez un autre signalement, qui ne soit pas lui-même un doublon."]},
            )
        signalement.doublon_de = doublon_de
        if not commentaire:
            commentaire = f"Ce problème est déjà suivi dans le signalement {doublon_de.reference}."

    signalement.statut = statut
    if statut == Statut.RESOLU:
        signalement.date_resolution = timezone.now()
    signalement.save(update_fields=["statut", "doublon_de", "date_resolution", "maj_le"])
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.CHANGEMENT_STATUT,
        ancien_statut=ancien,
        nouveau_statut=statut,
        commentaire=commentaire,
        auteur=par,
    )
    notifications.notifier_statut_signalement(signalement, commentaire)
    return signalement


@transaction.atomic
def assigner(signalement, *, par, service=None, agent=None):
    signalement = _verrouiller(signalement)
    if signalement.est_cloture:
        raise ErreurMetier(CodeErreur.SIGNALEMENT_CLOTURE)
    if agent is not None:
        if service is not None and agent.service_id != service.pk:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={"agent": [f"Cet agent ne fait pas partie du service « {service.nom} »."]},
            )
        service = agent.service
    signalement.service_assigne = service
    signalement.agent_assigne = agent
    signalement.save(update_fields=["service_assigne", "agent_assigne", "maj_le"])
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.ASSIGNATION,
        commentaire=f"Dossier confié au service « {service.nom} ».",
        auteur=par,
    )
    return signalement


@transaction.atomic
def repondre(signalement, *, par, commentaire, interne=False):
    """Réponse officielle (visible et notifiée au citoyen) ou note interne (mairie seulement)."""
    commentaire = commentaire.strip()
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.NOTE_INTERNE if interne else TypeEvenement.REPONSE,
        commentaire=commentaire,
        visible_citoyen=not interne,
        auteur=par,
    )
    Signalement.objects.filter(pk=signalement.pk).update(maj_le=timezone.now())
    if not interne:
        notifications.notifier_reponse_signalement(signalement, commentaire)
    return signalement
