import logging
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import update_last_login
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.sms import EnvoiSMSEchoue, envoyer_sms

from .models import CodeOTP, Organisation, Utilisateur

logger = logging.getLogger(__name__)

Role = Utilisateur.Role

MESSAGE_SMS_OTP = (
    "Voix du Citoyen : votre code de vérification est {code}. "
    "Il expire dans {minutes} minutes. Ne le partagez avec personne."
)


def _erreur_telephone_deja_utilise():
    return ErreurMetier(
        CodeErreur.TELEPHONE_DEJA_UTILISE,
        details={"telephone": ["Ce numéro de téléphone est déjà utilisé."]},
    )


# ---------------------------------------------------------------------------
# Codes OTP
# ---------------------------------------------------------------------------


def generer_code_otp(utilisateur, motif):
    """
    Crée un nouveau code (les précédents non utilisés sont supprimés) et l'envoie par SMS.
    Le code n'apparaît que dans le SMS : jamais dans les logs ni dans les réponses.
    """
    code = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        CodeOTP.objects.filter(utilisateur=utilisateur, motif=motif, utilise=False).delete()
        CodeOTP.objects.create(
            utilisateur=utilisateur,
            motif=motif,
            code_hash=make_password(code),
            expire_le=timezone.now() + timedelta(minutes=CodeOTP.DUREE_VALIDITE_MINUTES),
        )
    message = MESSAGE_SMS_OTP.format(code=code, minutes=CodeOTP.DUREE_VALIDITE_MINUTES)
    try:
        envoyer_sms(utilisateur.telephone, message)
    except EnvoiSMSEchoue:
        logger.exception("Échec d'envoi du SMS OTP (%s) à l'utilisateur %s", motif, utilisateur.pk)
        raise ErreurMetier(CodeErreur.SMS_ECHEC)


def _verifier_code_otp(utilisateur, motif, code):
    """Contrôle le code ; chaque échec est enregistré avant que l'erreur soit levée."""
    erreur = None
    with transaction.atomic():
        otp = (
            CodeOTP.objects.select_for_update()
            .filter(utilisateur=utilisateur, motif=motif, utilise=False)
            .order_by("-cree_le")
            .first()
        )
        if otp is None or otp.est_expire:
            erreur = ErreurMetier(CodeErreur.OTP_EXPIRE)
        elif otp.est_bloque:
            erreur = ErreurMetier(CodeErreur.OTP_TENTATIVES_DEPASSEES)
        elif not check_password(code, otp.code_hash):
            otp.tentatives += 1
            otp.save(update_fields=["tentatives", "maj_le"])
            restantes = CodeOTP.TENTATIVES_MAX - otp.tentatives
            if restantes > 0:
                erreur = ErreurMetier(
                    CodeErreur.OTP_INVALIDE,
                    f"Le code saisi est incorrect. Il vous reste {restantes} essai"
                    f"{'s' if restantes > 1 else ''}.",
                    details={"tentatives_restantes": restantes},
                )
            else:
                erreur = ErreurMetier(CodeErreur.OTP_TENTATIVES_DEPASSEES)
        else:
            otp.utilise = True
            otp.save(update_fields=["utilise", "maj_le"])
    if erreur:
        raise erreur


# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------


def _citoyen_non_verifie(telephone):
    return Utilisateur.objects.filter(
        telephone=telephone, role=Role.CITOYEN, telephone_verifie=False
    ).first()


def inscrire_citoyen(*, telephone, nom, prenoms, password, email=None, quartier_residence=None):
    """
    Crée un compte citoyen non vérifié et envoie un code OTP.
    Un compte citoyen jamais vérifié peut être repris (ex. erreur de saisie, SMS non reçu),
    car il n'a encore donné accès à rien.
    """
    email = Utilisateur.objects.normalize_email(email) if email else None
    try:
        with transaction.atomic():
            existant = Utilisateur.objects.select_for_update().filter(telephone=telephone).first()
            if existant is not None:
                if existant.role != Role.CITOYEN or existant.telephone_verifie:
                    raise _erreur_telephone_deja_utilise()
                utilisateur = existant
                utilisateur.nom = nom
                utilisateur.prenoms = prenoms
                utilisateur.email = email
                utilisateur.quartier_residence = quartier_residence
                utilisateur.set_password(password)
                utilisateur.save()
            else:
                utilisateur = Utilisateur.objects.create_user(
                    telephone,
                    password=password,
                    nom=nom,
                    prenoms=prenoms,
                    email=email,
                    quartier_residence=quartier_residence,
                    role=Role.CITOYEN,
                )
    except IntegrityError:
        # Deux inscriptions simultanées avec le même numéro.
        raise _erreur_telephone_deja_utilise()

    generer_code_otp(utilisateur, CodeOTP.Motif.INSCRIPTION)
    return utilisateur


