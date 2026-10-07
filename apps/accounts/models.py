from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from phonenumber_field.phonenumber import to_python

from apps.core.models import ModeleHorodate


class UtilisateurManager(BaseUserManager):
    """Manager basé sur le numéro de téléphone (identifiant de connexion)."""

    use_in_migrations = True

    def _create_user(self, telephone, password, **extra_fields):
        if not telephone:
            raise ValueError("Le numéro de téléphone est obligatoire.")
        numero = to_python(telephone)
        if numero is None or not numero.is_valid():
            raise ValueError("Le numéro de téléphone est invalide.")
        champs_obligatoires = {
            "nom": "Le nom est obligatoire.",
            "prenoms": "Les prénoms sont obligatoires.",
        }
        for champ, message in champs_obligatoires.items():
            if not str(extra_fields.get(champ) or "").strip():
                raise ValueError(message)
        if extra_fields.get("email"):
            extra_fields["email"] = self.normalize_email(extra_fields["email"])
        utilisateur = self.model(telephone=numero, **extra_fields)
        utilisateur.set_password(password)
        utilisateur.save(using=self._db)
        return utilisateur

    def create_user(self, telephone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(telephone, password, **extra_fields)

    def create_superuser(self, telephone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Utilisateur.Role.ADMIN_MAIRIE)
        extra_fields.setdefault("telephone_verifie", True)
        if extra_fields["is_staff"] is not True:
            raise ValueError("Un superutilisateur doit avoir is_staff=True.")
        if extra_fields["is_superuser"] is not True:
            raise ValueError("Un superutilisateur doit avoir is_superuser=True.")
        return self._create_user(telephone, password, **extra_fields)


class Utilisateur(ModeleHorodate, AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CITOYEN = "CITOYEN", "Citoyen"
        AGENT = "AGENT", "Agent municipal"
        ADMIN_MAIRIE = "ADMIN_MAIRIE", "Administrateur mairie"
        ORGANISATION = "ORGANISATION", "Organisation"

    telephone = PhoneNumberField(
        "téléphone",
        unique=True,
        error_messages={"unique": "Un compte existe déjà avec ce numéro de téléphone."},
    )
    nom = models.CharField("nom", max_length=100)
    prenoms = models.CharField("prénoms", max_length=150)
    email = models.EmailField("adresse e-mail", null=True, blank=True)
    role = models.CharField(
        "rôle", max_length=20, choices=Role.choices, default=Role.CITOYEN
    )
    quartier_residence = models.ForeignKey(
        "territoire.Quartier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="residents",
        verbose_name="quartier de résidence",
    )
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="membres",
        verbose_name="organisation",
    )
    service = models.ForeignKey(
        "accounts.ServiceMunicipal",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents",
        verbose_name="service municipal",
    )
    telephone_verifie = models.BooleanField("téléphone vérifié", default=False)
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès à l'administration", default=False)
    date_joined = models.DateTimeField("date d'inscription", default=timezone.now)

    objects = UtilisateurManager()

    USERNAME_FIELD = "telephone"
    REQUIRED_FIELDS = ["nom", "prenoms"]

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        ordering = ["nom", "prenoms"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(role="AGENT") | models.Q(service__isnull=False),
                name="utilisateur_agent_avec_service",
                violation_error_message="Un agent doit être rattaché à un service municipal.",
            ),
            models.CheckConstraint(
                condition=~models.Q(role="ORGANISATION")
                | models.Q(organisation__isnull=False),
                name="utilisateur_organisation_avec_organisation",
                violation_error_message=(
                    "Un compte organisation doit être rattaché à une organisation."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.telephone})"

    def get_full_name(self):
        return f"{self.prenoms} {self.nom}".strip()

    def get_short_name(self):
        return self.prenoms

    def clean(self):
        super().clean()
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email)
        erreurs = {}
        if self.role == self.Role.AGENT and not self.service_id:
            erreurs["service"] = "Un agent doit être rattaché à un service municipal."
        if self.role == self.Role.ORGANISATION and not self.organisation_id:
            erreurs["organisation"] = (
                "Un compte organisation doit être rattaché à une organisation."
            )
        if erreurs:
            raise ValidationError(erreurs)


