"""
Documentation OpenAPI (Swagger) de l'API.

Dans chaque vue :

    @extend_schema(
        tags=[TAG_AUTH],
        summary="Titre court",
        description="Règles métier détaillées (Markdown).",
        request=MonSerializerEntree,
        responses={200: enveloppe(MonSerializer), **erreurs(400, 401)},
        examples=[exemple_requete(...), exemple_succes(...), exemple_erreur(CodeErreur.X)],
    )

- `enveloppe(S)` : composant « Reponse<S> » = {succes, message, donnees: S}.
- `erreurs(...)` : réponses d'erreur utilisant le composant « ReponseErreur ».
- `exemple_*` : exemples affichés dans Swagger, au format réel des réponses.
Les listes paginées sont documentées automatiquement par PaginationStandard.
L'introduction générale de la documentation est dans `documentation.py`.
"""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema_serializer
from rest_framework import serializers

from .codes_erreur import INFOS_ERREURS, CodeErreur, message_par_defaut, statut_http
from .reponses import corps_erreur, corps_succes

# ---------------------------------------------------------------------------
# Tags (groupes d'endpoints dans Swagger), dans l'ordre d'affichage
# ---------------------------------------------------------------------------

TAG_AUTH = "Authentification"
TAG_TERRITOIRE = "Territoire"
TAG_SECTEURS = "Secteurs"
TAG_MEDIAS = "Médias"
TAG_SIGNALEMENTS = "Signalements"
TAG_SUGGESTIONS = "Suggestions"
TAG_REALISATIONS = "Réalisations"
TAG_NOTIFICATIONS = "Notifications"
TAG_TABLEAUX_DE_BORD = "Tableaux de bord"
TAG_ADMINISTRATION = "Administration"
TAG_SYSTEME = "Système"

TAGS = [
    {
        "name": TAG_AUTH,
        "description": "Création de compte citoyen, vérification du numéro par SMS, connexion, "
        "jetons JWT et profil de l'utilisateur connecté.",
    },
    {
        "name": TAG_TERRITOIRE,
        "description": "Quartiers de la commune et proposition du quartier le plus proche d'une "
        "position GPS. Le quartier est obligatoire sur chaque signalement.",
    },
    {
        "name": TAG_SECTEURS,
        "description": "Secteurs d'intervention (voirie, éclairage, insalubrité…) utilisés pour "
        "classer les signalements, suggestions et réalisations.",
    },
    {
        "name": TAG_SIGNALEMENTS,
        "description": "Problèmes signalés par les citoyens (voirie, insalubrité, éclairage…), "
        "leur suivi par le citoyen et leur traitement par la mairie.",
    },
    {
        "name": TAG_SUGGESTIONS,
        "description": "Idées proposées par les citoyens pour le développement de la commune, "
        "soutiens des autres citoyens et décision de la mairie.",
    },
    {
        "name": TAG_REALISATIONS,
        "description": "Travaux entrepris et réalisés par la mairie, avec leur avancement et leurs "
        "photos avant / pendant / après. Consultables sans compte une fois publiés.",
    },
    {
        "name": TAG_NOTIFICATIONS,
        "description": "Enregistrement des téléphones pour les notifications push et consultation "
        "des notifications reçues (changement de statut, réponse de la mairie, nouvelle réalisation).",
    },
    {
        "name": TAG_TABLEAUX_DE_BORD,
        "description": "Chiffres agrégés pour la mairie et les organisations habilitées : synthèse, "
        "répartition par secteur et par quartier, évolution dans le temps, carte.",
    },
    {
        "name": TAG_ADMINISTRATION,
        "description": "Gestion par les admins mairie : commune, services municipaux et comptes des "
        "agents. Les secteurs et quartiers se gèrent dans leurs propres groupes.",
    },
    {
        "name": TAG_MEDIAS,
        "description": "Envoi des photos, vidéos et enregistrements vocaux, un fichier à la fois, "
        "avant de les joindre à un signalement, une suggestion ou une réalisation.",
    },
    {"name": TAG_SYSTEME, "description": "Supervision technique de l'API."},
]


class AuthentificationJWTScheme(SimpleJWTScheme):
    """Documente AuthentificationJWT comme un schéma Bearer JWT dans OpenAPI."""

    target_class = "apps.core.authentication.AuthentificationJWT"

    def get_security_definition(self, auto_schema):
        definition = super().get_security_definition(auto_schema)
        definition["description"] = (
            "Jeton d'accès (`access`) obtenu avec `/auth/login/` ou `/auth/otp/verify/`. "
            "Collez uniquement le jeton, sans le mot « Bearer ». Il est valable 30 minutes ; "
            "renouvelez-le avec `/auth/refresh/`."
        )
        return definition


