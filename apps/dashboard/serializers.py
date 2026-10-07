"""Paramètres et formats de réponse des tableaux de bord (documentation incluse)."""

from rest_framework import serializers

from apps.referentiel.models import Secteur
from apps.signalements.models import Signalement
from apps.territoire.models import Arrondissement, Quartier

PERIODES = [("jour", "Jour"), ("semaine", "Semaine"), ("mois", "Mois")]
MAX_POINTS_EVOLUTION = 400


# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------


class FiltresSerializer(serializers.Serializer):
    date_debut = serializers.DateField(required=False, help_text="Dossiers créés à partir de ce jour (AAAA-MM-JJ).")
    date_fin = serializers.DateField(required=False, help_text="Dossiers créés jusqu'à ce jour inclus (AAAA-MM-JJ).")
    secteur = serializers.PrimaryKeyRelatedField(
        queryset=Secteur.objects.all(),
        required=False,
        error_messages={"does_not_exist": "Ce secteur n'existe pas."},
        help_text="Limiter à un secteur (identifiant).",
    )
    quartier = serializers.PrimaryKeyRelatedField(
        queryset=Quartier.objects.all(),
        required=False,
        error_messages={"does_not_exist": "Ce quartier n'existe pas."},
        help_text="Limiter à un quartier (identifiant).",
    )

    def validate(self, attrs):
        if attrs.get("date_debut") and attrs.get("date_fin") and attrs["date_fin"] < attrs["date_debut"]:
            raise serializers.ValidationError({"date_fin": ["La date de fin doit suivre la date de début."]})
        return attrs


class FiltresQuartierSerializer(FiltresSerializer):
    arrondissement = serializers.PrimaryKeyRelatedField(
        queryset=Arrondissement.objects.all(),
        required=False,
        error_messages={"does_not_exist": "Cet arrondissement n'existe pas."},
        help_text="Limiter aux quartiers d'un arrondissement (identifiant).",
    )


class FiltresEvolutionSerializer(FiltresSerializer):
    periode = serializers.ChoiceField(
        choices=PERIODES,
        default="mois",
        help_text="Regroupement : `jour`, `semaine` (du lundi) ou `mois` (défaut). Sans dates, la "
        "période couvre les 30 derniers jours, les 12 dernières semaines ou les 12 derniers mois.",
    )

    def validate(self, attrs):
        from .services import bornes_evolution, nombre_de_periodes

        attrs = super().validate(attrs)
        debut, fin = bornes_evolution(attrs, attrs["periode"])
        if nombre_de_periodes(debut, fin, attrs["periode"]) > MAX_POINTS_EVOLUTION:
            raise serializers.ValidationError(
                {"periode": [f"Trop de points ({MAX_POINTS_EVOLUTION} au maximum) : choisissez une période plus longue ou réduisez les dates."]}
            )
        return attrs


class FiltresCarteSerializer(FiltresSerializer):
    statut = serializers.ChoiceField(
        choices=Signalement.Statut.choices, required=False, help_text="Limiter aux signalements à ce statut."
    )


# ---------------------------------------------------------------------------
# Réponses
# ---------------------------------------------------------------------------


def _entier(texte):
    return serializers.IntegerField(help_text=texte)


def _pourcentage(texte):
    return serializers.FloatField(allow_null=True, help_text=texte + " (en %, `null` sans dossier).")


class StatutsSignalementSerializer(serializers.Serializer):
    SOUMIS = _entier("Signalements envoyés, pas encore pris en compte.")
    RECU = _entier("Signalements reçus par la mairie.")
    EN_COURS = _entier("Signalements en cours de traitement.")
    RESOLU = _entier("Signalements résolus.")
    REJETE = _entier("Signalements rejetés.")
    DOUBLON = _entier("Signalements classés en doublon.")


class SyntheseSignalementsSerializer(serializers.Serializer):
    total = _entier("Nombre de signalements.")
    par_statut = StatutsSignalementSerializer(help_text="Répartition par statut.")
    ouverts = _entier("Signalements non clos (soumis, reçus ou en cours).")
    resolus = _entier("Signalements résolus.")
    taux_resolution = _pourcentage("Part des signalements résolus")
    delai_moyen_resolution_jours = serializers.FloatField(
        allow_null=True, help_text="Délai moyen entre l'envoi et la résolution, en jours (`null` sans résolution)."
    )


class SyntheseSuggestionsSerializer(serializers.Serializer):
    total = _entier("Nombre de suggestions.")
    nb_soutiens = _entier("Total des soutiens reçus.")
    pertinentes = serializers.IntegerField(
        required=False, help_text="Suggestions cochées « pertinentes » (agents et admins uniquement)."
    )


class StatutsRealisationSerializer(serializers.Serializer):
    PLANIFIEE = _entier("Réalisations planifiées.")
    EN_COURS = _entier("Réalisations en cours.")
    TERMINEE = _entier("Réalisations terminées.")
    SUSPENDUE = _entier("Réalisations suspendues.")


