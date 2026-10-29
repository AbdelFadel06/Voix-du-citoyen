from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import commune_imposee
from apps.core.espaces import EspaceMairie
from apps.core.permissions import EstMairieOuOrganisation, est_personnel_mairie
from apps.core.visibilite import communes_autorisees, secteurs_autorises
from apps.core.reponses import reponse_succes
from apps.core.schema import EXEMPLES_AUTH_REQUISE, TAG_TABLEAUX_DE_BORD, enveloppe, erreurs, exemple_erreur, exemple_succes

from . import exemples, services
from .serializers import (
    CarteSerializer,
    EvolutionSerializer,
    FiltresCarteMairieSerializer,
    FiltresCarteSerializer,
    FiltresEvolutionMairieSerializer,
    FiltresEvolutionSerializer,
    FiltresQuartierSerializer,
    FiltresSerializer,
    FiltresSyntheseMairieSerializer,
    LigneQuartierSerializer,
    LigneSecteurSerializer,
    SyntheseCompleteSerializer,
    SyntheseSerializer,
)

ACCES = """
**Commune** : les organisations et l'admin de la plateforme voient toutes les communes ensemble,
ou une seule avec `?commune=<id>`. La mairie d'une commune utilise l'espace mairie
(`/api/v1/mairie/dashboard/…`) : ici, elle reçoit `ESPACE_MAIRIE_REQUIS`.

**Filtres communs** : `date_debut`, `date_fin` (date de création des dossiers), `secteur`, `quartier`.

**Connecté** : organisations habilitées et admin de la plateforme. Les organisations ne voient
que les **signalements de leurs communes et secteurs d'intervention**, **aucune suggestion** (les champs
`suggestions…` sont absents de leurs réponses) et pas les réalisations en brouillon.
"""
EXEMPLES_ERREURS = [
    exemple_erreur(
        CodeErreur.VALIDATION_ERREUR,
        details={"date_fin": ["La date de fin doit suivre la date de début."]},
        nom="Dates incohérentes",
    ),
    exemple_erreur(
        CodeErreur.PERMISSION_REFUSEE,
        "Accès réservé à la mairie et aux organisations habilitées.",
        nom="Compte citoyen",
    ),
    *EXEMPLES_AUTH_REQUISE,
]


class VueTableau(APIView):
    permission_classes = [IsAuthenticated, EstMairieOuOrganisation]
    filtres_class = FiltresSerializer

    def filtres(self, request):
        entree = self.filtres_class(data=request.query_params)
        entree.is_valid(raise_exception=True)
        filtres = dict(entree.validated_data)
        imposee = commune_imposee(request.user)
        if imposee is not None:
            filtres["commune"] = imposee  # la mairie d'une commune ne voit que la sienne
        # Organisations : seulement les signalements de leurs communes et secteurs d'intervention.
        filtres["secteurs_autorises"] = secteurs_autorises(request.user)
        filtres["communes_autorisees"] = communes_autorisees(request.user)
        return filtres

    @property
    def mairie(self):
        return est_personnel_mairie(self.request.user)


class SyntheseView(VueTableau):
    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Chiffres clés",
        description=f"""
Vue d'ensemble : signalements (total, répartition par statut, dossiers ouverts, taux de
résolution, délai moyen de résolution en jours), suggestions (nombre, soutiens) et
réalisations (répartition par statut, budget total en FCFA, avancement moyen).

Pour la mairie seulement : `suggestions.pertinentes` et `realisations.brouillons`.
{ACCES}""",
        parameters=[FiltresSerializer],
        responses={200: enveloppe(SyntheseSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_succes("Vue par la mairie", exemples.SYNTHESE_MAIRIE),
            exemple_succes("Vue par une organisation", exemples.SYNTHESE_ORGANISATION),
            *EXEMPLES_ERREURS,
        ],
    )
    def get(self, request):
        donnees = services.synthese(self.filtres(request), self.mairie)
        return reponse_succes(SyntheseSerializer(donnees).data)


