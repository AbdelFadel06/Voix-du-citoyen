"""
Logique métier des signalements (CLAUDE.md § 6).

L'auteur est notifié à chaque changement de statut et à chaque réponse officielle.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.core.communes import commune_de_l_auteur, controler_quartier
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
# Statuts qu'une organisation en charge peut donner : rejeter un dossier ou le classer comme
# doublon reste une décision de la mairie.
STATUTS_ORGANISATION = {Statut.RECU, Statut.EN_COURS, Statut.RESOLU}


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
    commune = commune_de_l_auteur(auteur)
    controler_quartier(quartier, commune)
    if mode_localisation == Signalement.ModeLocalisation.GPS:
        latitude, longitude = _coordonnee(latitude), _coordonnee(longitude)
        if not commune.contient(latitude, longitude):
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
    # Les secteurs sont communs à toutes les communes : leur service par défaut n'est retenu
    # que s'il appartient à la mairie de cette commune.
    service = secteur.service_par_defaut
    if service is not None and service.commune_id != commune.pk:
        service = None
    signalement = Signalement.objects.create(
        reference=prochaine_reference(Signalement, PREFIXE_REFERENCE),
        commune=commune,
        titre=titre or titre_genere(secteur, quartier),
        titre_genere=not titre,
        description_texte=description_texte.strip(),
        description_audio=audio,
        secteur=secteur,
        auteur=auteur,
        mode_localisation=mode_localisation,
        latitude=latitude,
        longitude=longitude,
        precision_gps=precision_gps,
        quartier=quartier,
        repere=repere.strip(),
        service_assigne=service,
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
    notifications.notifier_nouveau_signalement(signalement)
    return signalement, avertissements


# ---------------------------------------------------------------------------
# Traitement par la mairie
# ---------------------------------------------------------------------------


def _verrouiller(signalement):
    return Signalement.objects.select_for_update().get(pk=signalement.pk)


@transaction.atomic
def changer_statut(signalement, *, par, statut, commentaire="", doublon_de=None):
    signalement = _verrouiller(signalement)
    if par.role == Utilisateur.Role.ORGANISATION:
        if signalement.organisation_assignee_id is None or signalement.organisation_assignee_id != par.organisation_id:
            raise ErreurMetier(CodeErreur.ORGANISATION_NON_EN_CHARGE)
        if statut not in STATUTS_ORGANISATION:
            raise ErreurMetier(
                CodeErreur.PERMISSION_REFUSEE,
                "Seule la mairie peut rejeter un signalement ou le classer comme doublon.",
            )
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
        if doublon_de.pk == signalement.pk or doublon_de.statut == Statut.DOUBLON or doublon_de.commune_id != signalement.commune_id:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={"doublon_de": ["Indiquez un autre signalement de la même commune, qui ne soit pas lui-même un doublon."]},
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
    for membre, champ in ((service, "service"), (agent, "agent")):
        if membre is not None and membre.commune_id != signalement.commune_id:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={champ: ["Ce dossier relève d'une autre commune que celle de ce service ou de cet agent."]},
            )
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


def _controler_perimetre(organisation, signalement):
    """L'organisation doit être habilitée et intervenir dans la commune et le secteur du dossier."""
    if not organisation.acces_autorise:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR,
            details={"organisation": ["Cette organisation est suspendue ou son habilitation a expiré."]},
        )
    couvert = (
        organisation.communes.filter(pk=signalement.commune_id).exists()
        and organisation.secteurs.filter(pk=signalement.secteur_id).exists()
    )
    if not couvert:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR,
            details={"organisation": ["Cette organisation n'intervient pas dans la commune ou le secteur de ce dossier."]},
        )


@transaction.atomic
def prendre_en_charge(signalement, *, par):
    """
    Une organisation se confie un signalement de son périmètre qui n'est encore suivi par
    aucune organisation. Sans effet si elle en est déjà chargée.
    """
    signalement = _verrouiller(signalement)
    if signalement.organisation_assignee_id == par.organisation_id:
        return signalement
    if signalement.est_cloture:
        raise ErreurMetier(CodeErreur.SIGNALEMENT_CLOTURE)
    if signalement.organisation_assignee_id is not None:
        raise ErreurMetier(CodeErreur.SIGNALEMENT_DEJA_PRIS_EN_CHARGE)
    organisation = par.organisation
    _controler_perimetre(organisation, signalement)
    signalement.organisation_assignee = organisation
    signalement.save(update_fields=["organisation_assignee", "maj_le"])
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.ASSIGNATION,
        commentaire=f"Dossier pris en charge par l'organisation « {organisation.nom} ».",
        auteur=par,
    )
    return signalement


@transaction.atomic
def affecter_organisation(signalement, *, par, organisation):
    """
    La mairie confie le signalement à une organisation (qui en remplace une éventuelle autre),
    ou le lui retire (`organisation=None`).
    """
    signalement = _verrouiller(signalement)
    if signalement.est_cloture:
        raise ErreurMetier(CodeErreur.SIGNALEMENT_CLOTURE)
    precedente = signalement.organisation_assignee
    if organisation is None:
        if precedente is None:
            return signalement
        commentaire = f"L'organisation « {precedente.nom} » n'est plus chargée de ce dossier."
    else:
        if precedente is not None and precedente.pk == organisation.pk:
            return signalement
        _controler_perimetre(organisation, signalement)
        commentaire = f"Dossier confié à l'organisation « {organisation.nom} »."
    signalement.organisation_assignee = organisation
    signalement.save(update_fields=["organisation_assignee", "maj_le"])
    SuiviSignalement.objects.create(
        signalement=signalement,
        type_evenement=TypeEvenement.ASSIGNATION,
        commentaire=commentaire,
        auteur=par,
    )
    if organisation is not None:
        notifications.notifier_affectation_organisation(signalement)
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