def verifier_inscription(telephone, code):
    """Valide le code d'inscription et marque le téléphone comme vérifié."""
    utilisateur = _citoyen_non_verifie(telephone)
    if utilisateur is None:
        raise ErreurMetier(CodeErreur.OTP_EXPIRE)
    _verifier_code_otp(utilisateur, CodeOTP.Motif.INSCRIPTION, code)
    utilisateur.telephone_verifie = True
    utilisateur.save(update_fields=["telephone_verifie", "maj_le"])
    return utilisateur


def renvoyer_code_inscription(telephone):
    """
    Renvoie un code si le numéro correspond à une inscription en attente.
    Ne signale rien sinon, pour ne pas révéler quels numéros sont inscrits.
    """
    utilisateur = _citoyen_non_verifie(telephone)
    if utilisateur is not None:
        generer_code_otp(utilisateur, CodeOTP.Motif.INSCRIPTION)


# ---------------------------------------------------------------------------
# Connexion / jetons
# ---------------------------------------------------------------------------


def verifier_acces_organisation(utilisateur):
    """Refuse l'accès à un compte organisation dont l'habilitation n'est pas active."""
    if utilisateur.role != Role.ORGANISATION:
        return
    organisation = utilisateur.organisation
    if organisation is None or not organisation.acces_autorise:
        raise ErreurMetier(CodeErreur.ORGANISATION_NON_HABILITEE)


def connecter(request, telephone, password):
    utilisateur = authenticate(request, telephone=telephone, password=password)
    if utilisateur is None:
        # Le compte désactivé n'est signalé qu'à qui connaît le bon mot de passe.
        candidat = Utilisateur.objects.filter(telephone=telephone).first()
        if candidat and not candidat.is_active and candidat.check_password(password):
            raise ErreurMetier(CodeErreur.COMPTE_DESACTIVE)
        raise ErreurMetier(CodeErreur.IDENTIFIANTS_INVALIDES)
    if utilisateur.role == Role.CITOYEN and not utilisateur.telephone_verifie:
        raise ErreurMetier(CodeErreur.TELEPHONE_NON_VERIFIE)
    verifier_acces_organisation(utilisateur)
    update_last_login(None, utilisateur)
    return utilisateur


def generer_jetons(utilisateur):
    refresh = RefreshToken.for_user(utilisateur)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def deconnecter(utilisateur, refresh):
    """Invalide le jeton de rafraîchissement (blacklist) de l'utilisateur connecté."""
    try:
        jeton = RefreshToken(refresh)
    except TokenError:
        raise ErreurMetier(CodeErreur.JETON_INVALIDE)
    if str(jeton.get(jwt_settings.USER_ID_CLAIM)) != str(utilisateur.pk):
        raise ErreurMetier(
            CodeErreur.PERMISSION_REFUSEE, "Ce jeton n'appartient pas à votre compte."
        )
    jeton.blacklist()


# ---------------------------------------------------------------------------
# Habilitation des organisations (admin)
# ---------------------------------------------------------------------------


def creer_organisation(organisation, par):
    """Enregistre une nouvelle organisation, habilitée ce jour par l'admin `par`."""
    organisation.statut_habilitation = Organisation.StatutHabilitation.HABILITEE
    organisation.motif_suspension = ""
    organisation.date_habilitation = timezone.localdate()
    organisation.habilitee_par = par
    organisation.save()
    return organisation


def suspendre_organisation(organisation, motif):
    """Suspend l'organisation : ses comptes perdent l'accès à l'API dès la requête suivante."""
    motif = (motif or "").strip()
    if not motif:
        raise DjangoValidationError({"motif_suspension": "Le motif de suspension est obligatoire."})
    organisation.statut_habilitation = Organisation.StatutHabilitation.SUSPENDUE
    organisation.motif_suspension = motif
    organisation.save(update_fields=["statut_habilitation", "motif_suspension", "maj_le"])


def rehabiliter_organisation(organisation):
    """Rétablit l'habilitation et efface le motif de suspension."""
    organisation.statut_habilitation = Organisation.StatutHabilitation.HABILITEE
    organisation.motif_suspension = ""
    organisation.save(update_fields=["statut_habilitation", "motif_suspension", "maj_le"])
