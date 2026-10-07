import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.import_csv import ImportRefuse, executer, lire_csv
from apps.core.sms import EnvoiSMSEchoue, envoyer_sms

from .models import CodeOTP, Organisation, ServiceMunicipal, Utilisateur, normaliser_email

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


def inscrire_citoyen(*, telephone, nom, prenoms, password, commune, email=None, quartier_residence=None):
    """
    Crée un compte citoyen non vérifié et envoie un code OTP.
    Un compte citoyen jamais vérifié peut être repris (ex. erreur de saisie, SMS non reçu),
    car il n'a encore donné accès à rien.
    """
    email = normaliser_email(email)
    try:
        with transaction.atomic():
            existant = Utilisateur.objects.select_for_update().filter(telephone=telephone).first()
            controler_email_disponible(email, sauf=existant)
            if existant is not None:
                if existant.role != Role.CITOYEN or existant.telephone_verifie:
                    raise _erreur_telephone_deja_utilise()
                utilisateur = existant
                utilisateur.nom = nom
                utilisateur.prenoms = prenoms
                utilisateur.email = email
                utilisateur.commune = commune
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
                    commune=commune,
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


def _verifier_mot_de_passe(candidat, password):
    """Vrai si le mot de passe correspond ; sans compte, le calcul est fait quand même (même durée)."""
    if candidat is None:
        Utilisateur().set_password(password)
        return False
    return candidat.check_password(password)


def connecter(password, telephone=None, email=None):
    """
    Citoyens : téléphone + mot de passe. Mairie et organisations : e-mail + mot de passe.
    Une erreur de méthode n'est signalée qu'à qui donne le bon mot de passe.
    """
    if email:
        candidat = Utilisateur.objects.filter(email__iexact=normaliser_email(email)).first()
    else:
        candidat = Utilisateur.objects.filter(telephone=telephone).first()
    if not _verifier_mot_de_passe(candidat, password):
        raise ErreurMetier(CodeErreur.IDENTIFIANTS_INVALIDES)

    par_email = candidat.role in Utilisateur.ROLES_CONNEXION_EMAIL
    if email and not par_email:
        raise ErreurMetier(CodeErreur.CONNEXION_PAR_TELEPHONE)
    if not email and par_email:
        raise ErreurMetier(CodeErreur.CONNEXION_PAR_EMAIL)
    if not candidat.is_active:
        raise ErreurMetier(CodeErreur.COMPTE_DESACTIVE)
    utilisateur = candidat
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
# Mot de passe oublié
# ---------------------------------------------------------------------------


def _compte_a_reinitialiser(telephone=None, email=None):
    """
    Compte actif identifié comme à la connexion (citoyen vérifié par son téléphone, mairie et
    organisations par leur e-mail), ou None. Ne jamais dire à l'appelant pourquoi.
    """
    if email:
        compte = Utilisateur.objects.filter(email__iexact=normaliser_email(email)).first()
        valide = compte is not None and compte.role in Utilisateur.ROLES_CONNEXION_EMAIL
    else:
        compte = Utilisateur.objects.filter(telephone=telephone).first()
        valide = compte is not None and compte.role == Role.CITOYEN and compte.telephone_verifie
    return compte if valide and compte.is_active else None


def demander_reinitialisation(telephone=None, email=None):
    """
    Envoie un code par SMS au numéro du compte. Sans effet (et sans le signaler) si aucun
    compte ne correspond, pour ne pas révéler qui est inscrit.
    """
    compte = _compte_a_reinitialiser(telephone, email)
    if compte is not None:
        generer_code_otp(compte, CodeOTP.Motif.REINITIALISATION_MDP)


def _valider_nouveau_mot_de_passe(password, compte):
    try:
        validate_password(password, user=compte)
    except DjangoValidationError as exc:
        raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details={"password": list(exc.messages)})


def reinitialiser_mot_de_passe(*, code, password, telephone=None, email=None):
    """
    Remplace le mot de passe après contrôle du code, puis déconnecte toutes les sessions
    (jetons `refresh` invalidés). Le mot de passe est contrôlé avant le code, pour que
    le citoyen puisse corriger sa saisie sans redemander de code.
    """
    compte = _compte_a_reinitialiser(telephone, email)
    _valider_nouveau_mot_de_passe(password, compte)
    if compte is None:
        raise ErreurMetier(CodeErreur.OTP_EXPIRE)
    # Hors transaction : chaque essai raté doit rester compté.
    _verifier_code_otp(compte, CodeOTP.Motif.REINITIALISATION_MDP, code)
    with transaction.atomic():
        compte.set_password(password)
        compte.save(update_fields=["password", "maj_le"])
        for jeton in OutstandingToken.objects.filter(user=compte).exclude(blacklistedtoken__isnull=False):
            BlacklistedToken.objects.get_or_create(token=jeton)
    return compte


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


# ---------------------------------------------------------------------------
# Import CSV des services municipaux (`charger_services`, `POST /services/import/`)
# ---------------------------------------------------------------------------


