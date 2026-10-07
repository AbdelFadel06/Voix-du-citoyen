import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from apps.accounts.models import Appareil, ServiceMunicipal, Utilisateur
from apps.accounts.services import generer_jetons
from apps.core.checks import bloquer_si_erreurs, verifier_backend_push
from apps.core.codes_erreur import CodeErreur
from apps.core.push import envoyer_push
from apps.core.push.backends.console import ConsolePush
from apps.core.push.backends.memoire import MemoirePush
from apps.notifications import services
from apps.notifications.models import Notification
from apps.realisations import services as realisations
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.suggestions import services as suggestions
from apps.territoire.models import Arrondissement, Quartier
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

URL_APPAREILS = reverse("notifications:appareils")
URL_NOTIFICATIONS = reverse("notifications:notifications")
JETON = "jeton-fcm-de-test-0001"


def url_lue(notification):
    return reverse("notifications:notification-lue", args=[notification.pk])


@pytest.fixture
def quartier(commune):
    arrondissement = Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")
    return Quartier.objects.create(arrondissement=arrondissement, nom="Togoudo", code="TOG")


@pytest.fixture
def secteur():
    return Secteur.objects.create(
        nom="Voirie", code="VOIRIE", pour_signalement=True, pour_suggestion=True, pour_realisation=True
    )


@pytest.fixture
def citoyen(creer_utilisateur, quartier):
    return creer_utilisateur(nom="Hounkpatin", prenoms="Afiavi")


