from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CodeOTP, Organisation, Utilisateur
from apps.accounts.services import suspendre_organisation
from apps.core.codes_erreur import CodeErreur
from apps.territoire.models import Arrondissement, Quartier
from conftest import MOT_DE_PASSE, commune_de_test

pytestmark = pytest.mark.django_db

URL_REGISTER = reverse("accounts:register")
URL_VERIFY = reverse("accounts:otp-verify")
URL_RESEND = reverse("accounts:otp-resend")
URL_LOGIN = reverse("accounts:login")
URL_REFRESH = reverse("accounts:refresh")
URL_LOGOUT = reverse("accounts:logout")
URL_ME = reverse("accounts:me")

TELEPHONE = "+2290197123456"


def donnees_inscription(**surcharges):
    return {
        "commune": commune_de_test().pk,
        "telephone": "0197123456",
        "nom": "Hounkpatin",
        "prenoms": "Afiavi",
        "password": MOT_DE_PASSE,
        **surcharges,
    }


def donnees(reponse):
    corps = reponse.json()
    assert corps["succes"] is True, corps
    return corps["donnees"]


def erreur(reponse, code=None):
    corps = reponse.json()
    assert corps["succes"] is False, corps
    if code is not None:
        assert corps["erreur"]["code"] == code, corps
    return corps["erreur"]


def faux_code(code):
    return "000000" if code != "000000" else "111111"


@pytest.fixture
def quartier():
    arrondissement = Arrondissement.objects.create(commune=commune_de_test(), nom="Godomey", code="GOD")
    return Quartier.objects.create(arrondissement=arrondissement, nom="Togoudo", code="TOG")


@pytest.fixture
def inscrit(api_client, sms):
    """Un citoyen inscrit, pas encore vérifié. Renvoie le code reçu."""
    api_client.post(URL_REGISTER, donnees_inscription(), format="json")
    return sms.dernier_code()


# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------


