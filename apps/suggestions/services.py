"""
Logique métier des suggestions (CLAUDE.md § 5 et § 6).

Pas de statut : la mairie coche les suggestions pertinentes (`marquer_pertinente`).
L'auteur est notifié à chaque réponse officielle.
"""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.references import prochaine_reference
from apps.medias import services as medias
from apps.medias.regles import RATTACHEMENT_SUGGESTION
from apps.notifications import services as notifications

from .models import Soutien, Suggestion, SuiviSuggestion

TypeEvenement = SuiviSuggestion.TypeEvenement

PREFIXE_REFERENCE = "SUG"


@transaction.atomic
def creer_suggestion(*, auteur, titre, description, secteur, quartier=None, medias_ids=()):
    photos = medias.verifier_medias(auteur, medias_ids, RATTACHEMENT_SUGGESTION)
    suggestion = Suggestion.objects.create(
        reference=prochaine_reference(Suggestion, PREFIXE_REFERENCE),
        titre=titre.strip(),
        description=description.strip(),
        secteur=secteur,
        quartier=quartier,
        auteur=auteur,
    )
    suggestion.medias.set(photos)
    medias.attacher(photos)
    return suggestion


def _verrouiller(suggestion):
    return Suggestion.objects.select_for_update().get(pk=suggestion.pk)


# ---------------------------------------------------------------------------
# Soutiens
# ---------------------------------------------------------------------------


def _controler_soutien(suggestion, citoyen):
    if suggestion.auteur_id == citoyen.pk:
        raise ErreurMetier(CodeErreur.SOUTIEN_PROPRE_SUGGESTION)


@transaction.atomic
def soutenir(suggestion, citoyen):
    """
    Ajoute le soutien du citoyen. Sans effet s'il soutient déjà : l'application peut renvoyer
    la requête sans risque (connexion coupée…). Renvoie la suggestion à jour.
    """
    suggestion = _verrouiller(suggestion)
    _controler_soutien(suggestion, citoyen)
    _, cree = Soutien.objects.get_or_create(suggestion=suggestion, citoyen=citoyen)
    if cree:
        Suggestion.objects.filter(pk=suggestion.pk).update(nb_soutiens=F("nb_soutiens") + 1)
        suggestion.refresh_from_db(fields=["nb_soutiens"])
    return suggestion


@transaction.atomic
def retirer_soutien(suggestion, citoyen):
    """Retire le soutien du citoyen. Sans effet s'il ne soutenait pas. Renvoie la suggestion à jour."""
    suggestion = _verrouiller(suggestion)
    _controler_soutien(suggestion, citoyen)
    supprimes, _ = Soutien.objects.filter(suggestion=suggestion, citoyen=citoyen).delete()
    if supprimes:
        Suggestion.objects.filter(pk=suggestion.pk).update(nb_soutiens=F("nb_soutiens") - 1)
        suggestion.refresh_from_db(fields=["nb_soutiens"])
    return suggestion


# ---------------------------------------------------------------------------
# Examen par la mairie
# ---------------------------------------------------------------------------


def marquer_pertinente(suggestion, pertinente=True):
    """Coche (ou décoche) la suggestion comme pertinente. Sans effet si elle l'est déjà."""
    Suggestion.objects.filter(pk=suggestion.pk).exclude(est_pertinente=pertinente).update(
        est_pertinente=pertinente, maj_le=timezone.now()
    )
    suggestion.est_pertinente = pertinente
    return suggestion


@transaction.atomic
def repondre(suggestion, *, par, commentaire, interne=False):
    """
    Réponse officielle (enregistrée dans `reponse_officielle`, visible par tous) ou note
    interne (historique de la mairie seulement). Une nouvelle réponse officielle remplace
    la précédente ; toutes restent dans l'historique.
    """
    suggestion = _verrouiller(suggestion)
    commentaire = commentaire.strip()
    if interne:
        suggestion.save(update_fields=["maj_le"])
    else:
        suggestion.reponse_officielle = commentaire
        suggestion.repondu_par = par
        suggestion.repondu_le = timezone.now()
        suggestion.save(update_fields=["reponse_officielle", "repondu_par", "repondu_le", "maj_le"])
    SuiviSuggestion.objects.create(
        suggestion=suggestion,
        type_evenement=TypeEvenement.NOTE_INTERNE if interne else TypeEvenement.REPONSE,
        commentaire=commentaire,
        visible_citoyen=not interne,
        auteur=par,
    )
    if not interne:
        notifications.notifier_reponse_suggestion(suggestion)
    return suggestion
