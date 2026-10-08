"""
Agrégations des tableaux de bord (aucun modèle propre).

Tous les calculs se font en base (COUNT, AVG, SUM, regroupements) : quelques requêtes par
tableau, quel que soit le volume de dossiers. Les filtres (`date_debut`, `date_fin`,
`secteur`, `quartier`) s'appliquent à la date de création de chaque dossier.

Confidentialité : les organisations (`mairie=False`) ne voient que les signalements de leurs
secteurs d'intervention (`filtres["secteurs_autorises"]`), aucune suggestion et aucune
réalisation en brouillon ; aucun tableau ne contient d'auteur.
"""

from datetime import date, timedelta

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from apps.core.visibilite import limiter_aux_secteurs
from apps.realisations.models import Realisation
from apps.referentiel.models import Secteur
from apps.signalements.models import Signalement
from apps.suggestions.models import Suggestion
from apps.territoire.models import Quartier

StatutSignalement = Signalement.Statut
STATUTS_OUVERTS = [StatutSignalement.SOUMIS, StatutSignalement.RECU, StatutSignalement.EN_COURS]
LIMITE_POINTS_CARTE = 2000
TRONCATURES = {"jour": TruncDay, "semaine": TruncWeek, "mois": TruncMonth}


# ---------------------------------------------------------------------------
# Jeux de données filtrés
# ---------------------------------------------------------------------------


def _filtrer(queryset, filtres, champ_quartier):
    if filtres.get("commune"):
        queryset = queryset.filter(commune=filtres["commune"])
    if filtres.get("date_debut"):
        queryset = queryset.filter(cree_le__date__gte=filtres["date_debut"])
    if filtres.get("date_fin"):
        queryset = queryset.filter(cree_le__date__lte=filtres["date_fin"])
    if filtres.get("secteur"):
        queryset = queryset.filter(secteur=filtres["secteur"])
    if filtres.get("quartier"):
        queryset = queryset.filter(**{champ_quartier: filtres["quartier"]})
    return queryset


def signalements(filtres):
    queryset = _filtrer(Signalement.objects.all(), filtres, "quartier")
    return limiter_aux_secteurs(queryset, filtres.get("secteurs_autorises"))


def suggestions(filtres):
    return _filtrer(Suggestion.objects.all(), filtres, "quartier")


def realisations(filtres, mairie):
    queryset = _filtrer(Realisation.objects.all(), filtres, "quartiers").distinct()
    return queryset if mairie else queryset.filter(publie=True)


def _jours(duree):
    return None if duree is None else round(duree.total_seconds() / 86400, 1)


def _pourcentage(partie, total):
    return round(100 * partie / total, 1) if total else None


# ---------------------------------------------------------------------------
# Tableaux
# ---------------------------------------------------------------------------


def synthese(filtres, mairie):
    dossiers = signalements(filtres)
    par_statut = dict(dossiers.values_list("statut").annotate(n=Count("id")).values_list("statut", "n"))
    total = sum(par_statut.values())
    resolus = par_statut.get(StatutSignalement.RESOLU, 0)
    delai = dossiers.filter(statut=StatutSignalement.RESOLU).aggregate(
        delai=Avg(F("date_resolution") - F("cree_le"))
    )["delai"]


    travaux = realisations(filtres, mairie)
    chiffres = Realisation.objects.filter(pk__in=travaux.values("pk")).aggregate(
        total=Count("id"),
        budget=Sum("budget"),
        avancement=Avg("taux_avancement"),
        publiees=Count("id", filter=Q(publie=True)),
    )
    travaux_par_statut = dict(
        Realisation.objects.filter(pk__in=travaux.values("pk"))
        .values_list("statut")
        .annotate(n=Count("id"))
        .values_list("statut", "n")
    )
    bloc_realisations = {
        "total": chiffres["total"],
        "par_statut": {statut: travaux_par_statut.get(statut, 0) for statut in Realisation.Statut.values},
        "budget_total": int(chiffres["budget"] or 0),
        "taux_avancement_moyen": round(chiffres["avancement"], 1) if chiffres["avancement"] is not None else None,
    }
    if mairie:
        bloc_realisations["brouillons"] = chiffres["total"] - chiffres["publiees"]

    resultat = {
        "signalements": {
            "total": total,
            "par_statut": {statut: par_statut.get(statut, 0) for statut in StatutSignalement.values},
            "ouverts": sum(par_statut.get(s, 0) for s in STATUTS_OUVERTS),
            "resolus": resolus,
            "taux_resolution": _pourcentage(resolus, total),
            "delai_moyen_resolution_jours": _jours(delai),
        },
        "realisations": bloc_realisations,
    }
    if mairie:  # les suggestions restent entre les citoyens et la mairie
        idees = suggestions(filtres).aggregate(
            total=Count("id"), soutiens=Sum("nb_soutiens"), pertinentes=Count("id", filter=Q(est_pertinente=True))
        )
        resultat["suggestions"] = {
            "total": idees["total"], "nb_soutiens": idees["soutiens"] or 0, "pertinentes": idees["pertinentes"]
        }
    return resultat