class TestInscription:
    def test_cree_un_citoyen_non_verifie_et_envoie_un_code(self, api_client, sms):
        reponse = api_client.post(URL_REGISTER, donnees_inscription(), format="json")

        assert reponse.status_code == 201
        assert reponse.json()["message"].startswith("Compte créé.")
        assert donnees(reponse) == {"telephone": TELEPHONE}
        utilisateur = Utilisateur.objects.get(telephone=TELEPHONE)
        assert utilisateur.role == Utilisateur.Role.CITOYEN
        assert not utilisateur.telephone_verifie
        assert utilisateur.email is None
        assert len(sms) == 1 and sms[0].telephone == TELEPHONE

    def test_texte_du_sms(self, inscrit, sms):
        assert sms[0].message == (
            f"Voix du Citoyen : votre code de vérification est {inscrit}. "
            "Il expire dans 10 minutes. Ne le partagez avec personne."
        )

    def test_le_code_n_apparait_ni_en_base_ni_dans_la_reponse_ni_dans_les_logs(
        self, api_client, sms, caplog
    ):
        caplog.set_level("DEBUG")
        reponse = api_client.post(URL_REGISTER, donnees_inscription(), format="json")
        code = sms.dernier_code()

        assert code not in reponse.content.decode()
        assert code not in caplog.text
        otp = CodeOTP.objects.get()
        assert code not in otp.code_hash
        assert otp.motif == CodeOTP.Motif.INSCRIPTION
        assert otp.expire_le > timezone.now() + timedelta(minutes=9)

    def test_avec_email_et_quartier(self, api_client, sms, quartier):
        reponse = api_client.post(
            URL_REGISTER,
            donnees_inscription(email="Afiavi@Exemple.BJ", quartier_residence=quartier.pk),
            format="json",
        )
        assert reponse.status_code == 201
        utilisateur = Utilisateur.objects.get(telephone=TELEPHONE)
        assert utilisateur.email == "afiavi@exemple.bj"
        assert utilisateur.quartier_residence == quartier

    @pytest.mark.parametrize("champ", ["telephone", "nom", "prenoms", "password"])
    def test_champs_obligatoires(self, api_client, sms, champ):
        corps = donnees_inscription()
        del corps[champ]
        reponse = api_client.post(URL_REGISTER, corps, format="json")
        assert reponse.status_code == 400
        assert champ in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_refuse_un_numero_non_beninois(self, api_client, sms):
        reponse = api_client.post(
            URL_REGISTER, donnees_inscription(telephone="+33612345678"), format="json"
        )
        assert reponse.status_code == 400
        assert "béninois" in erreur(reponse)["details"]["telephone"][0]

    def test_refuse_un_numero_invalide(self, api_client, sms):
        reponse = api_client.post(URL_REGISTER, donnees_inscription(telephone="123"), format="json")
        assert reponse.status_code == 400
        assert "telephone" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_refuse_un_mot_de_passe_faible(self, api_client, sms):
        reponse = api_client.post(URL_REGISTER, donnees_inscription(password="1234"), format="json")
        assert reponse.status_code == 400
        assert "password" in erreur(reponse)["details"]
        assert not Utilisateur.objects.exists()

    def test_refuse_un_numero_deja_verifie(self, api_client, sms, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        reponse = api_client.post(URL_REGISTER, donnees_inscription(), format="json")
        assert reponse.status_code == 409
        details = erreur(reponse, CodeErreur.TELEPHONE_DEJA_UTILISE)["details"]
        assert "telephone" in details
        assert len(sms) == 0

    def test_refuse_le_numero_d_un_agent(self, api_client, sms, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, telephone=TELEPHONE, telephone_verifie=False)
        reponse = api_client.post(URL_REGISTER, donnees_inscription(), format="json")
        assert reponse.status_code == 409

    def test_reprend_une_inscription_non_verifiee(self, api_client, sms, inscrit):
        reponse = api_client.post(URL_REGISTER, donnees_inscription(nom="Corrigé"), format="json")
        assert reponse.status_code == 201
        assert Utilisateur.objects.get().nom == "Corrigé"
        # L'ancien code est remplacé par le nouveau.
        assert CodeOTP.objects.count() == 1
        assert len(sms) == 2

    def test_echec_du_fournisseur_sms(self, api_client, sms):
        sms.simuler_echec()
        reponse = api_client.post(URL_REGISTER, donnees_inscription(), format="json")
        assert reponse.status_code == 503
        erreur(reponse, CodeErreur.SMS_ECHEC)


# ---------------------------------------------------------------------------
# Vérification OTP
# ---------------------------------------------------------------------------


class TestVerificationOTP:
    def test_bon_code_verifie_le_numero_et_connecte(self, api_client, inscrit):
        reponse = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")

        assert reponse.status_code == 200
        corps = donnees(reponse)
        assert {"access", "refresh", "utilisateur"} <= corps.keys()
        assert corps["utilisateur"]["telephone_verifie"] is True
        assert Utilisateur.objects.get().telephone_verifie
        assert CodeOTP.objects.get().utilise

    def test_code_deja_utilise_refuse(self, api_client, inscrit):
        api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")
        reponse = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")
        assert reponse.status_code == 400
        erreur(reponse, CodeErreur.OTP_EXPIRE)

    def test_mauvais_code_compte_les_tentatives(self, api_client, inscrit):
        reponse = api_client.post(
            URL_VERIFY, {"telephone": TELEPHONE, "code": faux_code(inscrit)}, format="json"
        )

        assert reponse.status_code == 400
        details = erreur(reponse, CodeErreur.OTP_INVALIDE)
        assert details["details"] == {"tentatives_restantes": 4}
        assert "4 essais" in details["message"]
        assert CodeOTP.objects.get().tentatives == 1

    def test_bloque_apres_cinq_echecs_meme_avec_le_bon_code(self, api_client, inscrit):
        for _ in range(CodeOTP.TENTATIVES_MAX - 1):
            api_client.post(
                URL_VERIFY, {"telephone": TELEPHONE, "code": faux_code(inscrit)}, format="json"
            )
        cinquieme = api_client.post(
            URL_VERIFY, {"telephone": TELEPHONE, "code": faux_code(inscrit)}, format="json"
        )
        assert cinquieme.status_code == 429
        erreur(cinquieme, CodeErreur.OTP_TENTATIVES_DEPASSEES)

        reponse = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")
        assert reponse.status_code == 429
        erreur(reponse, CodeErreur.OTP_TENTATIVES_DEPASSEES)
        assert not Utilisateur.objects.get().telephone_verifie

    def test_code_expire_refuse(self, api_client, inscrit):
        CodeOTP.objects.update(expire_le=timezone.now() - timedelta(seconds=1))
        reponse = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")
        assert reponse.status_code == 400
        erreur(reponse, CodeErreur.OTP_EXPIRE)

    def test_format_du_code(self, api_client, inscrit):
        reponse = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": "12ab"}, format="json")
        assert reponse.status_code == 400
        assert "6 chiffres" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]["code"][0]


