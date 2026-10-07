from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.reponses import reponse_succes
from apps.core.schema import (
    EXEMPLE_PAGE_INEXISTANTE,
    EXEMPLES_AUTH_REQUISE,
    TAG_NOTIFICATIONS,
    enveloppe,
    erreurs,
    exemple_element_liste,
    exemple_erreur,
    exemple_requete,
    exemple_succes,
)

from . import services
from .filters import NotificationFilter
from .models import Notification
from .serializers import AppareilSerializer, NotificationSerializer, ToutLuSerializer

JETON = "dGhpcyBpcyBhbiBleGFtcGxlIEZDTSB0b2tlbg:APA91bH0exemple-de-jeton-fcm"
NOTIFICATION = {
    "id": 2045,
    "type": "STATUT_SIGNALEMENT",
    "titre": "Votre signalement avance",
    "message": "Votre signalement SIG-2026-00128 est en cours de traitement.",
    "cible_type": "signalement",
    "cible_id": 128,
    "lu": False,
    "cree_le": "2026-10-07T09:02:13+01:00",
}
NOTIFICATION_REALISATION = {
    **NOTIFICATION,
    "id": 2051,
    "type": "NOUVELLE_REALISATION",
    "titre": "Nouvelle réalisation de la mairie",
    "message": "Pavage de la rue de l'EPP Togoudo",
    "cible_type": "realisation",
    "cible_id": 4,
}
EXEMPLE_INTROUVABLE = exemple_erreur(
    CodeErreur.RESSOURCE_INTROUVABLE, nom="Notification inconnue", description="Inexistante ou destinée à un autre compte."
)


class AppareilView(APIView):
    @extend_schema(
        tags=[TAG_NOTIFICATIONS],
        summary="Enregistrer l'appareil pour les notifications push",
        description="""
À appeler par l'application mobile **après chaque connexion** et **chaque fois que Firebase
fournit un nouveau jeton** (`onTokenRefresh`). L'appareil reçoit ensuite les notifications
push du compte connecté.

- Sans effet si l'appareil est déjà enregistré pour ce compte (il est simplement réactivé).
- Un jeton déjà connu pour un autre compte (téléphone partagé, réinstallation) passe sur le
  compte connecté : les notifications de l'ancien compte n'y arrivent plus.
- À la déconnexion, envoyer `token_fcm` à `POST /auth/logout/` pour arrêter les pushs.
- Un jeton refusé par Firebase (application désinstallée) est désactivé automatiquement.

**Réponse** : 201 si l'appareil est nouveau, 200 s'il était déjà connu.

**Connecté** : tous les rôles.
""",
        request=AppareilSerializer,
        responses={
            201: enveloppe(AppareilSerializer),
            200: enveloppe(AppareilSerializer),
            **erreurs(400, 401, 403),
        },
        examples=[
            exemple_requete("Téléphone Android", {"token_fcm": JETON, "plateforme": "ANDROID"}),
            exemple_succes(
                "Nouvel appareil",
                {"token_fcm": JETON, "plateforme": "ANDROID", "actif": True},
                "Appareil enregistré : vous recevrez les notifications.",
                statut=201,
            ),
            exemple_succes(
                "Appareil déjà connu",
                {"token_fcm": JETON, "plateforme": "ANDROID", "actif": True},
                "Appareil enregistré : vous recevrez les notifications.",
            ),
            exemple_erreur(
                CodeErreur.VALIDATION_ERREUR,
                details={"plateforme": ["« WINDOWS » n'est pas un choix valide."]},
                nom="Plateforme inconnue",
            ),
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def post(self, request):
        entree = AppareilSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        appareil, cree = services.enregistrer_appareil(request.user, **entree.validated_data)
        return reponse_succes(
            AppareilSerializer(appareil).data,
            "Appareil enregistré : vous recevrez les notifications.",
            status=status.HTTP_201_CREATED if cree else status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(
        tags=[TAG_NOTIFICATIONS],
        summary="Lister mes notifications",
        description="""
Notifications du compte connecté, de la plus récente à la plus ancienne (liste paginée).

**Quand une notification est-elle créée ?**
| `type` | Destinataire | Événement |
|---|---|---|
| `STATUT_SIGNALEMENT` | Auteur du signalement | Changement de statut |
| `REPONSE_SIGNALEMENT` | Auteur du signalement | Réponse officielle de la mairie |
| `REPONSE_SUGGESTION` | Auteur de la suggestion | Réponse officielle de la mairie |
| `NOUVELLE_REALISATION` | Auteurs des signalements / suggestions liés et habitants des quartiers concernés | Publication d'une réalisation |

`cible_type` et `cible_id` indiquent l'écran à ouvrir. Les mêmes informations sont envoyées
en push (données `notification_id`, `type`, `cible_type`, `cible_id`).

**Filtres** : `lu=false` (non lues : `pagination.total` donne leur nombre), `type`.

**Connecté** : tous les rôles.
""",
        responses={200: NotificationSerializer(many=True), **erreurs(401, 403, 404)},
        examples=[
            exemple_element_liste("Statut d'un signalement", NOTIFICATION),
            exemple_element_liste("Nouvelle réalisation", NOTIFICATION_REALISATION),
            EXEMPLE_PAGE_INEXISTANTE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
    patch=extend_schema(
        tags=[TAG_NOTIFICATIONS],
        summary="Tout marquer comme lu",
        description="""
Marque comme lues **toutes** les notifications non lues du compte connecté et renvoie leur
nombre. Aucun corps de requête n'est nécessaire.

**Connecté** : tous les rôles.
""",
        request=None,
        responses={200: enveloppe(ToutLuSerializer), **erreurs(401, 403)},
        examples=[
            exemple_succes("Notifications lues", {"nb_marquees": 3}, "Toutes vos notifications sont marquées comme lues."),
            *EXEMPLES_AUTH_REQUISE,
        ],
    ),
)
class NotificationListView(ListAPIView):
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilter

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return Notification.objects.filter(destinataire=self.request.user)

    def patch(self, request):
        nombre = services.tout_marquer_lu(request.user)
        return reponse_succes({"nb_marquees": nombre}, "Toutes vos notifications sont marquées comme lues.")


class NotificationLueView(APIView):
    @extend_schema(
        tags=[TAG_NOTIFICATIONS],
        summary="Marquer une notification comme lue",
        description="""
À appeler quand l'utilisateur ouvre la notification. Sans effet si elle est déjà lue.
Seules les notifications du compte connecté sont accessibles.

**Connecté** : tous les rôles.
""",
        request=None,
        parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH, description="Identifiant de la notification.")],
        responses={200: enveloppe(NotificationSerializer), **erreurs(401, 403, 404)},
        examples=[
            exemple_succes("Notification lue", {**NOTIFICATION, "lu": True}),
            EXEMPLE_INTROUVABLE,
            *EXEMPLES_AUTH_REQUISE,
        ],
    )
    def patch(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        return reponse_succes(NotificationSerializer(services.marquer_lue(notification)).data)