def _compter_par(queryset, champ):
    return dict(queryset.values_list(champ).annotate(n=Count("id", distinct=True)).values_list(champ, "n"))


def par_secteur(filtres, mairie):
    dossiers = signalements(filtres)
    totaux = _compter_par(dossiers, "secteur")
    resolus = _compter_par(dossiers.filter(statut=StatutSignalement.RESOLU), "secteur")
    ouverts = _compter_par(dossiers.filter(statut__in=STATUTS_OUVERTS), "secteur")
    idees = _compter_par(suggestions(filtres), "secteur") if mairie else {}
    travaux = _compter_par(realisations(filtres, mairie), "secteur")

    secteurs = Secteur.objects.filter(Q(actif=True) | Q(pk__in=set(totaux) | set(idees) | set(travaux)))
    secteurs = limiter_aux_secteurs(secteurs, filtres.get("secteurs_autorises"), champ="pk")
    if filtres.get("secteur"):
        secteurs = secteurs.filter(pk=filtres["secteur"].pk)
    lignes = [
        {
            "secteur": {"id": s.pk, "nom": s.nom, "code": s.code, "couleur": s.couleur},
            **_compteurs(s.pk, totaux, ouverts, resolus, travaux, idees if mairie else None),
        }
        for s in secteurs
    ]
    return sorted(lignes, key=lambda l: (-l["signalements"], -l.get("suggestions", 0), l["secteur"]["nom"]))


def _compteurs(cle, totaux, ouverts, resolus, travaux, idees):
    """Colonnes communes à par_secteur et par_quartier ; `idees=None` : pas de suggestions."""
    ligne = {
        "signalements": totaux.get(cle, 0),
        "signalements_ouverts": ouverts.get(cle, 0),
        "signalements_resolus": resolus.get(cle, 0),
        "taux_resolution": _pourcentage(resolus.get(cle, 0), totaux.get(cle, 0)),
        "realisations": travaux.get(cle, 0),
    }
    if idees is not None:
        ligne["suggestions"] = idees.get(cle, 0)
    return ligne


def par_quartier(filtres, mairie, arrondissement=None):
    dossiers = signalements(filtres)
    totaux = _compter_par(dossiers, "quartier")
    resolus = _compter_par(dossiers.filter(statut=StatutSignalement.RESOLU), "quartier")
    ouverts = _compter_par(dossiers.filter(statut__in=STATUTS_OUVERTS), "quartier")
    idees = _compter_par(suggestions(filtres).exclude(quartier=None), "quartier") if mairie else {}
    travaux = _compter_par(realisations(filtres, mairie), "quartiers")

    actifs = set(totaux) | set(idees) | set(travaux)
    quartiers = Quartier.objects.filter(pk__in=actifs).select_related("arrondissement")
    if arrondissement:
        quartiers = quartiers.filter(arrondissement=arrondissement)
    lignes = [
        {
            "quartier": {"id": q.pk, "nom": q.nom, "arrondissement": q.arrondissement.nom},
            **_compteurs(q.pk, totaux, ouverts, resolus, travaux, idees if mairie else None),
        }
        for q in quartiers
    ]
    return sorted(lignes, key=lambda l: (-l["signalements"], -l.get("suggestions", 0), l["quartier"]["nom"]))


def debut_de_periode(jour, periode):
    if periode == "mois":
        return jour.replace(day=1)
    if periode == "semaine":
        return jour - timedelta(days=jour.weekday())
    return jour