class Organisation(ModeleHorodate):
    class Type(models.TextChoices):
        ONG = "ONG", "ONG"
        OSC = "OSC", "OSC"
        AUTRE = "AUTRE", "Autre"

    class StatutHabilitation(models.TextChoices):
        # EN_ATTENTE et REVOQUEE viendront avec l'auto-inscription des organisations (hors MVP).
        HABILITEE = "HABILITEE", "Habilitée"
        SUSPENDUE = "SUSPENDUE", "Suspendue"

    nom = models.CharField("nom", max_length=200)
    sigle = models.CharField("sigle", max_length=50, blank=True)
    type = models.CharField("type", max_length=10, choices=Type.choices)
    numero_enregistrement = models.CharField(
        "numéro d'enregistrement",
        max_length=100,
        unique=True,
        error_messages={"unique": "Une organisation existe déjà avec ce numéro d'enregistrement."},
    )
    email = models.EmailField("adresse e-mail", blank=True)
    telephone = PhoneNumberField("téléphone", blank=True)
    adresse = models.CharField("adresse", max_length=255, blank=True)
    logo = models.ImageField("logo", upload_to="organisations/logos/", null=True, blank=True)
    statut_habilitation = models.CharField(
        "statut d'habilitation",
        max_length=20,
        choices=StatutHabilitation.choices,
        default=StatutHabilitation.HABILITEE,
    )
    motif_suspension = models.TextField(
        "motif de suspension",
        blank=True,
        help_text="Obligatoire quand l'organisation est suspendue, vidé à la réhabilitation.",
    )
    # Remplis automatiquement à la création depuis l'admin (voir services.creer_organisation).
    date_habilitation = models.DateField("date d'habilitation", null=True, editable=False)
    habilitee_par = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="organisations_habilitees",
        verbose_name="habilitée par",
    )
    date_expiration = models.DateField(
        "date d'expiration", null=True, blank=True, help_text="Laisser vide pour une habilitation sans limite."
    )
    secteurs = models.ManyToManyField(
        "referentiel.Secteur",
        blank=True,
        related_name="organisations",
        verbose_name="secteurs d'intervention",
    )

    class Meta:
        verbose_name = "organisation"
        verbose_name_plural = "organisations"
        ordering = ["nom"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(statut_habilitation="SUSPENDUE") | ~models.Q(motif_suspension=""),
                name="organisation_suspension_avec_motif",
                violation_error_message="Le motif de suspension est obligatoire.",
            ),
        ]

    def __str__(self):
        return self.sigle or self.nom

    def clean(self):
        super().clean()
        self.motif_suspension = self.motif_suspension.strip()
        if self.statut_habilitation == self.StatutHabilitation.HABILITEE:
            self.motif_suspension = ""
        elif not self.motif_suspension:
            raise ValidationError({"motif_suspension": "Le motif de suspension est obligatoire."})

    @property
    def acces_autorise(self):
        """Une organisation n'accède à l'API que si elle est habilitée et non expirée."""
        if self.statut_habilitation != self.StatutHabilitation.HABILITEE:
            return False
        return self.date_expiration is None or self.date_expiration >= timezone.localdate()


class ServiceMunicipal(ModeleHorodate):
    nom = models.CharField(
        "nom",
        max_length=150,
        unique=True,
        error_messages={"unique": "Un service porte déjà ce nom."},
    )
    description = models.TextField("description", blank=True)
    responsable = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services_diriges",
        verbose_name="responsable",
    )
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "service municipal"
        verbose_name_plural = "services municipaux"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class CodeOTP(ModeleHorodate):
    TENTATIVES_MAX = 5
    DUREE_VALIDITE_MINUTES = 10

    class Motif(models.TextChoices):
        INSCRIPTION = "INSCRIPTION", "Inscription"
        REINITIALISATION_MDP = "REINITIALISATION_MDP", "Réinitialisation du mot de passe"

    utilisateur = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.CASCADE,
        related_name="codes_otp",
        verbose_name="utilisateur",
    )
    # Seul le hash est stocké, jamais le code en clair.
    code_hash = models.CharField("empreinte du code", max_length=128)
    motif = models.CharField("motif", max_length=30, choices=Motif.choices)
    expire_le = models.DateTimeField("expire le")
    tentatives = models.PositiveSmallIntegerField("tentatives", default=0)
    utilise = models.BooleanField("utilisé", default=False)

    class Meta:
        verbose_name = "code OTP"
        verbose_name_plural = "codes OTP"
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["utilisateur", "motif"])]

    def __str__(self):
        return f"{self.get_motif_display()} – {self.utilisateur.telephone}"

    @property
    def est_expire(self):
        return timezone.now() >= self.expire_le

    @property
    def est_bloque(self):
        return self.tentatives >= self.TENTATIVES_MAX


class Appareil(ModeleHorodate):
    class Plateforme(models.TextChoices):
        ANDROID = "ANDROID", "Android"
        IOS = "IOS", "iOS"

    utilisateur = models.ForeignKey(
        "accounts.Utilisateur",
        on_delete=models.CASCADE,
        related_name="appareils",
        verbose_name="utilisateur",
    )
    token_fcm = models.CharField("jeton FCM", max_length=255, unique=True)
    plateforme = models.CharField("plateforme", max_length=10, choices=Plateforme.choices)
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "appareil"
        verbose_name_plural = "appareils"

    def __str__(self):
        return f"{self.get_plateforme_display()} – {self.utilisateur.telephone}"