class TestRenvoiOTP:
    def test_renvoie_un_nouveau_code_et_invalide_l_ancien(self, api_client, sms, inscrit):
        reponse = api_client.post(URL_RESEND, {"telephone": TELEPHONE}, format="json")

        assert reponse.status_code == 200
        assert reponse.json()["donnees"] is None
        assert len(sms) == 2
        assert CodeOTP.objects.count() == 1
        nouveau = sms.dernier_code()
        if nouveau != inscrit:
            ancien = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": inscrit}, format="json")
            assert ancien.status_code == 400
        ok = api_client.post(URL_VERIFY, {"telephone": TELEPHONE, "code": nouveau}, format="json")
        assert ok.status_code == 200

    def test_numero_inconnu_meme_reponse_sans_sms(self, api_client, sms):
        reponse = api_client.post(URL_RESEND, {"telephone": TELEPHONE}, format="json")
        assert reponse.status_code == 200
        assert len(sms) == 0

    def test_numero_deja_verifie_sans_sms(self, api_client, sms, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        api_client.post(URL_RESEND, {"telephone": TELEPHONE}, format="json")
        assert len(sms) == 0


class TestThrottlingOTP:
    def test_limite_a_cinq_demandes_par_heure_et_par_numero(self, api_client, sms, inscrit):
        # 1 inscription (fixture) + 4 renvois = 5 demandes autorisées.
        for _ in range(4):
            assert api_client.post(URL_RESEND, {"telephone": TELEPHONE}, format="json").status_code == 200
        reponse = api_client.post(URL_RESEND, {"telephone": "0197123456"}, format="json")

        assert reponse.status_code == 429
        details = erreur(reponse, CodeErreur.TROP_DE_REQUETES)["details"]
        assert 0 < details["attente_secondes"] <= 3600
        assert reponse["Retry-After"] == str(details["attente_secondes"])

    def test_la_limite_est_propre_a_chaque_numero(self, api_client, sms, inscrit):
        for _ in range(4):
            api_client.post(URL_RESEND, {"telephone": TELEPHONE}, format="json")
        autre = api_client.post(URL_RESEND, {"telephone": "+2290197999999"}, format="json")
        assert autre.status_code == 200


# ---------------------------------------------------------------------------
# Connexion, rafraîchissement, déconnexion
# ---------------------------------------------------------------------------


def connexion(client, telephone, password=MOT_DE_PASSE):
    return client.post(URL_LOGIN, {"telephone": telephone, "password": password}, format="json")


def connexion_email(client, email, password=MOT_DE_PASSE):
    return client.post(URL_LOGIN, {"email": email, "password": password}, format="json")


class TestConnexion:
    def test_renvoie_les_jetons_et_le_profil(self, api_client, creer_utilisateur):
        utilisateur = creer_utilisateur(telephone=TELEPHONE)
        reponse = connexion(api_client, TELEPHONE)

        assert reponse.status_code == 200
        assert reponse.json()["message"] == "Connexion réussie."
        assert donnees(reponse)["utilisateur"]["id"] == utilisateur.pk
        assert donnees(reponse)["utilisateur"]["role"] == "CITOYEN"
        utilisateur.refresh_from_db()
        assert utilisateur.last_login is not None

    def test_accepte_le_format_national(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        assert connexion(api_client, "0197123456").status_code == 200

    def test_mauvais_mot_de_passe(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        reponse = connexion(api_client, TELEPHONE, "mauvais")
        assert reponse.status_code == 401
        erreur(reponse, CodeErreur.IDENTIFIANTS_INVALIDES)

    def test_numero_inconnu(self, api_client, db):
        reponse = connexion(api_client, TELEPHONE)
        assert reponse.status_code == 401
        erreur(reponse, CodeErreur.IDENTIFIANTS_INVALIDES)

    def test_compte_desactive(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE, is_active=False)
        reponse = connexion(api_client, TELEPHONE)
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.COMPTE_DESACTIVE)

    def test_compte_desactive_avec_mauvais_mot_de_passe_ne_revele_rien(
        self, api_client, creer_utilisateur
    ):
        creer_utilisateur(telephone=TELEPHONE, is_active=False)
        erreur(connexion(api_client, TELEPHONE, "mauvais"), CodeErreur.IDENTIFIANTS_INVALIDES)

    def test_citoyen_non_verifie_refuse(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE, telephone_verifie=False)
        reponse = connexion(api_client, TELEPHONE)
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.TELEPHONE_NON_VERIFIE)

    def test_agent_cree_par_l_admin_n_a_pas_besoin_d_otp(self, api_client, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, email="agent@mairie.bj", telephone_verifie=False)
        assert connexion_email(api_client, "agent@mairie.bj").status_code == 200

    def test_organisation_suspendue_refusee(self, api_client, creer_utilisateur):
        compte = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, email="ong@exemple.bj")
        suspendre_organisation(compte.organisation, "Rapport annuel non fourni")
        reponse = connexion_email(api_client, "ong@exemple.bj")
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.ORGANISATION_NON_HABILITEE)

    def test_organisation_expiree_refusee(self, api_client, creer_utilisateur):
        compte = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, email="ong@exemple.bj")
        Organisation.objects.filter(pk=compte.organisation_id).update(
            date_expiration=timezone.localdate() - timedelta(days=1)
        )
        assert connexion_email(api_client, "ong@exemple.bj").status_code == 403

    def test_organisation_habilitee_acceptee(self, api_client, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.ORGANISATION, email="ong@exemple.bj")
        assert connexion_email(api_client, "ong@exemple.bj").status_code == 200


