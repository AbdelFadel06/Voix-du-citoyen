from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.codes_erreur import CodeErreur
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLES_AUTH_REQUISE,
    TAG_AUTH,
    enveloppe,
    erreurs,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
    exemple_trop_de_requetes,
)
from apps.core.throttling import ThrottleOTP

from . import exemples, services
from .serializers import (
    ConnexionSerializer,
    DeconnexionSerializer,
    InscriptionDonneesSerializer,
    InscriptionSerializer,
    JetonsRafraichisSerializer,
    JetonsSerializer,
    RafraichissementSerializer,
    RenvoiOTPSerializer,
    UtilisateurSerializer,
    VerificationOTPSerializer,
)

MESSAGE_INSCRIPTION = "Compte créé. Un code de vérification vous a été envoyé par SMS."
MESSAGE_VERIFICATION = "Votre numéro est vérifié. Bienvenue !"
MESSAGE_RENVOI = "Si une inscription est en attente pour ce numéro, un nouveau code a été envoyé."
MESSAGE_CONNEXION = "Connexion réussie."
MESSAGE_PROFIL = "Votre profil a été mis à jour."

EXEMPLE_TELEPHONE_INVALIDE = exemple_erreur(
    CodeErreur.VALIDATION_ERREUR,
    details={"telephone": ["Saisissez un numéro de téléphone valide."]},
    nom="Téléphone invalide",
)


def donnees_jetons(utilisateur):
    return {**services.generer_jetons(utilisateur), "utilisateur": UtilisateurSerializer(utilisateur).data}


class VuePublique(APIView):
    """Endpoint public : un jeton éventuellement expiré envoyé par le mobile est ignoré."""

    permission_classes = [AllowAny]
    authentication_classes = []


class InscriptionView(VuePublique):
    throttle_classes = [ThrottleOTP]

    @extend_schema(
        tags=[TAG_AUTH],
        summary="Créer un compte citoyen",
        description="""
Crée un compte **citoyen** non vérifié et envoie un **code à 6 chiffres** par SMS.
L'étape suivante est `POST /auth/otp/verify/`.

**Règles**
- Seuls les numéros béninois (+229) sont acceptés.
- Si le numéro a déjà été inscrit **sans être vérifié** (SMS perdu, erreur de saisie),
  l'inscription est reprise : les informations sont remplacées et un nouveau code est envoyé.
- Si le numéro appartient à un compte vérifié, ou à un agent ou une organisation :
  `TELEPHONE_DEJA_UTILISE` (409).
- Le code expire au bout de 10 minutes.

**Limitation** : 5 demandes de code par heure et par numéro (inscription et renvoi
confondus), sinon `TROP_DE_REQUETES` (429).

**Public** : aucun jeton requis.
""",
        auth=[],
        request=InscriptionSerializer,
        responses={201: enveloppe(InscriptionDonneesSerializer), **erreurs(400, 409, 429, 503)},
        examples=[
            exemple_requete(
                "Avec les champs obligatoires",
                {
                    "telephone": "0197123456",
                    "nom": "Hounkpatin",
                    "prenoms": "Afiavi",
                    "password": "Barometre!2026",
                },
            ),
            exemple_requete(
                "Avec e-mail et quartier",
                {
                    "telephone": "+2290197123456",
                    "nom": "Hounkpatin",
                    "prenoms": "Afiavi",
                    "email": "afiavi@exemple.bj",
                    "password": "Barometre!2026",
                    "quartier_residence": 12,
                },
            ),
            exemple_succes(
                "Compte créé", {"telephone": exemples.TELEPHONE}, MESSAGE_INSCRIPTION, statut=201
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={
                    "telephone": ["Saisissez un numéro de téléphone béninois (+229)."],
                    "prenoms": ["Ce champ est obligatoire."],
                    "password": [
                        "Ce mot de passe est trop court. Il doit contenir au minimum 8 caractères.",
                        "Ce mot de passe est entièrement numérique.",
                    ],
                },
                nom="Champs invalides",
            ),
            exemple_erreur(
                CodeErreur.TELEPHONE_DEJA_UTILISE,
                details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]},
            ),
            exemple_trop_de_requetes(),
            exemple_erreur(CodeErreur.SMS_ECHEC, description="Le fournisseur SMS n'a pas répondu."),
        ],
    )
    def post(self, request):
        serializer = InscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = services.inscrire_citoyen(**serializer.validated_data)
        return reponse_succes(
            {"telephone": str(utilisateur.telephone)},
            MESSAGE_INSCRIPTION,
            status=status.HTTP_201_CREATED,
        )


