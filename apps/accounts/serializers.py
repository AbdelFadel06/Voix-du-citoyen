from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

from apps.territoire.models import Commune, Quartier
from apps.territoire.serializers import CommuneResumeSerializer

from .models import Organisation, ServiceMunicipal, Utilisateur, normaliser_email

MESSAGE_TELEPHONE_INVALIDE = "Saisissez un numéro de téléphone valide."
AIDE_TELEPHONE = (
    "Numéro béninois, au format national (`0197123456`) ou international (`+2290197123456`)."
)
AIDE_MOT_DE_PASSE = (
    "Au moins 8 caractères, pas uniquement des chiffres, pas trop proche du nom ni trop courant."
)


def champ_telephone(help_text=AIDE_TELEPHONE):
    return PhoneNumberField(error_messages={"invalid": MESSAGE_TELEPHONE_INVALIDE}, help_text=help_text)


def champ_commune(help_text, required=True):
    return serializers.PrimaryKeyRelatedField(
        queryset=Commune.objects.all(),
        required=required,
        error_messages={"does_not_exist": "Cette commune n'est pas desservie par la plateforme."},
        help_text=help_text,
    )


def controler_quartier_dans_commune(quartier, commune):
    if quartier is not None and commune is not None and quartier.arrondissement.commune_id != commune.pk:
        raise serializers.ValidationError(
            {"quartier_residence": [f"Ce quartier n'est pas dans la commune de {commune.nom}."]}
        )


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

    commune = champ_commune(
        "Identifiant de la commune de résidence (`GET /communes/`). Les citoyens peuvent la changer ; "
        "pour la mairie, c'est la commune de sa mairie (non modifiable ici).",
        required=False,
    )
    commune_nom = serializers.CharField(
        source="commune.nom", read_only=True, allow_null=True, help_text="Nom de la commune de résidence."
    )
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
            "commune",
            "commune_nom",
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
            "email": {
                "help_text": "Adresse e-mail : identifiant de connexion (obligatoire) pour la mairie et les "
                "organisations, facultative pour les citoyens (`null` ou `\"\"` pour l'effacer)."
            },
            "role": {"help_text": "Rôle du compte, qui détermine ses droits. Non modifiable."},
            "telephone_verifie": {"help_text": "Vrai une fois le numéro confirmé par le code SMS."},
            "date_joined": {"help_text": "Date de création du compte."},
        }

    def validate(self, attrs):
        compte = self.instance
        if compte is not None and compte.role != Utilisateur.Role.CITOYEN:
            attrs.pop("commune", None)  # la commune de la mairie se gère dans /agents/
        commune = attrs.get("commune", getattr(compte, "commune", None))
        if "commune" in attrs and "quartier_residence" not in attrs and compte is not None:
            # Changement de commune : l'ancien quartier n'est plus valable.
            ancien = compte.quartier_residence
            if ancien is not None and ancien.arrondissement.commune_id != commune.pk:
                attrs["quartier_residence"] = None
        controler_quartier_dans_commune(attrs.get("quartier_residence"), commune)
        return attrs

    def validate_email(self, valeur):
        email = normaliser_email(valeur)
        compte = self.instance
        if not email and compte is not None and compte.role in Utilisateur.ROLES_CONNEXION_EMAIL:
            raise serializers.ValidationError("L'adresse e-mail est obligatoire : elle sert à vous connecter.")
        if email and Utilisateur.objects.filter(email__iexact=email).exclude(pk=getattr(compte, "pk", None)).exists():
            raise serializers.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email


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
    commune = champ_commune(
        "Identifiant de la commune de résidence, choisie dans `GET /communes/` (seules les communes "
        "où la plateforme est déployée y figurent). **Obligatoire.**"
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
        controler_quartier_dans_commune(attrs.get("quartier_residence"), attrs["commune"])
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


class IdentifiantSerializer(serializers.Serializer):
    """Identifiant de connexion : téléphone pour les citoyens, e-mail pour la mairie et les organisations."""

    telephone = PhoneNumberField(
        required=False,
        error_messages={"invalid": MESSAGE_TELEPHONE_INVALIDE},
        help_text="**Citoyens** : numéro de téléphone (`0197123456` ou `+2290197123456`).",
    )
    email = serializers.EmailField(
        required=False,
        help_text="**Mairie et organisations** : adresse e-mail du compte.",
    )

    def validate(self, attrs):
        if bool(attrs.get("telephone")) == bool(attrs.get("email")):
            raise serializers.ValidationError(
                {"identifiant": ["Indiquez soit le numéro de téléphone (citoyens), soit l'adresse e-mail (mairie, organisations)."]}
            )
        return attrs

    def identifiant(self):
        donnees = self.validated_data
        telephone = donnees.get("telephone")
        return {"telephone": telephone.as_e164 if telephone else None, "email": donnees.get("email")}


class ConnexionSerializer(IdentifiantSerializer):
    password = serializers.CharField(
        trim_whitespace=False, style={"input_type": "password"}, help_text="Mot de passe du compte."
    )


class DemandeReinitialisationSerializer(IdentifiantSerializer):
    pass


class ReinitialisationSerializer(IdentifiantSerializer):
    code = serializers.RegexField(
        r"^\d{6}$",
        error_messages={"invalid": "Le code doit comporter 6 chiffres."},
        help_text="Code à 6 chiffres reçu par SMS. Valable 10 minutes, 5 essais au maximum.",
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
        help_text="Nouveau mot de passe. " + AIDE_MOT_DE_PASSE,
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


# ---------------------------------------------------------------------------
# Administration : services municipaux et comptes du personnel (admins mairie)
# ---------------------------------------------------------------------------

ROLES_PERSONNEL = [
    (Utilisateur.Role.AGENT, Utilisateur.Role.AGENT.label),
    (Utilisateur.Role.ADMIN_MAIRIE, Utilisateur.Role.ADMIN_MAIRIE.label),
]


def _personnel_actif():
    return Utilisateur.objects.filter(
        role__in=[Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE], is_active=True
    )


class ServiceMunicipalSerializer(serializers.ModelSerializer):
    commune = CommuneResumeSerializer(help_text="Commune (mairie) du service.")
    responsable = AgentResumeSerializer(allow_null=True, help_text="Responsable du service, ou `null`.")
    nb_agents = serializers.IntegerField(read_only=True, help_text="Nombre d'agents actifs du service.")

    class Meta:
        model = ServiceMunicipal
        fields = ["id", "commune", "nom", "description", "responsable", "nb_agents", "actif"]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant du service (pour assigner un signalement)."},
            "nom": {"help_text": "Nom du service."},
            "description": {"help_text": "Missions du service (peut être vide)."},
            "actif": {"help_text": "Faux si le service n'existe plus."},
        }


class ServiceMunicipalEcritureSerializer(serializers.ModelSerializer):
    """La commune du service est déduite de l'admin connecté (`context["request"]`)."""

    commune = champ_commune(
        "Commune du service. Uniquement pour un admin de la plateforme ; sinon c'est la commune "
        "de l'admin connecté.",
        required=False,
    )
    responsable = serializers.PrimaryKeyRelatedField(
        queryset=_personnel_actif(),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce responsable n'est pas un agent ou un admin actif."},
        help_text="Identifiant de l'agent ou de l'admin responsable (facultatif).",
    )

    class Meta:
        model = ServiceMunicipal
        fields = ["commune", "nom", "description", "responsable", "actif"]
        validators = []  # unicité (commune, nom) vérifiée ci-dessous avec un message clair
        extra_kwargs = {
            "nom": {"help_text": "Nom du service, unique dans la commune."},
            "description": {"help_text": "Missions du service (facultatif)."},
            "actif": {"help_text": "`false` quand le service n'existe plus (rien n'est supprimé)."},
        }

    def validate(self, attrs):
        from apps.core.communes import commune_d_action

        demandee = attrs.pop("commune", None)
        commune = self.instance.commune if self.instance else commune_d_action(self.context["request"].user, demandee)
        nom = attrs.get("nom", getattr(self.instance, "nom", ""))
        doublons = ServiceMunicipal.objects.filter(commune=commune, nom__iexact=nom)
        if self.instance:
            doublons = doublons.exclude(pk=self.instance.pk)
        if doublons.exists():
            raise serializers.ValidationError({"nom": ["Un service porte déjà ce nom dans cette commune."]})
        responsable = attrs.get("responsable")
        if responsable is not None and responsable.commune_id not in (None, commune.pk):
            raise serializers.ValidationError({"responsable": ["Ce responsable travaille dans une autre commune."]})
        attrs["commune"] = commune
        return attrs


class AgentSerializer(serializers.ModelSerializer):
    commune = CommuneResumeSerializer(
        allow_null=True, help_text="Commune de la mairie, ou `null` pour un admin de la plateforme."
    )
    service = ServiceResumeSerializer(allow_null=True, help_text="Service de l'agent, ou `null`.")
    actif = serializers.BooleanField(source="is_active", help_text="Faux si le compte est désactivé.")

    class Meta:
        model = Utilisateur
        fields = [
            "id", "telephone", "nom", "prenoms", "email", "role", "commune", "service", "actif", "date_joined", "last_login",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "id": {"help_text": "Identifiant du compte (pour assigner un signalement)."},
            "telephone": {"help_text": "Téléphone, identifiant de connexion."},
            "nom": {"help_text": "Nom."},
            "prenoms": {"help_text": "Prénom(s)."},
            "email": {"help_text": "Adresse e-mail, ou `null`."},
            "role": {"help_text": "`AGENT` ou `ADMIN_MAIRIE`."},
            "date_joined": {"help_text": "Date de création du compte."},
            "last_login": {"help_text": "Dernière connexion, ou `null`."},
        }


class _AgentEcritureSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100, help_text="Nom.")
    prenoms = serializers.CharField(max_length=150, help_text="Prénom(s).")
    email = serializers.EmailField(help_text="Adresse e-mail, **identifiant de connexion** (unique).")
    role = serializers.ChoiceField(
        choices=ROLES_PERSONNEL,
        help_text="`AGENT` (traite les dossiers) ou `ADMIN_MAIRIE` (gère aussi le référentiel et les comptes).",
    )
    service = serializers.PrimaryKeyRelatedField(
        queryset=ServiceMunicipal.objects.filter(actif=True),
        required=False,
        allow_null=True,
        error_messages={"does_not_exist": "Ce service n'existe pas ou n'est plus actif."},
        help_text="Identifiant du service municipal. **Obligatoire pour un `AGENT`.**",
    )
    mot_de_passe = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}, help_text=AIDE_MOT_DE_PASSE
    )

    def validate_mot_de_passe(self, valeur):
        try:
            validate_password(valeur)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return valeur


class AgentCreationSerializer(_AgentEcritureSerializer):
    telephone = champ_telephone(AIDE_TELEPHONE)
    commune = champ_commune(
        "Commune de la mairie. Uniquement pour un admin de la plateforme ; sinon c'est la commune "
        "de l'admin connecté.",
        required=False,
    )

    def validate_telephone(self, valeur):
        if valeur.country_code != 229:
            raise serializers.ValidationError("Saisissez un numéro de téléphone béninois (+229).")
        return valeur


class AgentModificationSerializer(_AgentEcritureSerializer):
    actif = serializers.BooleanField(
        required=False, help_text="`false` désactive le compte : la personne ne peut plus se connecter."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for champ in self.fields.values():
            champ.required = False
        self.fields["mot_de_passe"].help_text = "Nouveau mot de passe (facultatif). " + AIDE_MOT_DE_PASSE