class TestConnexionParEmail:
    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE, Utilisateur.Role.ORGANISATION])
    def test_le_personnel_se_connecte_par_email(self, api_client, creer_utilisateur, role):
        compte = creer_utilisateur(role=role, email="Rodrigue.Ahouansou@Mairie-Parakou.bj")
        reponse = connexion_email(api_client, "  rodrigue.ahouansou@mairie-parakou.BJ ")
        assert reponse.status_code == 200, reponse.json()
        assert donnees(reponse)["utilisateur"]["id"] == compte.pk

    def test_le_personnel_ne_se_connecte_pas_par_telephone(self, api_client, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, telephone=TELEPHONE)
        reponse = connexion(api_client, TELEPHONE)
        assert reponse.status_code == 400
        erreur(reponse, CodeErreur.CONNEXION_PAR_EMAIL)

    def test_le_citoyen_ne_se_connecte_pas_par_email(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE, email="afiavi@exemple.bj")
        reponse = connexion_email(api_client, "afiavi@exemple.bj")
        assert reponse.status_code == 400
        erreur(reponse, CodeErreur.CONNEXION_PAR_TELEPHONE)

    def test_mauvaise_methode_et_mauvais_mot_de_passe_ne_revelent_rien(self, api_client, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, telephone=TELEPHONE, email="agent@mairie.bj")
        erreur(connexion(api_client, TELEPHONE, "mauvais"), CodeErreur.IDENTIFIANTS_INVALIDES)
        erreur(connexion_email(api_client, "agent@mairie.bj", "mauvais"), CodeErreur.IDENTIFIANTS_INVALIDES)
        erreur(connexion_email(api_client, "inconnu@mairie.bj"), CodeErreur.IDENTIFIANTS_INVALIDES)

    def test_compte_du_personnel_desactive(self, api_client, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, email="agent@mairie.bj", is_active=False)
        reponse = connexion_email(api_client, "agent@mairie.bj")
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.COMPTE_DESACTIVE)

    @pytest.mark.parametrize(
        "corps",
        [
            {"password": MOT_DE_PASSE},
            {"telephone": TELEPHONE, "email": "agent@mairie.bj", "password": MOT_DE_PASSE},
        ],
    )
    def test_un_seul_identifiant(self, api_client, db, corps):
        reponse = api_client.post(URL_LOGIN, corps, format="json")
        assert "identifiant" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_inscription_avec_un_email_deja_pris(self, api_client, sms, creer_utilisateur):
        creer_utilisateur(role=Utilisateur.Role.AGENT, email="agent@mairie.bj")
        reponse = api_client.post(URL_REGISTER, donnees_inscription(email="AGENT@mairie.bj"), format="json")
        assert reponse.status_code == 409
        erreur(reponse, CodeErreur.EMAIL_DEJA_UTILISE)

    def test_le_personnel_ne_peut_pas_effacer_son_email(self, creer_utilisateur, client_connecte):
        client = client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT))
        reponse = client.patch(URL_ME, {"email": ""}, format="json")
        assert "email" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_email_du_profil_unique(self, creer_utilisateur, client_connecte):
        creer_utilisateur(role=Utilisateur.Role.AGENT, email="agent@mairie.bj")
        reponse = client_connecte(creer_utilisateur()).patch(URL_ME, {"email": "Agent@Mairie.bj"}, format="json")
        assert "email" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]