@pytest.fixture
def agent(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.AGENT, service=ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie"))


@pytest.fixture
def appareil(citoyen):
    return Appareil.objects.create(utilisateur=citoyen, token_fcm=JETON, plateforme="ANDROID")


@pytest.fixture
def signalement(citoyen, secteur, quartier, televerser):
    dossier, _ = signalements.creer_signalement(
        auteur=citoyen, secteur=secteur, quartier=quartier, mode_localisation="MANUEL",
        medias_ids=[televerser(citoyen).id], titre="Trou", description_texte="Gros trou", repere="École",
    )
    return dossier


# ---------------------------------------------------------------------------
# Service push
# ---------------------------------------------------------------------------


class TestServicePush:
    def test_backend_configure(self):
        envoyer_push("abc", "Titre", "Message", {"cible_id": 4})
        assert MemoirePush.boite[0].donnees == {"cible_id": "4"}  # valeurs converties en texte

    def test_backend_console(self, caplog):
        caplog.set_level("INFO")
        ConsolePush().envoyer(JETON, "Votre signalement avance", "SIG-2026-00001 est en cours.", {"cible_id": "1"})
        assert "PUSH" in caplog.text and "SIG-2026-00001" in caplog.text

    def test_console_interdit_en_production(self, settings):
        settings.EST_PRODUCTION = True
        settings.PUSH_BACKEND = settings.PUSH_BACKEND_CONSOLE
        assert [e.id for e in verifier_backend_push(None)] == ["core.E002"]
        with pytest.raises(ImproperlyConfigured, match="core.E002"):
            bloquer_si_erreurs()

    def test_autre_backend_accepte_en_production(self, settings):
        settings.EST_PRODUCTION = True
        assert verifier_backend_push(None) == []


# ---------------------------------------------------------------------------
# Création et envoi
# ---------------------------------------------------------------------------


class TestEnvoi:
    def test_push_envoye_apres_validation(self, citoyen, appareil, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            (notification,) = services.notifier(
                [citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=7
            )
            assert MemoirePush.boite == []  # rien avant la validation de la transaction
        assert len(MemoirePush.boite) == 1
        push = MemoirePush.boite[0]
        assert (push.jeton, push.titre, push.message) == (JETON, "T", "M")
        assert push.donnees == {
            "notification_id": str(notification.pk), "type": "STATUT_SIGNALEMENT",
            "cible_type": "signalement", "cible_id": "7",
        }
        notification.refresh_from_db()
        assert notification.envoye_push

    def test_tous_les_appareils_actifs(self, citoyen, appareil, django_capture_on_commit_callbacks):
        Appareil.objects.create(utilisateur=citoyen, token_fcm="tablette", plateforme="IOS")
        Appareil.objects.create(utilisateur=citoyen, token_fcm="ancien", plateforme="IOS", actif=False)
        with django_capture_on_commit_callbacks(execute=True):
            services.notifier([citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=1)
        assert {p.jeton for p in MemoirePush.boite} == {JETON, "tablette"}

    def test_sans_appareil_la_notification_reste_consultable(self, citoyen, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            (notification,) = services.notifier([citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=1)
        notification.refresh_from_db()
        assert not notification.envoye_push and MemoirePush.boite == []

    def test_jeton_invalide_desactive_l_appareil(self, citoyen, appareil, django_capture_on_commit_callbacks):
        MemoirePush.jetons_invalides.add(JETON)
        with django_capture_on_commit_callbacks(execute=True):
            services.notifier([citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=1)
        appareil.refresh_from_db()
        assert not appareil.actif

    def test_echec_du_fournisseur_sans_consequence(self, citoyen, appareil, django_capture_on_commit_callbacks):
        MemoirePush.simuler_echec = True
        with django_capture_on_commit_callbacks(execute=True):
            (notification,) = services.notifier([citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=1)
        notification.refresh_from_db()
        appareil.refresh_from_db()
        assert not notification.envoye_push and appareil.actif

    def test_pas_de_doublon_de_destinataire(self, citoyen):
        assert len(services.notifier([citoyen, citoyen], type="STATUT_SIGNALEMENT", titre="T", message="M", cible_type="signalement", cible_id=1)) == 1


# ---------------------------------------------------------------------------
# Événements métier
# ---------------------------------------------------------------------------


class TestEvenements:
    def test_changement_de_statut_d_un_signalement(self, signalement, agent, citoyen, appareil, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            signalements.changer_statut(signalement, par=agent, statut="RECU")
        notification = Notification.objects.get()
        assert (notification.destinataire, notification.type) == (citoyen, "STATUT_SIGNALEMENT")
        assert notification.message == f"La mairie a bien reçu votre signalement {signalement.reference}."
        assert (notification.cible_type, notification.cible_id) == ("signalement", signalement.pk)
        assert MemoirePush.boite[0].titre == "Votre signalement avance"

    @pytest.mark.parametrize(
        "statut, attendu",
        [("RESOLU", "est résolu"), ("REJETE", "n'a pas été retenu : Terrain privé.")],
    )
    def test_messages_selon_le_statut(self, signalement, agent, statut, attendu):
        if statut == "RESOLU":
            signalements.changer_statut(signalement, par=agent, statut="RECU")
            signalements.changer_statut(signalement, par=agent, statut="EN_COURS")
        signalements.changer_statut(signalement, par=agent, statut=statut, commentaire="Terrain privé.")
        assert attendu in Notification.objects.order_by("-id").first().message

    def test_le_citoyen_anonyme_est_quand_meme_notifie(self, signalement, agent, citoyen):
        signalements.changer_statut(signalement, par=agent, statut="RECU")
        assert Notification.objects.get().destinataire == citoyen

    def test_reponse_a_un_signalement(self, signalement, agent):
        signalements.repondre(signalement, par=agent, commentaire="Les travaux commencent lundi.")
        notification = Notification.objects.get()
        assert notification.type == "REPONSE_SIGNALEMENT"
        assert "Les travaux commencent lundi." in notification.message

    def test_note_interne_jamais_notifiee(self, signalement, agent):
        signalements.repondre(signalement, par=agent, commentaire="Note", interne=True)
        assert not Notification.objects.exists()

    def test_assignation_non_notifiee(self, signalement, agent):
        signalements.assigner(signalement, par=agent, agent=agent)
        assert not Notification.objects.exists()

    def test_reponse_a_une_suggestion(self, citoyen, agent, secteur):
        suggestion = suggestions.creer_suggestion(auteur=citoyen, titre="Des bancs", description="D", secteur=secteur)
        suggestions.marquer_pertinente(suggestion)
        assert not Notification.objects.exists()  # la marque « pertinente » reste interne
        suggestions.repondre(suggestion, par=agent, commentaire="Prévu en 2027.")
        notification = Notification.objects.get()
        assert (notification.type, notification.cible_type, notification.cible_id) == ("REPONSE_SUGGESTION", "suggestion", suggestion.pk)
        assert notification.message == "« Des bancs » : Prévu en 2027."

    def test_publication_d_une_realisation(self, signalement, citoyen, agent, secteur, quartier, creer_utilisateur):
        habitant = creer_utilisateur(quartier_residence=quartier)
        ailleurs = creer_utilisateur(
            quartier_residence=Quartier.objects.create(arrondissement=quartier.arrondissement, nom="Ailleurs", code="AIL")
        )
        auteur_suggestion = creer_utilisateur()
        suggestion = suggestions.creer_suggestion(auteur=auteur_suggestion, titre="T", description="D", secteur=secteur)
        creer_utilisateur(role=Utilisateur.Role.AGENT, service=agent.service, quartier_residence=quartier)

        realisation = realisations.creer_realisation(
            par=agent, titre="Pavage de la rue", description="D", secteur=secteur,
            quartiers=[quartier], signalements=[signalement], suggestions=[suggestion],
        )
        assert not Notification.objects.exists()  # brouillon : personne n'est prévenu
        realisations.modifier_realisation(realisation, par=agent, publie=True)

        destinataires = set(Notification.objects.values_list("destinataire_id", flat=True))
        assert destinataires == {citoyen.pk, habitant.pk, auteur_suggestion.pk}
        assert ailleurs.pk not in destinataires
        assert set(Notification.objects.values_list("type", flat=True)) == {"NOUVELLE_REALISATION"}

        realisations.modifier_realisation(realisation, par=agent, titre="Nouveau titre")
        assert Notification.objects.count() == 3  # pas de nouvelle notification sans nouvelle publication


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class TestAppareils:
    def test_enregistrement(self, citoyen, client_connecte):
        reponse = client_connecte(citoyen).post(URL_APPAREILS, {"token_fcm": JETON, "plateforme": "ANDROID"}, format="json")
        assert reponse.status_code == 201
        assert reponse.json()["donnees"] == {"token_fcm": JETON, "plateforme": "ANDROID", "actif": True}
        assert Appareil.objects.get().utilisateur == citoyen

    def test_deja_connu_reactive(self, citoyen, appareil, client_connecte):
        Appareil.objects.filter(pk=appareil.pk).update(actif=False)
        reponse = client_connecte(citoyen).post(URL_APPAREILS, {"token_fcm": JETON, "plateforme": "ANDROID"}, format="json")
        assert reponse.status_code == 200
        appareil.refresh_from_db()
        assert appareil.actif and Appareil.objects.count() == 1

    def test_le_jeton_change_de_compte(self, appareil, creer_utilisateur, client_connecte):
        autre = creer_utilisateur()
        client_connecte(autre).post(URL_APPAREILS, {"token_fcm": JETON, "plateforme": "ANDROID"}, format="json")
        appareil.refresh_from_db()
        assert appareil.utilisateur == autre

    def test_plateforme_invalide(self, citoyen, client_connecte):
        reponse = client_connecte(citoyen).post(URL_APPAREILS, {"token_fcm": JETON, "plateforme": "WINDOWS"}, format="json")
        assert reponse.status_code == 400 and "plateforme" in reponse.json()["erreur"]["details"]

    def test_non_authentifie(self, api_client):
        assert api_client.post(URL_APPAREILS, {"token_fcm": JETON, "plateforme": "IOS"}, format="json").status_code == 401

    def test_deconnexion_desactive_l_appareil(self, citoyen, appareil, client_connecte):
        refresh = generer_jetons(citoyen)["refresh"]
        reponse = client_connecte(citoyen).post(
            reverse("accounts:logout"), {"refresh": refresh, "token_fcm": JETON}, format="json"
        )
        assert reponse.status_code == 204
        appareil.refresh_from_db()
        assert not appareil.actif


class TestNotifications:
    @pytest.fixture
    def mes_notifications(self, citoyen):
        return [
            services.notifier([citoyen], type="STATUT_SIGNALEMENT", titre=f"T{i}", message="M", cible_type="signalement", cible_id=i)[0]
            for i in range(3)
        ]

    def test_liste_de_mes_notifications(self, mes_notifications, citoyen, creer_utilisateur, client_connecte):
        services.notifier([creer_utilisateur()], type="STATUT_SIGNALEMENT", titre="Autre", message="M", cible_type="signalement", cible_id=9)
        corps = client_connecte(citoyen).get(URL_NOTIFICATIONS).json()
        assert [n["titre"] for n in corps["donnees"]] == ["T2", "T1", "T0"]
        assert corps["pagination"]["total"] == 3

    def test_filtre_non_lues(self, mes_notifications, citoyen, client_connecte):
        services.marquer_lue(mes_notifications[0])
        corps = client_connecte(citoyen).get(URL_NOTIFICATIONS, {"lu": "false"}).json()
        assert corps["pagination"]["total"] == 2

    def test_marquer_une_lue(self, mes_notifications, citoyen, client_connecte):
        client = client_connecte(citoyen)
        for _ in range(2):  # sans effet la deuxième fois
            reponse = client.patch(url_lue(mes_notifications[0]))
            assert reponse.status_code == 200 and reponse.json()["donnees"]["lu"] is True
        assert Notification.objects.filter(lu=True).count() == 1

    def test_notification_d_un_autre_introuvable(self, mes_notifications, creer_utilisateur, client_connecte):
        reponse = client_connecte(creer_utilisateur()).patch(url_lue(mes_notifications[0]))
        assert reponse.status_code == 404
        assert reponse.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE

    def test_tout_marquer_lu(self, mes_notifications, citoyen, client_connecte):
        services.marquer_lue(mes_notifications[0])
        reponse = client_connecte(citoyen).patch(URL_NOTIFICATIONS)
        assert reponse.json()["donnees"] == {"nb_marquees": 2}
        assert not Notification.objects.filter(lu=False).exists()

    def test_non_authentifie(self, api_client):
        assert api_client.get(URL_NOTIFICATIONS).status_code == 401