# ---------------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------------


# Le libellé de chaque choix (statut HTTP – message) apparaît dans la doc de l'énumération
# « CodeErreurEnum » (voir ENUM_NAME_OVERRIDES dans les settings).
CHOIX_CODES_ERREUR = [
    (code.value, f"HTTP {statut} – {message}") for code, (statut, message) in INFOS_ERREURS.items()
]


class ErreurSerializer(serializers.Serializer):
    code = serializers.ChoiceField(
        choices=CHOIX_CODES_ERREUR,
        help_text="Code stable, en majuscules, à utiliser par les applications pour réagir à l'erreur.",
    )
    message = serializers.CharField(help_text="Message en français, affichable tel quel à l'utilisateur.")
    details = serializers.JSONField(
        allow_null=True,
        help_text="`null` en général. Pour `VALIDATION_ERREUR` : erreurs par champ "
        "(`{\"telephone\": [\"…\"]}`). Pour `TROP_DE_REQUETES` : `{\"attente_secondes\": n}`.",
    )


class ReponseErreurSerializer(serializers.Serializer):
    succes = serializers.BooleanField(default=False, help_text="Toujours `false` pour une erreur.")
    erreur = ErreurSerializer(help_text="Description de l'erreur.")


DESCRIPTIONS_ERREURS = {
    400: "Données invalides (`VALIDATION_ERREUR`) ou erreur métier.",
    401: "Non connecté, session expirée ou identifiants incorrects.",
    403: "Action non autorisée pour ce compte.",
    404: "Élément introuvable.",
    405: "Méthode non autorisée.",
    409: "Conflit avec des données existantes.",
    429: "Trop de demandes : `details.attente_secondes` indique le délai à respecter.",
    500: "Erreur inattendue du serveur.",
    503: "Service momentanément indisponible.",
}


def erreurs(*statuts):
    return {
        statut: OpenApiResponse(ReponseErreurSerializer, description=DESCRIPTIONS_ERREURS[statut])
        for statut in statuts
    }


# ---------------------------------------------------------------------------
# Enveloppe de succès
# ---------------------------------------------------------------------------

_enveloppes = {}


def enveloppe(serializer=None, many=False):
    """Composant « Reponse<Nom> » enveloppant `serializer` (ou `donnees: null` si None)."""
    if serializer is None:
        nom = "ReponseSimple"
    else:
        base = serializer.__name__.removesuffix("Serializer")
        nom = f"ReponseListe{base}" if many else f"Reponse{base}"

    if nom not in _enveloppes:
        if serializer is None:
            donnees = serializers.JSONField(
                allow_null=True, default=None, help_text="Toujours `null` pour cette réponse."
            )
        else:
            donnees = serializer(many=many, help_text="Données renvoyées par l'endpoint.")
        # many=False : l'enveloppe est toujours la réponse entière, même sur une vue de liste
        # (sinon drf-spectacular la mettrait dans un tableau).
        _enveloppes[nom] = extend_schema_serializer(many=False)(type(
            f"{nom}Serializer",
            (serializers.Serializer,),
            {
                "succes": serializers.BooleanField(
                    default=True, help_text="Toujours `true` pour un succès."
                ),
                "message": serializers.CharField(
                    allow_null=True,
                    help_text="Message de confirmation à afficher, ou `null`.",
                ),
                "donnees": donnees,
            },
        ))
    return _enveloppes[nom]


# ---------------------------------------------------------------------------
# Exemples
# ---------------------------------------------------------------------------


def exemple_requete(nom, valeur, description=None):
    return OpenApiExample(nom, value=valeur, request_only=True, description=description)


def exemple_succes(nom, donnees=None, message=None, statut=200, description=None):
    return OpenApiExample(
        nom,
        value=corps_succes(donnees, message),
        response_only=True,
        status_codes=[str(statut)],
        description=description,
    )


def exemple_element_liste(nom, element, description=None):
    """
    Exemple d'une liste **paginée** : on donne un seul élément, drf-spectacular construit
    la réponse complète (enveloppe + bloc `pagination`).
    """
    return OpenApiExample(nom, value=element, response_only=True, status_codes=["200"], description=description)