class TestJetons:
    def test_jeton_d_une_organisation_suspendue_ensuite_refuse(
        self, creer_utilisateur, client_connecte
    ):
        compte = creer_utilisateur(role=Utilisateur.Role.ORGANISATION)
        client = client_connecte(compte)
        assert client.get(URL_ME).status_code == 200

        suspendre_organisation(compte.organisation, "Rapport annuel non fourni")
        reponse = client.get(URL_ME)
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.ORGANISATION_NON_HABILITEE)

    def test_jeton_d_un_compte_desactive_refuse(self, creer_utilisateur, client_connecte):
        utilisateur = creer_utilisateur()
        client = client_connecte(utilisateur)
        Utilisateur.objects.filter(pk=utilisateur.pk).update(is_active=False)
        reponse = client.get(URL_ME)
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.COMPTE_DESACTIVE)

    def test_jeton_invalide(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer nimporte.quoi.ici")
        reponse = api_client.get(URL_ME)
        assert reponse.status_code == 401
        erreur(reponse, CodeErreur.JETON_INVALIDE)

    def test_rafraichissement_avec_rotation(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        refresh = donnees(connexion(api_client, TELEPHONE))["refresh"]

        reponse = api_client.post(URL_REFRESH, {"refresh": refresh}, format="json")
        assert reponse.status_code == 200
        assert {"access", "refresh"} <= donnees(reponse).keys()
        # L'ancien jeton de rafraîchissement est désormais inutilisable.
        rejoue = api_client.post(URL_REFRESH, {"refresh": refresh}, format="json")
        assert rejoue.status_code == 401
        erreur(rejoue, CodeErreur.JETON_INVALIDE)

    def test_deconnexion_invalide_le_jeton(self, api_client, creer_utilisateur):
        creer_utilisateur(telephone=TELEPHONE)
        jetons = donnees(connexion(api_client, TELEPHONE))
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {jetons['access']}")

        reponse = api_client.post(URL_LOGOUT, {"refresh": jetons["refresh"]}, format="json")
        assert reponse.status_code == 204
        assert reponse.content == b""
        assert (
            api_client.post(URL_REFRESH, {"refresh": jetons["refresh"]}, format="json").status_code
            == 401
        )

    def test_deconnexion_avec_le_jeton_d_un_autre(self, api_client, creer_utilisateur, client_connecte):
        creer_utilisateur(telephone=TELEPHONE)
        refresh_autre = donnees(connexion(api_client, TELEPHONE))["refresh"]
        moi = client_connecte(creer_utilisateur())

        reponse = moi.post(URL_LOGOUT, {"refresh": refresh_autre}, format="json")
        assert reponse.status_code == 403
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE)
        assert api_client.post(URL_REFRESH, {"refresh": refresh_autre}, format="json").status_code == 200

    def test_deconnexion_sans_authentification(self, api_client):
        reponse = api_client.post(URL_LOGOUT, {"refresh": "x"}, format="json")
        assert reponse.status_code == 401
        erreur(reponse, CodeErreur.NON_AUTHENTIFIE)


# ---------------------------------------------------------------------------
# Profil /auth/me/
# ---------------------------------------------------------------------------


class TestProfil:
    def test_non_authentifie(self, api_client):
        reponse = api_client.get(URL_ME)
        assert reponse.status_code == 401
        erreur(reponse, CodeErreur.NON_AUTHENTIFIE)

    def test_lecture(self, creer_utilisateur, client_connecte):
        utilisateur = creer_utilisateur(role=Utilisateur.Role.AGENT)
        reponse = client_connecte(utilisateur).get(URL_ME)
        assert reponse.json()["message"] is None
        corps = donnees(reponse)
        assert corps["telephone"] == str(utilisateur.telephone)
        assert corps["role"] == "AGENT"
        assert corps["service"] == {"id": utilisateur.service_id, "nom": "Voirie"}
        assert corps["organisation"] is None

    def test_modification_identite_et_quartier(self, creer_utilisateur, client_connecte, quartier):
        utilisateur = creer_utilisateur()
        reponse = client_connecte(utilisateur).patch(
            URL_ME,
            {"nom": "Nouveau", "email": "", "quartier_residence": quartier.pk},
            format="json",
        )
        assert reponse.status_code == 200
        assert reponse.json()["message"] == "Votre profil a été mis à jour."
        assert donnees(reponse)["nom"] == "Nouveau"
        utilisateur.refresh_from_db()
        assert utilisateur.nom == "Nouveau"
        assert utilisateur.email is None
        assert utilisateur.quartier_residence == quartier

    def test_role_et_telephone_non_modifiables(self, creer_utilisateur, client_connecte):
        utilisateur = creer_utilisateur()
        telephone = str(utilisateur.telephone)
        client_connecte(utilisateur).patch(
            URL_ME, {"role": "ADMIN_MAIRIE", "telephone": "+2290197999999"}, format="json"
        )
        utilisateur.refresh_from_db()
        assert utilisateur.role == Utilisateur.Role.CITOYEN
        assert str(utilisateur.telephone) == telephone

    def test_nom_vide_refuse(self, creer_utilisateur, client_connecte):
        reponse = client_connecte(creer_utilisateur()).patch(URL_ME, {"nom": "  "}, format="json")
        assert reponse.status_code == 400
        assert "nom" in erreur(reponse, CodeErreur.VALIDATION_ERREUR)["details"]

    def test_quartier_inactif_refuse(self, creer_utilisateur, client_connecte, quartier):
        Quartier.objects.filter(pk=quartier.pk).update(actif=False)
        reponse = client_connecte(creer_utilisateur()).patch(
            URL_ME, {"quartier_residence": quartier.pk}, format="json"
        )
        assert reponse.status_code == 400

    def test_put_non_autorise(self, creer_utilisateur, client_connecte):
        reponse = client_connecte(creer_utilisateur()).put(URL_ME, {}, format="json")
        assert reponse.status_code == 405
        erreur(reponse, CodeErreur.METHODE_NON_AUTORISEE)