class ParSecteurView(VueTableau):
    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Chiffres par secteur",
        description=f"""
Une ligne par secteur actif (et par secteur désactivé qui a encore des dossiers), triée du
plus grand nombre de signalements au plus petit : signalements (total, ouverts, résolus, taux
de résolution), suggestions et réalisations.
{ACCES}""",
        parameters=[FiltresSerializer],
        responses={200: enveloppe(LigneSecteurSerializer, many=True), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Secteurs", exemples.PAR_SECTEUR), *EXEMPLES_ERREURS],
    )
    def get(self, request):
        lignes = services.par_secteur(self.filtres(request), self.mairie)
        return reponse_succes(LigneSecteurSerializer(lignes, many=True).data)


class ParQuartierView(VueTableau):
    filtres_class = FiltresQuartierSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Chiffres par quartier",
        description=f"""
Une ligne par quartier ayant au moins un dossier, triée du plus grand nombre de signalements
au plus petit : signalements (total, ouverts, résolus, taux de résolution), suggestions
(hors suggestions pour toute la commune) et réalisations.

Filtre supplémentaire : `arrondissement`.
{ACCES}""",
        parameters=[FiltresQuartierSerializer],
        responses={200: enveloppe(LigneQuartierSerializer, many=True), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Quartiers", exemples.PAR_QUARTIER), *EXEMPLES_ERREURS],
    )
    def get(self, request):
        filtres = self.filtres(request)
        arrondissement = filtres.pop("arrondissement", None)
        lignes = services.par_quartier(filtres, self.mairie, arrondissement)
        return reponse_succes(LigneQuartierSerializer(lignes, many=True).data)


class EvolutionView(VueTableau):
    filtres_class = FiltresEvolutionSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Évolution dans le temps",
        description=f"""
Série chronologique, **sans trou** (0 pour une période sans dossier), pour tracer des courbes :
signalements envoyés, signalements résolus (à leur date de résolution) et suggestions envoyées.

- `periode` : `jour`, `semaine` (du lundi) ou `mois` (défaut).
- Sans dates : les 30 derniers jours, les 12 dernières semaines ou les 12 derniers mois.
- 400 points au maximum.
{ACCES}""",
        parameters=[FiltresEvolutionSerializer],
        responses={200: enveloppe(EvolutionSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_succes("Par mois", exemples.EVOLUTION),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"periode": ["Trop de points (400 au maximum) : choisissez une période plus longue ou réduisez les dates."]},
                nom="Trop de points",
            ),
            *EXEMPLES_ERREURS,
        ],
    )
    def get(self, request):
        filtres = self.filtres(request)
        periode = filtres.pop("periode")
        return reponse_succes(EvolutionSerializer(services.evolution(filtres, periode, self.mairie)).data)


class CarteView(VueTableau):
    filtres_class = FiltresCarteSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Données de la carte",
        description=f"""
Éléments à placer sur la carte de la commune :
- `signalements` : signalements localisés en **GPS** (2 000 au maximum, les plus récents ;
  `signalements_tronques` indique s'il faut affiner les filtres) ;
- `quartiers` : **tous** les signalements (GPS et manuels) comptés par quartier, au centre
  du quartier (pour une carte de chaleur) ;
- `realisations` : réalisations localisées.

Filtre supplémentaire : `statut` (signalements).
{ACCES}""",
        parameters=[FiltresCarteSerializer],
        responses={200: enveloppe(CarteSerializer), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Carte", exemples.CARTE), *EXEMPLES_ERREURS],
    )
    def get(self, request):
        filtres = self.filtres(request)
        statut = filtres.pop("statut", None)
        return reponse_succes(CarteSerializer(services.carte(filtres, self.mairie, statut)).data)


# ---------------------------------------------------------------------------
# Espace mairie (/api/v1/mairie/dashboard/…) : clé d'API IBDC seulement, la commune vient de la clé.
# ---------------------------------------------------------------------------