def _periode_suivante(jour, periode):
    if periode == "mois":
        return (jour.replace(day=28) + timedelta(days=4)).replace(day=1)
    return jour + timedelta(days=7 if periode == "semaine" else 1)


def bornes_evolution(filtres, periode):
    """Période par défaut : les 12 derniers mois, 12 dernières semaines ou 30 derniers jours."""
    fin = filtres.get("date_fin") or timezone.localdate()
    debut = filtres.get("date_debut")
    if debut is None:
        if periode == "mois":
            debut = date(fin.year - 1, fin.month, 1) + timedelta(days=32)
            debut = debut.replace(day=1)
        else:
            debut = fin - timedelta(weeks=11) if periode == "semaine" else fin - timedelta(days=29)
    return debut_de_periode(debut, periode), fin


def nombre_de_periodes(debut, fin, periode):
    nombre, jour = 0, debut_de_periode(debut, periode)
    while jour <= fin:
        nombre += 1
        jour = _periode_suivante(jour, periode)
    return nombre


def evolution(filtres, periode, mairie=True):
    debut, fin = bornes_evolution(filtres, periode)
    filtres = {**filtres, "date_debut": debut, "date_fin": fin}
    tronquer = TRONCATURES[periode]

    def par_periode(queryset, champ):
        lignes = queryset.annotate(p=tronquer(champ)).values("p").annotate(n=Count("id")).values_list("p", "n")
        return {timezone.localtime(p).date() if hasattr(p, "hour") else p: n for p, n in lignes}

    crees = par_periode(signalements(filtres), "cree_le")
    resolus = par_periode(
        signalements({k: v for k, v in filtres.items() if k not in ("date_debut", "date_fin")})
        .filter(statut=StatutSignalement.RESOLU, date_resolution__date__gte=debut, date_resolution__date__lte=fin),
        "date_resolution",
    )
    idees = par_periode(suggestions(filtres), "cree_le") if mairie else None

    points, jour = [], debut
    while jour <= fin:
        point = {
            "periode": jour,
            "signalements_crees": crees.get(jour, 0),
            "signalements_resolus": resolus.get(jour, 0),
        }
        if idees is not None:
            point["suggestions_creees"] = idees.get(jour, 0)
        points.append(point)
        jour = _periode_suivante(jour, periode)
    return {"periode": periode, "date_debut": debut, "date_fin": fin, "points": points}


def carte(filtres, mairie, statut=None):
    dossiers = signalements(filtres)
    if statut:
        dossiers = dossiers.filter(statut=statut)

    localises = dossiers.filter(latitude__isnull=False).select_related("secteur").order_by("-cree_le")
    total_localises = localises.count()
    points = [
        {
            "id": s.pk,
            "reference": s.reference,
            "titre": s.titre,
            "statut": s.statut,
            "secteur": {"id": s.secteur_id, "code": s.secteur.code, "couleur": s.secteur.couleur},
            "latitude": s.latitude,
            "longitude": s.longitude,
            "cree_le": s.cree_le,
        }
        for s in localises[:LIMITE_POINTS_CARTE]
    ]

    # Tous les signalements (GPS ou manuels) regroupés au centre de leur quartier.
    compte = _compter_par(dossiers, "quartier")
    quartiers = [
        {
            "quartier": {"id": q.pk, "nom": q.nom, "arrondissement": q.arrondissement.nom},
            "latitude": q.latitude_centre,
            "longitude": q.longitude_centre,
            "signalements": compte[q.pk],
        }
        for q in Quartier.objects.filter(pk__in=compte, latitude_centre__isnull=False).select_related("arrondissement")
    ]

    travaux = [
        {"id": r.pk, "reference": r.reference, "titre": r.titre, "statut": r.statut, "latitude": r.latitude, "longitude": r.longitude}
        for r in realisations(filtres, mairie).filter(latitude__isnull=False).order_by("-cree_le")[:LIMITE_POINTS_CARTE]
    ]
    return {
        "signalements": points,
        "signalements_tronques": total_localises > LIMITE_POINTS_CARTE,
        "quartiers": sorted(quartiers, key=lambda q: -q["signalements"]),
        "realisations": travaux,
    }