def exemple_erreur(code, message=None, details=None, nom=None, description=None):
    code = CodeErreur(code)
    return OpenApiExample(
        nom or code.value,
        value=corps_erreur(code, message or message_par_defaut(code), details),
        response_only=True,
        status_codes=[str(statut_http(code))],
        description=description,
    )


# Erreur d'une liste paginée quand `?page=` dépasse la dernière page.
EXEMPLE_PAGE_INEXISTANTE = OpenApiExample(
    "Page inexistante",
    value=corps_erreur(CodeErreur.RESSOURCE_INTROUVABLE, message_par_defaut(CodeErreur.RESSOURCE_INTROUVABLE)),
    response_only=True,
    status_codes=["404"],
    description="Le numéro de page demandé dépasse le nombre de pages.",
)

# Exemples communs à tous les endpoints protégés.
EXEMPLES_AUTH_REQUISE = [
    exemple_erreur(CodeErreur.NON_AUTHENTIFIE, description="Aucun jeton envoyé."),
    exemple_erreur(CodeErreur.JETON_INVALIDE, description="Jeton expiré ou falsifié."),
    exemple_erreur(
        CodeErreur.ORGANISATION_NON_HABILITEE,
        description="Compte organisation suspendu ou habilitation expirée.",
    ),
    exemple_erreur(CodeErreur.COMPTE_DESACTIVE, description="Compte désactivé par la mairie."),
]


def exemple_trop_de_requetes(secondes=1800):
    return exemple_erreur(
        CodeErreur.TROP_DE_REQUETES,
        f"Trop de demandes. Réessayez dans {secondes // 60} minutes.",
        details={"attente_secondes": secondes},
    )


# ---------------------------------------------------------------------------
# Post-traitement du schéma
# ---------------------------------------------------------------------------


def completer_documentation(result, generator, request, public):
    """Ajoute l'introduction générale et la description des tags au schéma."""
    from .documentation import introduction

    result["info"]["description"] = introduction()
    result["tags"] = TAGS
    return result


def parametre_id(description):
    """Paramètre de chemin `{id}` documenté (ex. `parametre_id("Identifiant du secteur.")`)."""
    return OpenApiParameter("id", int, OpenApiParameter.PATH, description=description)


# ---------------------------------------------------------------------------
# Imports CSV (`POST /…/import/`)
# ---------------------------------------------------------------------------


def schema_import(tag, quoi, format_csv, bilan, exemple_lignes, serializer_bilan=None, parametres="", requete=None):
    """Arguments de @extend_schema communs aux endpoints d'import CSV."""
    from .serializers import BilanImportSerializer, ImportCSVSerializer

    serializer_bilan = serializer_bilan or BilanImportSerializer
    return {
        "tags": [tag],
        "summary": f"Importer des {quoi} depuis un fichier CSV",
        "description": f"""
Crée ou met à jour des {quoi} en masse à partir d'un fichier CSV envoyé en
`multipart/form-data` (champ `fichier`). Même règles que la commande du serveur.

**Format** (une ligne par élément, la première ligne contient les noms des colonnes) :
```
{format_csv}
```
{parametres}
**Fonctionnement**
- **Tout ou rien** : la moindre erreur refuse tout le fichier (`IMPORT_CSV_INVALIDE`) ;
  `details.lignes` donne un message par problème, avec son numéro de ligne, à afficher
  tel quel.
- Relancer le même fichier met à jour sans créer de doublon.
- `simulation=true` vérifie et compte sans rien enregistrer : idéal pour un aperçu avant
  confirmation.
- `desactiver_absents=true` désactive ce qui n'est plus dans le fichier (rien n'est supprimé).

**Connecté** : admins mairie uniquement.
""",
        "request": {"multipart/form-data": requete or ImportCSVSerializer},
        "responses": {200: enveloppe(serializer_bilan), **erreurs(400, 401, 403)},
        "examples": [
            exemple_succes("Import terminé", {**bilan, "simulation": False}, "Import terminé : …"),
            exemple_succes("Simulation", {**bilan, "simulation": True}, "Simulation : … Rien n'a été enregistré."),
            exemple_erreur(CodeErreur.IMPORT_CSV_INVALIDE, details={"lignes": exemple_lignes}),
            exemple_erreur(
                CodeErreur.PERMISSION_REFUSEE,
                "Action réservée aux administrateurs de la mairie.",
                nom="Réservé aux admins mairie",
            ),
            *EXEMPLES_AUTH_REQUISE,
        ],
    }