class VerificationOTPView(VuePublique):
    @extend_schema(
        tags=[TAG_AUTH],
        summary="Vérifier le numéro avec le code SMS",
        description="""
Valide le code reçu par SMS après l'inscription. En cas de succès, le numéro est marqué
vérifié et **le citoyen est connecté directement** : la réponse contient les jetons
`access` et `refresh` et le profil, comme `/auth/login/`.

**Règles**
- Le code est valable **10 minutes** et ne sert qu'une fois.
- **5 essais** au maximum par code. Chaque erreur indique le nombre d'essais restants
  (`details.tentatives_restantes`). Au 5ᵉ échec, le code est bloqué
  (`OTP_TENTATIVES_DEPASSEES`) : il faut en demander un nouveau avec `/auth/otp/resend/`.
- Un code expiré, déjà utilisé ou remplacé par un renvoi donne `OTP_EXPIRE`.

**Public** : aucun jeton requis.
""",
        auth=[],
        request=VerificationOTPSerializer,
        responses={200: enveloppe(JetonsSerializer), **erreurs(400, 429)},
        examples=[
            exemple_requete("Code reçu", {"telephone": "0197123456", "code": "482915"}),
            exemple_succes("Numéro vérifié", exemples.JETONS, MESSAGE_VERIFICATION),
            exemple_erreur(
                CodeErreur.OTP_INVALIDE,
                "Le code saisi est incorrect. Il vous reste 4 essais.",
                details={"tentatives_restantes": 4},
            ),
            exemple_erreur(CodeErreur.OTP_EXPIRE),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"code": ["Le code doit comporter 6 chiffres."]},
                nom="Format du code",
            ),
            exemple_erreur(CodeErreur.OTP_TENTATIVES_DEPASSEES),
        ],
    )
    def post(self, request):
        serializer = VerificationOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = services.verifier_inscription(**serializer.validated_data)
        return reponse_succes(donnees_jetons(utilisateur), MESSAGE_VERIFICATION)


class RenvoiOTPView(VuePublique):
    throttle_classes = [ThrottleOTP]

    @extend_schema(
        tags=[TAG_AUTH],
        summary="Renvoyer le code de vérification",
        description="""
Envoie un nouveau code par SMS à un numéro dont l'inscription n'est pas encore vérifiée.
**Le code précédent ne fonctionne plus.**

La réponse est **toujours la même**, que le numéro soit inscrit ou non, pour ne pas révéler
quels numéros ont un compte. Aucun SMS n'est envoyé si le numéro est inconnu ou déjà vérifié.

**Limitation** : 5 demandes de code par heure et par numéro (inscription et renvoi confondus).

**Public** : aucun jeton requis.
""",
        auth=[],
        request=RenvoiOTPSerializer,
        responses={200: enveloppe(), **erreurs(400, 429, 503)},
        examples=[
            exemple_requete("Numéro", {"telephone": "0197123456"}),
            exemple_succes("Demande prise en compte", None, MESSAGE_RENVOI),
            EXEMPLE_TELEPHONE_INVALIDE,
            exemple_trop_de_requetes(),
            exemple_erreur(CodeErreur.SMS_ECHEC),
        ],
    )
    def post(self, request):
        serializer = RenvoiOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.renvoyer_code_inscription(serializer.validated_data["telephone"])
        return reponse_succes(message=MESSAGE_RENVOI)