class SyntheseRealisationsSerializer(serializers.Serializer):
    total = _entier("Nombre de réalisations (publiées seulement pour les organisations).")
    par_statut = StatutsRealisationSerializer(help_text="Répartition par statut.")
    budget_total = _entier("Somme des budgets renseignés, en FCFA.")
    taux_avancement_moyen = serializers.FloatField(
        allow_null=True, help_text="Avancement moyen en % (`null` sans réalisation)."
    )
    brouillons = serializers.IntegerField(
        required=False, help_text="Réalisations non publiées (agents et admins uniquement)."
    )


class SyntheseSerializer(serializers.Serializer):
    signalements = SyntheseSignalementsSerializer(help_text="Chiffres des signalements.")
    suggestions = SyntheseSuggestionsSerializer(help_text="Chiffres des suggestions.")
    realisations = SyntheseRealisationsSerializer(help_text="Chiffres des réalisations.")


class SecteurTableauSerializer(serializers.Serializer):
    id = _entier("Identifiant du secteur.")
    nom = serializers.CharField(help_text="Nom du secteur.")
    code = serializers.CharField(help_text="Code du secteur.")
    couleur = serializers.CharField(help_text="Couleur d'affichage `#RRGGBB` (peut être vide).")


class QuartierTableauSerializer(serializers.Serializer):
    id = _entier("Identifiant du quartier.")
    nom = serializers.CharField(help_text="Nom du quartier.")
    arrondissement = serializers.CharField(help_text="Nom de l'arrondissement.")


class _CompteursSerializer(serializers.Serializer):
    signalements = _entier("Signalements.")
    signalements_ouverts = _entier("Signalements non clos.")
    signalements_resolus = _entier("Signalements résolus.")
    taux_resolution = _pourcentage("Part des signalements résolus")
    suggestions = _entier("Suggestions.")
    realisations = _entier("Réalisations.")


class LigneSecteurSerializer(_CompteursSerializer):
    secteur = SecteurTableauSerializer(help_text="Secteur.")


class LigneQuartierSerializer(_CompteursSerializer):
    quartier = QuartierTableauSerializer(help_text="Quartier.")


class PointEvolutionSerializer(serializers.Serializer):
    periode = serializers.DateField(help_text="Premier jour de la période (jour, lundi ou 1er du mois).")
    signalements_crees = _entier("Signalements envoyés pendant la période.")
    signalements_resolus = _entier("Signalements résolus pendant la période.")
    suggestions_creees = _entier("Suggestions envoyées pendant la période.")


class EvolutionSerializer(serializers.Serializer):
    periode = serializers.ChoiceField(choices=PERIODES, help_text="Regroupement utilisé.")
    date_debut = serializers.DateField(help_text="Début effectif de la série.")
    date_fin = serializers.DateField(help_text="Fin effective de la série.")
    points = PointEvolutionSerializer(many=True, help_text="Une valeur par période, sans trou (0 si rien).")


class SecteurCarteSerializer(serializers.Serializer):
    id = _entier("Identifiant du secteur.")
    code = serializers.CharField(help_text="Code du secteur (choix de l'icône).")
    couleur = serializers.CharField(help_text="Couleur du marqueur.")


class PointSignalementSerializer(serializers.Serializer):
    id = _entier("Identifiant du signalement.")
    reference = serializers.CharField(help_text="Référence du signalement.")
    titre = serializers.CharField(help_text="Titre du signalement.")
    statut = serializers.ChoiceField(choices=Signalement.Statut.choices, help_text="Statut du signalement.")
    secteur = SecteurCarteSerializer(help_text="Secteur (pour la couleur du marqueur).")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Latitude.")
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Longitude.")
    cree_le = serializers.DateTimeField(help_text="Date d'envoi.")


class PointQuartierSerializer(serializers.Serializer):
    quartier = QuartierTableauSerializer(help_text="Quartier.")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Latitude du centre du quartier.")
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Longitude du centre du quartier.")
    signalements = _entier("Nombre de signalements du quartier (GPS et manuels).")


class PointRealisationSerializer(serializers.Serializer):
    id = _entier("Identifiant de la réalisation.")
    reference = serializers.CharField(help_text="Référence de la réalisation.")
    titre = serializers.CharField(help_text="Titre de la réalisation.")
    statut = serializers.CharField(help_text="Statut de la réalisation.")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Latitude du chantier.")
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, help_text="Longitude du chantier.")


class CarteSerializer(serializers.Serializer):
    signalements = PointSignalementSerializer(
        many=True, help_text="Signalements localisés en GPS, les plus récents d'abord (2 000 au maximum)."
    )
    signalements_tronques = serializers.BooleanField(
        help_text="Vrai si plus de 2 000 signalements correspondent : affiner les filtres."
    )
    quartiers = PointQuartierSerializer(
        many=True, help_text="Nombre de signalements par quartier, au centre du quartier (carte de chaleur)."
    )
    realisations = PointRealisationSerializer(many=True, help_text="Réalisations localisées.")