ACCES_MAIRIE = """
**Commune** : toujours celle de la clé d'API ; aucun paramètre `commune`.

**Filtres** : `date_debut`, `date_fin` (date de création des dossiers), `secteur`, `quartier`.

**Connecté** : clé d'API d'une institution (plateforme IBDC des mairies) uniquement. Tout
jeton de connexion, même d'un agent ou admin mairie, reçoit `PERMISSION_REFUSEE`.
"""
EXEMPLES_ERREURS_MAIRIE = [
    EXEMPLES_ERREURS[0],
    exemple_erreur(
        CodeErreur.PERMISSION_REFUSEE,
        "Espace réservé à la plateforme des mairies (IBDC), avec la clé d'API de la mairie.",
        nom="Sans clé IBDC",
    ),
    *EXEMPLES_AUTH_REQUISE,
]


class VueTableauMairie(VueTableau):
    permission_classes = [EspaceMairie]


class SyntheseCompleteView(VueTableauMairie):
    filtres_class = FiltresSyntheseMairieSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Récapitulatif complet de la mairie",
        description=f"""
Tout le récapitulatif de la commune en un seul appel :

1. `globales` : chiffres clés — signalements (total, par statut, ouverts, taux et délai moyen
   de résolution), suggestions (nombre, soutiens, pertinentes) et réalisations (par statut,
   brouillons, budget total en FCFA, avancement moyen) ;
2. `par_secteur` : une ligne par secteur (signalements, ouverts, résolus, taux de résolution,
   suggestions, réalisations), du plus grand nombre de signalements au plus petit ;
3. `par_quartier` : une ligne par quartier ayant au moins un dossier, mêmes colonnes.

Les filtres s'appliquent aux trois blocs ; `arrondissement` ne limite que `par_quartier`.
L'évolution dans le temps et la carte restent à part (`/mairie/dashboard/evolution/`,
`/mairie/dashboard/carte/`), car plus lourdes.
{ACCES_MAIRIE}""",
        parameters=[FiltresSyntheseMairieSerializer],
        responses={200: enveloppe(SyntheseCompleteSerializer), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Récapitulatif", exemples.SYNTHESE_COMPLETE), *EXEMPLES_ERREURS_MAIRIE],
    )
    def get(self, request):
        filtres = self.filtres(request)
        arrondissement = filtres.pop("arrondissement", None)
        donnees = {
            "globales": services.synthese(filtres, True),
            "par_secteur": services.par_secteur(filtres, True),
            "par_quartier": services.par_quartier(filtres, True, arrondissement),
        }
        return reponse_succes(SyntheseCompleteSerializer(donnees).data)


class EvolutionMairieView(VueTableauMairie, EvolutionView):
    filtres_class = FiltresEvolutionMairieSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Évolution dans le temps (mairie)",
        description=f"""
Série chronologique de la commune, **sans trou** (0 pour une période sans dossier) :
signalements envoyés, signalements résolus (à leur date de résolution) et suggestions envoyées.

- `periode` : `jour`, `semaine` (du lundi) ou `mois` (défaut).
- Sans dates : les 30 derniers jours, les 12 dernières semaines ou les 12 derniers mois.
- 400 points au maximum.
{ACCES_MAIRIE}""",
        parameters=[FiltresEvolutionMairieSerializer],
        responses={200: enveloppe(EvolutionSerializer), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Par mois", exemples.EVOLUTION), *EXEMPLES_ERREURS_MAIRIE],
    )
    def get(self, request):
        return super().get(request)


class CarteMairieView(VueTableauMairie, CarteView):
    filtres_class = FiltresCarteMairieSerializer

    @extend_schema(
        tags=[TAG_TABLEAUX_DE_BORD],
        summary="Données de la carte (mairie)",
        description=f"""
Éléments à placer sur la carte de la commune :
- `signalements` : signalements localisés en **GPS** (2 000 au maximum, les plus récents ;
  `signalements_tronques` indique s'il faut affiner les filtres) ;
- `quartiers` : **tous** les signalements (GPS et manuels) comptés par quartier, au centre
  du quartier (pour une carte de chaleur) ;
- `realisations` : réalisations localisées.

Filtre supplémentaire : `statut` (signalements).
{ACCES_MAIRIE}""",
        parameters=[FiltresCarteMairieSerializer],
        responses={200: enveloppe(CarteSerializer), **erreurs(400, 401, 403)},
        examples=[exemple_succes("Carte", exemples.CARTE), *EXEMPLES_ERREURS_MAIRIE],
    )
    def get(self, request):
        return super().get(request)