def importer_services(texte, commune, *, simulation=False, desactiver_absents=False):
    """
    Crée ou met à jour les services municipaux depuis le texte d'un CSV (`nom` obligatoire,
    `description` facultative), reconnus par leur nom. Renvoie le bilan ou lève ImportRefuse.
    """
    lignes, colonnes = lire_csv(texte, ["nom"], ["description"])
    erreurs, services, noms_vus = [], [], {}
    for numero, ligne in lignes:
        nom = ligne["nom"]
        if not nom:
            erreurs.append(f"Ligne {numero} : « nom » est vide.")
        elif nom.casefold() in noms_vus:
            erreurs.append(f"Ligne {numero} : le service « {nom} » apparaît déjà ligne {noms_vus[nom.casefold()]}.")
        noms_vus.setdefault(nom.casefold(), numero)
        services.append(ligne)
    if erreurs:
        raise ImportRefuse(erreurs)

    def enregistrer():
        existants = {s.nom.casefold(): s for s in ServiceMunicipal.objects.filter(commune=commune)}
        bilan = {"crees": 0, "mis_a_jour": 0, "desactives": 0}
        vus = set()
        for ligne in services:
            service = existants.get(ligne["nom"].casefold()) or ServiceMunicipal(nom=ligne["nom"], commune=commune)
            bilan["mis_a_jour" if service.pk else "crees"] += 1
            if "description" in colonnes:
                service.description = ligne["description"]
            service.actif = True
            service.save()
            vus.add(service.pk)
        if desactiver_absents:
            bilan["desactives"] = (
                ServiceMunicipal.objects.filter(commune=commune, actif=True).exclude(pk__in=vus).update(actif=False)
            )
        return bilan

    return executer(enregistrer, simulation)


# ---------------------------------------------------------------------------
# Comptes du personnel de la mairie (`/agents/`, admins mairie)
# ---------------------------------------------------------------------------


def _controler_agent(role, service, commune):
    if role == Role.AGENT and service is None:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR, details={"service": ["Un agent doit être rattaché à un service municipal."]}
        )
    if role == Role.AGENT and commune is None:
        raise ErreurMetier(CodeErreur.VALIDATION_ERREUR, details={"commune": ["Indiquez la commune de la mairie."]})
    if service is not None and commune is not None and service.commune_id != commune.pk:
        raise ErreurMetier(
            CodeErreur.VALIDATION_ERREUR,
            details={"service": [f"Ce service n'appartient pas à la mairie de {commune.nom}."]},
        )


@transaction.atomic
def controler_email_disponible(email, sauf=None):
    """Lève EMAIL_DEJA_UTILISE si l'adresse appartient déjà à un autre compte."""
    autres = Utilisateur.objects.filter(email__iexact=normaliser_email(email))
    if sauf is not None:
        autres = autres.exclude(pk=sauf.pk)
    if email and autres.exists():
        raise ErreurMetier(
            CodeErreur.EMAIL_DEJA_UTILISE, details={"email": ["Cette adresse e-mail est déjà utilisée."]}
        )


@transaction.atomic
def creer_agent(*, telephone, nom, prenoms, role, mot_de_passe, email, commune, service=None):
    """
    Crée le compte d'un agent ou d'un admin mairie, qui se connectera avec son e-mail
    (sans code SMS : la mairie se porte garante de la personne).
    """
    _controler_agent(role, service, commune)
    if Utilisateur.objects.filter(telephone=telephone).exists():
        raise _erreur_telephone_deja_utilise()
    controler_email_disponible(email)
    return Utilisateur.objects.create_user(
        telephone,
        password=mot_de_passe,
        nom=nom,
        prenoms=prenoms,
        email=email,
        role=role,
        service=service,
        commune=commune,
    )


@transaction.atomic
def modifier_agent(agent, *, par, mot_de_passe=None, **changements):
    """
    Modification partielle d'un compte du personnel. Un admin ne peut ni se désactiver ni
    retirer son propre rôle d'administrateur (il pourrait ne plus rester aucun admin).
    """
    actif = changements.pop("actif", None)
    if agent.pk == par.pk and (actif is False or changements.get("role", agent.role) != agent.role):
        raise ErreurMetier(CodeErreur.ACTION_SUR_SON_PROPRE_COMPTE)
    if "email" in changements:
        changements["email"] = normaliser_email(changements["email"])
        if not changements["email"]:
            raise ErreurMetier(
                CodeErreur.VALIDATION_ERREUR,
                details={"email": ["L'adresse e-mail est obligatoire : elle sert à se connecter."]},
            )
        controler_email_disponible(changements["email"], sauf=agent)
    for champ, valeur in changements.items():
        setattr(agent, champ, valeur)
    if actif is not None:
        agent.is_active = actif
    _controler_agent(agent.role, agent.service, agent.commune)
    if mot_de_passe:
        agent.set_password(mot_de_passe)
    agent.save()
    return agent
