"""
Création des notifications et envoi des pushs (CLAUDE.md § 5).

Les services métier (signalements, suggestions, réalisations) appellent les fonctions
`notifier_…` dans leur transaction. Les notifications sont enregistrées tout de suite ; les
pushs partent après la validation de la transaction (`on_commit`) et un échec d'envoi
n'interrompt jamais l'action de l'utilisateur.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Appareil, Utilisateur
from apps.core.push import EnvoiPushEchoue, JetonPushInvalide, envoyer_push

from .models import Notification

logger = logging.getLogger(__name__)

Type = Notification.Type
Cible = Notification.Cible

LONGUEUR_EXTRAIT = 200


def _extrait(texte):
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_EXTRAIT else texte[: LONGUEUR_EXTRAIT - 1].rstrip() + "…"


def notifier(destinataires, *, type, titre, message, cible_type, cible_id):
    """Crée une notification par destinataire (sans doublon) et programme l'envoi des pushs."""
    destinataires = list({u.pk: u for u in destinataires}.values())
    if not destinataires:
        return []
    notifications = Notification.objects.bulk_create(
        Notification(
            destinataire=destinataire,
            type=type,
            titre=titre,
            message=message,
            cible_type=cible_type,
            cible_id=cible_id,
        )
        for destinataire in destinataires
    )
    ids = [n.pk for n in notifications]
    transaction.on_commit(lambda: envoyer_pushs(ids))
    return notifications


def envoyer_pushs(ids):
    """Envoie chaque notification à tous les appareils actifs de son destinataire."""
    notifications = Notification.objects.filter(pk__in=ids)
    appareils = {}
    for appareil in Appareil.objects.filter(
        actif=True, utilisateur_id__in=notifications.values("destinataire_id")
    ):
        appareils.setdefault(appareil.utilisateur_id, []).append(appareil)

    envoyees, invalides = [], []
    for notification in notifications:
        donnees = {
            "notification_id": notification.pk,
            "type": notification.type,
            "cible_type": notification.cible_type,
            "cible_id": notification.cible_id,
        }
        for appareil in appareils.get(notification.destinataire_id, []):
            try:
                envoyer_push(appareil.token_fcm, notification.titre, notification.message, donnees)
            except JetonPushInvalide:
                invalides.append(appareil.pk)
            except EnvoiPushEchoue:
                logger.warning("Push non envoyé (notification %s, appareil %s).", notification.pk, appareil.pk)
            except Exception:
                logger.exception("Erreur inattendue à l'envoi du push (notification %s).", notification.pk)
            else:
                envoyees.append(notification.pk)
    if envoyees:
        Notification.objects.filter(pk__in=envoyees).update(envoye_push=True)
    if invalides:
        # Application désinstallée ou jeton expiré : on n'y enverra plus rien.
        Appareil.objects.filter(pk__in=invalides).update(actif=False, maj_le=timezone.now())


# ---------------------------------------------------------------------------
# Événements métier
# ---------------------------------------------------------------------------


def notifier_statut_signalement(signalement, commentaire=""):
    Statut = signalement.Statut
    ref = signalement.reference
    messages = {
        Statut.RECU: f"La mairie a bien reçu votre signalement {ref}.",
        Statut.EN_COURS: f"Votre signalement {ref} est en cours de traitement.",
        Statut.RESOLU: f"Bonne nouvelle : votre signalement {ref} est résolu. Merci !",
        Statut.REJETE: f"Votre signalement {ref} n'a pas été retenu : {commentaire}",
        Statut.DOUBLON: f"Votre signalement {ref} rejoint le signalement "
        f"{getattr(signalement.doublon_de, 'reference', '')}, déjà suivi par la mairie.",
    }
    notifier(
        [signalement.auteur],
        type=Type.STATUT_SIGNALEMENT,
        titre="Votre signalement avance",
        message=_extrait(messages.get(signalement.statut, f"Votre signalement {ref} a été mis à jour.")),
        cible_type=Cible.SIGNALEMENT,
        cible_id=signalement.pk,
    )


def notifier_reponse_signalement(signalement, commentaire):
    notifier(
        [signalement.auteur],
        type=Type.REPONSE_SIGNALEMENT,
        titre="Nouveau message de la mairie",
        message=_extrait(f"À propos de votre signalement {signalement.reference} : {commentaire}"),
        cible_type=Cible.SIGNALEMENT,
        cible_id=signalement.pk,
    )


def notifier_reponse_suggestion(suggestion):
    notifier(
        [suggestion.auteur],
        type=Type.REPONSE_SUGGESTION,
        titre="La mairie a répondu à votre suggestion",
        message=_extrait(f"« {suggestion.titre} » : {suggestion.reponse_officielle}"),
        cible_type=Cible.SUGGESTION,
        cible_id=suggestion.pk,
    )


def destinataires_realisation(realisation):
    """
    Citoyens concernés par une réalisation : auteurs des signalements et suggestions liés,
    et habitants (quartier de résidence) des quartiers concernés.
    """
    from django.db.models import Q

    return Utilisateur.objects.filter(
        Q(signalements__in=realisation.signalements.all())
        | Q(suggestions__in=realisation.suggestions.all())
        | Q(quartier_residence__in=realisation.quartiers.all()),
        role=Utilisateur.Role.CITOYEN,
        is_active=True,
    ).distinct()


def notifier_nouvelle_realisation(realisation):
    notifier(
        destinataires_realisation(realisation),
        type=Type.NOUVELLE_REALISATION,
        titre="Nouvelle réalisation de la mairie",
        message=_extrait(realisation.titre),
        cible_type=Cible.REALISATION,
        cible_id=realisation.pk,
    )


# ---------------------------------------------------------------------------
# Appareils et lecture
# ---------------------------------------------------------------------------


def enregistrer_appareil(utilisateur, *, token_fcm, plateforme):
    """
    Enregistre (ou réactive) l'appareil de l'utilisateur. Un jeton déjà connu change de
    compte : c'est le cas d'un téléphone partagé ou réinstallé. Renvoie (appareil, cree).
    """
    appareil, cree = Appareil.objects.update_or_create(
        token_fcm=token_fcm,
        defaults={"utilisateur": utilisateur, "plateforme": plateforme, "actif": True},
    )
    return appareil, cree


def desactiver_appareil(utilisateur, token_fcm):
    """Arrête les notifications vers cet appareil (déconnexion)."""
    Appareil.objects.filter(utilisateur=utilisateur, token_fcm=token_fcm).update(actif=False, maj_le=timezone.now())


def marquer_lue(notification):
    if not notification.lu:
        Notification.objects.filter(pk=notification.pk).update(lu=True, maj_le=timezone.now())
        notification.lu = True
    return notification


def tout_marquer_lu(utilisateur):
    return Notification.objects.filter(destinataire=utilisateur, lu=False).update(lu=True, maj_le=timezone.now())
