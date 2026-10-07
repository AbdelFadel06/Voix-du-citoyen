from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.communes import commune_imposee
from apps.core.permissions import EstMairieOuOrganisation, est_personnel_mairie
from apps.core.reponses import reponse_succes
from apps.core.schema import EXEMPLES_AUTH_REQUISE, TAG_TABLEAUX_DE_BORD, enveloppe, erreurs, exemple_erreur, exemple_succes

from . import exemples, services
from .serializers import (
    CarteSerializer,
    EvolutionSerializer,
    FiltresCarteSerializer,
    FiltresEvolutionSerializer,
    FiltresQuartierSerializer,
    FiltresSerializer,
    LigneQuartierSerializer,
    LigneSecteurSerializer,
    SyntheseSerializer,
)

ACCES = """
**Commune** : la mairie d'une commune ne voit que la sienne ; les organisations et les admins
de la plateforme voient toutes les communes ensemble, ou une seule avec `?commune=<id>`.

**Filtres communs** : `date_debut`, `date_fin` (date de création des dossiers), `secteur`, `quartier`.

**Connecté** : agents, admins mairie et organisations habilitées. Les organisations ne voient
ni les réalisations en brouillon ni les suggestions cochées « pertinentes ».
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
        return reponse_succes(EvolutionSerializer(services.evolution(filtres, periode)).data)


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