class ConnexionView(VuePublique):
    @extend_schema(
        tags=[TAG_AUTH],
        summary="Se connecter",
        description="""
Connexion par **numéro de téléphone et mot de passe**, pour tous les rôles.
Renvoie les jetons et le profil (le `role` indique quels écrans afficher).

**Refus possibles**
- `IDENTIFIANTS_INVALIDES` (401) : numéro inconnu ou mot de passe incorrect
  (la réponse ne précise pas lequel des deux).
- `TELEPHONE_NON_VERIFIE` (403) : citoyen dont le numéro n'est pas encore vérifié.
  Afficher l'écran de saisie du code (et proposer `/auth/otp/resend/`).
- `COMPTE_DESACTIVE` (403) : compte désactivé par la mairie (signalé seulement si le mot
  de passe est correct).
- `ORGANISATION_NON_HABILITEE` (403) : organisation suspendue ou habilitation expirée.

Les comptes agents et organisations, créés par la mairie, n'ont pas besoin de code SMS.

**Public** : aucun jeton requis.
""",
        auth=[],
        request=ConnexionSerializer,
        responses={200: enveloppe(JetonsSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete(
                "Identifiants", {"telephone": "0197123456", "password": "Barometre!2026"}
            ),
            exemple_succes("Citoyen connecté", exemples.JETONS, MESSAGE_CONNEXION),
            exemple_succes(
                "Agent connecté",
                {**exemples.JETONS, "utilisateur": exemples.AGENT},
                MESSAGE_CONNEXION,
            ),
            exemple_succes(
                "Organisation connectée",
                {**exemples.JETONS, "utilisateur": exemples.ORGANISATION},
                MESSAGE_CONNEXION,
            ),
            exemple_erreur(CodeErreur.IDENTIFIANTS_INVALIDES),
            exemple_erreur(CodeErreur.TELEPHONE_NON_VERIFIE),
            exemple_erreur(CodeErreur.COMPTE_DESACTIVE),
            exemple_erreur(CodeErreur.ORGANISATION_NON_HABILITEE),
            EXEMPLE_TELEPHONE_INVALIDE,
        ],
    )
    def post(self, request):
        serializer = ConnexionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        utilisateur = services.connecter(
            request,
            telephone=serializer.validated_data["telephone"].as_e164,
            password=serializer.validated_data["password"],
        )
        return reponse_succes(donnees_jetons(utilisateur), MESSAGE_CONNEXION)


@extend_schema_view(
    post=extend_schema(
        tags=[TAG_AUTH],
        summary="Renouveler les jetons",
        description="""
Échange le jeton `refresh` contre un **nouveau** jeton `access` **et** un **nouveau** jeton
`refresh`. L'ancien `refresh` devient immédiatement inutilisable : l'application doit
remplacer celui qu'elle a enregistré.

À appeler quand une requête répond `JETON_INVALIDE`. Si le rafraîchissement échoue lui
aussi (`JETON_INVALIDE`), l'utilisateur doit se reconnecter avec `/auth/login/`.

**Public** : aucun jeton `access` requis.
""",
        auth=[],
        request=RafraichissementSerializer,
        responses={200: enveloppe(JetonsRafraichisSerializer), **erreurs(400, 401)},
        examples=[
            exemple_requete("Jeton de rafraîchissement", {"refresh": exemples.REFRESH}),
            exemple_succes(
                "Nouveaux jetons", {"access": exemples.ACCESS, "refresh": exemples.REFRESH}
            ),
            exemple_erreur(
                CodeErreur.JETON_INVALIDE,
                description="Jeton expiré, déjà utilisé ou invalidé à la déconnexion.",
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"refresh": ["Ce champ est obligatoire."]},
                nom="Jeton manquant",
            ),
        ],
    )
)
class RafraichissementView(TokenRefreshView):
    pass


class DeconnexionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[TAG_AUTH],
        summary="Se déconnecter",
        description="""
Invalide le jeton `refresh` fourni : il ne pourra plus servir à obtenir de nouveaux jetons.
Avec `token_fcm`, l'appareil cesse aussi de recevoir les notifications push du compte.
Le jeton `access` en cours reste valable jusqu'à son expiration (30 minutes au plus) :
l'application doit le supprimer de son côté.

Le jeton `refresh` doit appartenir à l'utilisateur connecté (sinon `PERMISSION_REFUSEE`).

**Réponse** : 204, sans contenu.

**Connecté** : tous les rôles.
""",
        request=DeconnexionSerializer,
        responses={204: None, **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Jeton à invalider", {"refresh": exemples.REFRESH}),
            exemple_requete(
                "Déconnexion du téléphone (arrêt des pushs)",
                {"refresh": exemples.REFRESH, "token_fcm": "dGhpcyBpcyBhbiBleGFtcGxl:APA91bH0exemple"},
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"refresh": ["Ce champ est obligatoire."]},
                nom="Jeton manquant",
            ),
            exemple_erreur(CodeErreur.JETON_INVALIDE, description="Jeton `refresh` invalide ou expiré."),
            exemple_erreur(
                CodeErreur.PERMISSION_REFUSEE,
                "Ce jeton n'appartient pas à votre compte.",
                nom="Jeton d'un autre compte",
            ),
            exemple_erreur(CodeErreur.NON_AUTHENTIFIE),
        ],
    )
    def post(self, request):
        serializer = DeconnexionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.deconnecter(request.user, serializer.validated_data["refresh"])
        if serializer.validated_data.get("token_fcm"):
            from apps.notifications.services import desactiver_appareil

            desactiver_appareil(request.user, serializer.validated_data["token_fcm"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        tags=[TAG_AUTH],
        summary="Consulter son profil",
        description="""
Renvoie le profil de l'utilisateur connecté, quel que soit son rôle.
- `organisation` est renseigné pour les comptes `ORGANISATION`, `service` pour les `AGENT`.
- `quartier_residence` est l'identifiant d'un quartier (voir `GET /quartiers/`).

**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(UtilisateurSerializer), **erreurs(401, 403)},
        examples=[
            exemple_succes("Citoyen", exemples.CITOYEN),
            exemple_succes("Agent", exemples.AGENT),
            exemple_succes("Organisation", exemples.ORGANISATION),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    patch=extend_schema(
        tags=[TAG_AUTH],
        summary="Modifier son profil",
        description="""
Modifie **uniquement** les champs envoyés (mise à jour partielle).

Champs modifiables : `nom`, `prenoms`, `email`, `quartier_residence`.
Les autres champs (`telephone`, `role`…) sont ignorés s'ils sont envoyés.
- `email` : `null` ou `""` efface l'adresse.
- `quartier_residence` : identifiant d'un quartier **actif**, ou `null`.

**Connecté** : tous les rôles.
""",
        responses={200: enveloppe(UtilisateurSerializer), **erreurs(400, 401, 403)},
        examples=[
            exemple_requete("Changer de quartier", {"quartier_residence": 15}),
            exemple_requete(
                "Corriger le nom et effacer l'e-mail", {"nom": "Hounkpatin-Dossa", "email": None}
            ),
            exemple_succes(
                "Profil modifié", {**exemples.CITOYEN, "quartier_residence": 15}, MESSAGE_PROFIL
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"quartier_residence": ["Ce quartier n'existe pas ou n'est plus actif."]},
                nom="Quartier inconnu",
            ),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class MoiView(RetrieveUpdateAPIView):
    serializer_class = UtilisateurSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        reponse = super().update(request, *args, **kwargs)
        return reponse_succes(reponse.data, MESSAGE_PROFIL)
