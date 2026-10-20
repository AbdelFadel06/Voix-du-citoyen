"""
Statistiques des organisations : les signalements de leur périmètre d'intervention
(communes × secteurs) et la façon dont la mairie les a traités.

Une seule requête groupée par (commune, secteur) pour toute une page d'organisations ;
chaque organisation additionne ensuite les cases de son périmètre. Le nombre de requêtes ne
dépend donc ni du nombre d'organisations ni du volume de signalements.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, F, Q, Sum

from apps.realisations.models import Realisation
from apps.signalements.models import Signalement

Statut = Signalement.Statut
COMPTEURS = ("total", "en_attente", "en_cours", "resolus", "rejetes")


def _vide():
    return {**dict.fromkeys(COMPTEURS, 0), "duree_resolution": timedelta(0)}


def _cases(organisations, *, commune=None, date_debut=None, date_fin=None):
    """Compteurs par (commune, secteur) sur l'union des périmètres des organisations."""
    communes = {c.pk for o in organisations for c in o.communes.all()}
    secteurs = {s.pk for o in organisations for s in o.secteurs.all()}
    if not communes or not secteurs:
        return {}
    signalements = Signalement.objects.filter(commune_id__in=communes, secteur_id__in=secteurs)
    if commune is not None:
        signalements = signalements.filter(commune_id=commune)
    if date_debut:
        signalements = signalements.filter(cree_le__date__gte=date_debut)
    if date_fin:
        signalements = signalements.filter(cree_le__date__lte=date_fin)
    lignes = (
        signalements.order_by()
        .values("commune_id", "secteur_id")
        .annotate(
            total=Count("id"),
            en_attente=Count("id", filter=Q(statut=Statut.SOUMIS)),
            en_cours=Count("id", filter=Q(statut__in=[Statut.RECU, Statut.EN_COURS])),
            resolus=Count("id", filter=Q(statut=Statut.RESOLU)),
            rejetes=Count("id", filter=Q(statut=Statut.REJETE)),
            duree_resolution=Sum(F("date_resolution") - F("cree_le"), filter=Q(statut=Statut.RESOLU)),
        )
    )
    return {(ligne["commune_id"], ligne["secteur_id"]): ligne for ligne in lignes}


def _ajouter(cumul, ligne):
    for cle in COMPTEURS:
        cumul[cle] += ligne[cle]
    cumul["duree_resolution"] += ligne["duree_resolution"] or timedelta(0)


def _finaliser(cumul):
    resolus, total = cumul["resolus"], cumul["total"]
    return {
        "signalements": total,
        "en_attente": cumul["en_attente"],
        "en_cours": cumul["en_cours"],
        "ouverts": cumul["en_attente"] + cumul["en_cours"],
        "resolus": resolus,
        "rejetes": cumul["rejetes"],
        "taux_resolution": round(100 * resolus / total, 1) if total else None,
        "delai_moyen_resolution_jours": (
            round(cumul["duree_resolution"].total_seconds() / 86400 / resolus, 1) if resolus else None
        ),
    }


def _prises_en_charge(organisations, *, commune=None, date_debut=None, date_fin=None):
    """Dossiers dont chaque organisation est en charge, et combien sont résolus."""
    signalements = Signalement.objects.filter(organisation_assignee__in=[o.pk for o in organisations])
    if commune is not None:
        signalements = signalements.filter(commune_id=commune)
    if date_debut:
        signalements = signalements.filter(cree_le__date__gte=date_debut)
    if date_fin:
        signalements = signalements.filter(cree_le__date__lte=date_fin)
    lignes = (
        signalements.order_by()
        .values("organisation_assignee_id")
        .annotate(total=Count("id"), resolus=Count("id", filter=Q(statut=Statut.RESOLU)))
    )
    return {ligne["organisation_assignee_id"]: ligne for ligne in lignes}


def _realisations_publiees(organisations, *, commune=None, date_debut=None, date_fin=None):
    """Réalisations publiées par chaque organisation."""
    realisations = Realisation.objects.filter(organisation__in=[o.pk for o in organisations], publie=True)
    if commune is not None:
        realisations = realisations.filter(commune_id=commune)
    if date_debut:
        realisations = realisations.filter(cree_le__date__gte=date_debut)
    if date_fin:
        realisations = realisations.filter(cree_le__date__lte=date_fin)
    return dict(realisations.order_by().values_list("organisation_id").annotate(n=Count("id")))


def statistiques(organisations, *, commune=None, date_debut=None, date_fin=None, details=False):
    """
    {id organisation: statistiques} pour `organisations` (communes et secteurs préchargés).
    `commune` restreint le calcul à une commune (mairie d'une commune, ou filtre demandé).
    Avec `details`, ajoute la répartition par commune et par secteur.
    """
    cases = _cases(organisations, commune=commune, date_debut=date_debut, date_fin=date_fin)
    prises = _prises_en_charge(organisations, commune=commune, date_debut=date_debut, date_fin=date_fin)
    publiees = _realisations_publiees(organisations, commune=commune, date_debut=date_debut, date_fin=date_fin)
    resultat = {}
    for organisation in organisations:
        communes = {c.pk: c for c in organisation.communes.all() if commune is None or c.pk == commune}
        secteurs = {s.pk: s for s in organisation.secteurs.all()}
        cumul, par_commune, par_secteur = _vide(), defaultdict(_vide), defaultdict(_vide)
        for id_commune in communes:
            for id_secteur in secteurs:
                ligne = cases.get((id_commune, id_secteur))
                if ligne:
                    _ajouter(cumul, ligne)
                    _ajouter(par_commune[id_commune], ligne)
                    _ajouter(par_secteur[id_secteur], ligne)
        prise = prises.get(organisation.pk, {"total": 0, "resolus": 0})
        stats = {
            "globales": {
                **_finaliser(cumul),
                "pris_en_charge": prise["total"],
                "resolus_pris_en_charge": prise["resolus"],
                "realisations_publiees": publiees.get(organisation.pk, 0),
            }
        }
        if details:
            stats["par_commune"] = [
                {"commune": {"id": c.pk, "nom": c.nom}, **_finaliser(par_commune[c.pk])} for c in communes.values()
            ]
            stats["par_secteur"] = [
                {"secteur": {"id": s.pk, "nom": s.nom, "code": s.code}, **_finaliser(par_secteur[s.pk])}
                for s in secteurs.values()
            ]
        resultat[organisation.pk] = stats
    return resultat
