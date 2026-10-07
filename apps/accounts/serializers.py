from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

from apps.territoire.models import Quartier

from .models import Organisation, ServiceMunicipal, Utilisateur

MESSAGE_TELEPHONE_INVALIDE = "Saisissez un numéro de téléphone valide."
AIDE_TELEPHONE = (
    "Numéro béninois, au format national (`0197123456`) ou international (`+2290197123456`)."
)
AIDE_MOT_DE_PASSE = (
    "Au moins 8 caractères, pas uniquement des chiffres, pas trop proche du nom ni trop courant."
)


def champ_telephone(help_text=AIDE_TELEPHONE):
    return PhoneNumberField(error_messages={"invalid": MESSAGE_TELEPHONE_INVALIDE}, help_text=help_text)


def champ_quartier_residence():
    return serializers.PrimaryKeyRelatedField(
        queryset=Quartier.objects.filter(actif=True),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce quartier n'existe pas ou n'est plus actif."},
        help_text="Identifiant du quartier de résidence (voir `GET /quartiers/`). Facultatif.",
    )


# ---------------------------------------------------------------------------
# Lecture du profil
# ---------------------------------------------------------------------------


class OrganisationResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ["id", "nom", "sigle"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'organisation."},
            "nom": {"help_text": "Nom complet de l'organisation."},
            "sigle": {"help_text": "Sigle, ou chaîne vide."},
        }


class ServiceResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceMunicipal
        fields = ["id", "nom"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant du service."},
            "nom": {"help_text": "Nom du service municipal."},
        }


class UtilisateurSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur connecté (`/auth/me/`) : seuls identité et quartier sont modifiables."""

    quartier_residence = champ_quartier_residence()
    organisation = OrganisationResumeSerializer(
        read_only=True,
        allow_null=True,
        help_text="Organisation du compte (rôle `ORGANISATION` uniquement), sinon `null`.",
    )
    service = ServiceResumeSerializer(
        read_only=True,
        allow_null=True,
        help_text="Service municipal de l'agent (rôle `AGENT`), sinon `null`.",
    )

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "telephone",
            "nom",
            "prenoms",
            "email",
            "role",
            "quartier_residence",
            "organisation",
            "service",
            "telephone_verifie",
            "date_joined",
        ]
        read_only_fields = ["id", "telephone", "role", "telephone_verifie", "date_joined"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'utilisateur."},
            "telephone": {
                "help_text": "Numéro de téléphone (identifiant de connexion), format international. "
                "Non modifiable."
            },
            "nom": {"help_text": "Nom de famille."},
            "prenoms": {"help_text": "Prénom(s)."},
            "email": {"help_text": "Adresse e-mail facultative. Envoyer `null` ou `\"\"` pour l'effacer."},
            "role": {"help_text": "Rôle du compte, qui détermine ses droits. Non modifiable."},
            "telephone_verifie": {"help_text": "Vrai une fois le numéro confirmé par le code SMS."},
            "date_joined": {"help_text": "Date de création du compte."},
        }

    def validate_email(self, valeur):
        return Utilisateur.objects.normalize_email(valeur) if valeur else None


# ---------------------------------------------------------------------------
# Inscription et OTP
# ---------------------------------------------------------------------------


class InscriptionSerializer(serializers.Serializer):
    telephone = champ_telephone(AIDE_TELEPHONE + " Il servira d'identifiant de connexion.")
    nom = serializers.CharField(max_length=100, help_text="Nom de famille.")
    prenoms = serializers.CharField(max_length=150, help_text="Prénom(s).")
    email = serializers.EmailField(
        required=False, allow_blank=True, allow_null=True, help_text="Adresse e-mail. Facultative."
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
        help_text=AIDE_MOT_DE_PASSE,
    )
    quartier_residence = champ_quartier_residence()

    def validate_telephone(self, valeur):
        if valeur.country_code != 229:
            raise serializers.ValidationError("Saisissez un numéro de téléphone béninois (+229).")
        return valeur

    def validate(self, attrs):
        utilisateur = Utilisateur(
            telephone=attrs["telephone"],
            nom=attrs["nom"],
            prenoms=attrs["prenoms"],
            email=attrs.get("email") or None,
        )
        try:
            validate_password(attrs["password"], user=utilisateur)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class VerificationOTPSerializer(serializers.Serializer):
    telephone = champ_telephone("Numéro utilisé lors de l'inscription.")
    code = serializers.RegexField(
        r"^\d{6}$",
        error_messages={"invalid": "Le code doit comporter 6 chiffres."},
        help_text="Code à 6 chiffres reçu par SMS. Valable 10 minutes, 5 essais au maximum.",
    )


class RenvoiOTPSerializer(serializers.Serializer):
    telephone = champ_telephone("Numéro utilisé lors de l'inscription.")


class InscriptionDonneesSerializer(serializers.Serializer):
    telephone = serializers.CharField(
        help_text="Numéro enregistré, au format international, auquel le code a été envoyé."
    )


# ---------------------------------------------------------------------------
# Connexion / jetons
# ---------------------------------------------------------------------------


class ConnexionSerializer(serializers.Serializer):
    telephone = champ_telephone()
    password = serializers.CharField(
        trim_whitespace=False, style={"input_type": "password"}, help_text="Mot de passe du compte."
    )


class JetonsSerializer(serializers.Serializer):
    access = serializers.CharField(
        help_text="Jeton d'accès, valable 30 minutes. À envoyer dans l'en-tête "
        "`Authorization: Bearer <access>`."
    )
    refresh = serializers.CharField(
        help_text="Jeton de rafraîchissement, valable 30 jours. À conserver de façon sécurisée "
        "pour obtenir de nouveaux jetons avec `/auth/refresh/`."
    )
    utilisateur = UtilisateurSerializer(help_text="Profil de l'utilisateur connecté.")


class RafraichissementSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Dernier jeton `refresh` reçu.")


class JetonsRafraichisSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Nouveau jeton d'accès, valable 30 minutes.")
    refresh = serializers.CharField(
        help_text="Nouveau jeton de rafraîchissement : il remplace l'ancien, devenu inutilisable."
    )


class DeconnexionSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Jeton `refresh` à invalider.")
    token_fcm = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Jeton Firebase de l'appareil : il ne recevra plus les notifications de ce compte.",
    )


class AgentResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Utilisateur
        fields = ["id", "nom", "prenoms"]
        extra_kwargs = {
            "id": {"help_text": "Identifiant de l'agent."},
            "nom": {"help_text": "Nom de l'agent."},
            "prenoms": {"help_text": "Prénom(s) de l'agent."},
        }
