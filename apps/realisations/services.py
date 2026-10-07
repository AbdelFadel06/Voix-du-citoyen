"""
Logique métier des réalisations (CLAUDE.md § 5 et § 6).

À la publication (création publiée ou passage brouillon → publiée), les citoyens concernés
reçoivent une notification `NOUVELLE_REALISATION`.
"""

from decimal import Decimal

from django.db import transaction

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.references import prochaine_reference
from apps.medias import services as medias
from apps.medias.regles import RATTACHEMENT_REALISATION
from apps.notifications import services as notifications

from .models import Realisation, RealisationMedia

PREFIXE_REFERENCE = "REA"
RELATIONS = ("quartiers", "signalements", "suggestions")


def _coordonnee(valeur):
    return None if valeur is None else Decimal(str(round(valeur, 6)))


def _controler(realisation):
    """Contrôles sur l'état final (création ou modification partielle)."""
    erreurs = {}
    if (realisation.latitude is None) != (realisation.longitude is None):
        erreurs["latitude"] = ["La latitude et la longitude doivent être données ensemble."]
    for debut, fin, libelle in (
        ("date_debut_prevue", "date_fin_prevue", "La fin prévue ne peut pas précéder le début prévu."),
        ("date_debut_reelle", "date_fin_reelle", "La fin réelle ne peut pas précéder le début réel."),
    ):
        date_debut, date_fin = getattr(realisation, debut), getattr(realisation, fin)
        if date_debut and date_fin and date_fin < date_debut:
            erreurs[fin] = [libelle]
    if erreurs:
        raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details=erreurs)
    if realisation.latitude is not None and not realisation.commune.contient(realisation.latitude, realisation.longitude):
        raise ErreurMetier(CodeErreur.COORDONNEES_HORS_COMMUNE)


def _controler_relations(commune, relations):
    """Quartiers, signalements et suggestions liés doivent appartenir à la commune de la réalisation."""
    erreurs = {}
    if any(q.arrondissement.commune_id != commune.pk for q in relations.get("quartiers", [])):
        erreurs["quartiers"] = [f"Tous les quartiers doivent être dans la commune de {commune.nom}."]
    for nom in ("signalements", "suggestions"):
        if any(dossier.commune_id != commune.pk for dossier in relations.get(nom, [])):
            erreurs[nom] = [f"Les {nom} liés doivent être de la commune de {commune.nom}."]
    if erreurs:
        raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details=erreurs)


def _enregistrer_medias(realisation, elements, par):
    """
    Remplace la liste des photos et vidéos par `elements` ([{media, phase, legende, ordre}]).
    Les médias déjà rattachés sont conservés (phase, légende, ordre mis à jour), les nouveaux
    doivent être TEMPORAIRE et envoyés par `par`, ceux qui disparaissent sont supprimés.
    """
    existants = {str(rm.media_id): rm for rm in realisation.medias.select_related("media")}
    ids = [str(element["media"]) for element in elements]
    nouveaux = {str(m.id): m for m in medias.verrouiller_temporaires(par, [i for i in ids if i not in existants])}
    medias.controler_rattachement(
        [existants[i].media if i in existants else nouveaux[i] for i in ids], RATTACHEMENT_REALISATION
    )

    for media_id, lien in existants.items():
        if media_id not in ids:
            medias.supprimer_media(lien.media)  # supprime aussi le lien (CASCADE)
    for position, element in enumerate(elements):
        media_id = str(element["media"])
        valeurs = {
            "phase": element["phase"],
            "legende": element.get("legende", "").strip(),
            "ordre": element.get("ordre", position),
        }
        if media_id in existants:
            RealisationMedia.objects.filter(pk=existants[media_id].pk).update(**valeurs)
        else:
            RealisationMedia.objects.create(realisation=realisation, media=nouveaux[media_id], **valeurs)
    medias.attacher(list(nouveaux.values()))


@transaction.atomic
def creer_realisation(*, par, medias=(), **champs):
    relations = {nom: champs.pop(nom, []) for nom in RELATIONS}
    # Commune de l'agent ; pour un admin de la plateforme, celle des quartiers concernés.
    commune = par.commune or relations["quartiers"][0].arrondissement.commune
    _controler_relations(commune, relations)
    champs["latitude"], champs["longitude"] = _coordonnee(champs.get("latitude")), _coordonnee(champs.get("longitude"))
    realisation = Realisation(cree_par=par, commune=commune, **champs)
    _controler(realisation)
    realisation.reference = prochaine_reference(Realisation, PREFIXE_REFERENCE)
    realisation.save()
    for nom, valeurs in relations.items():
        getattr(realisation, nom).set(valeurs)
    _enregistrer_medias(realisation, list(medias), par)
    if realisation.publie:
        notifications.notifier_nouvelle_realisation(realisation)
    return realisation


@transaction.atomic
def modifier_realisation(realisation, *, par, **changements):
    """Modification partielle : seuls les champs fournis changent (`medias` remplace la liste)."""
    realisation = Realisation.objects.select_for_update().get(pk=realisation.pk)
    etait_publiee = realisation.publie
    elements = changements.pop("medias", None)
    relations = {nom: changements.pop(nom) for nom in RELATIONS if nom in changements}
    _controler_relations(realisation.commune, relations)
    for coordonnee in ("latitude", "longitude"):
        if coordonnee in changements:
            changements[coordonnee] = _coordonnee(changements[coordonnee])
    for champ, valeur in changements.items():
        setattr(realisation, champ, valeur)
    _controler(realisation)
    realisation.save()
    for nom, valeurs in relations.items():
        getattr(realisation, nom).set(valeurs)
    if elements is not None:
        _enregistrer_medias(realisation, elements, par)
    if realisation.publie and not etait_publiee:
        notifications.notifier_nouvelle_realisation(realisation)
    return realisation
