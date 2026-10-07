import pytest
from django.urls import reverse

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.signalements import services
from apps.signalements.models import Signalement, SuiviSignalement

pytestmark = pytest.mark.django_db

Statut = Signalement.Statut


def url(signalement, action):
    return reverse(f"signalements:signalement-{action}", args=[signalement.pk])


@pytest.fixture
def signalement(creer_signalement, citoyen):
    return creer_signalement(citoyen)


@pytest.fixture
def mairie(agent, client_connecte):
    return client_connecte(agent)


def poster(client, signalement, action, corps):
    return client.post(url(signalement, action), corps, format="json")


def ok(reponse, statut=200):
    assert reponse.status_code == statut, reponse.json()
    return reponse.json()


def erreur(reponse, code, statut):
    assert reponse.status_code == statut, reponse.json()
    assert reponse.json()["erreur"]["code"] == code, reponse.json()
    return reponse.json()["erreur"]


class TestChangementDeStatut:
    def test_cycle_complet(self, mairie, signalement, agent):
        for statut in ("RECU", "EN_COURS", "RESOLU"):
            corps = ok(poster(mairie, signalement, "changer-statut", {"statut": statut, "commentaire": f"Passage {statut}"}))
            assert corps["donnees"]["statut"] == statut
        assert corps["message"] == "Statut mis à jour : Résolu."
        signalement.refresh_from_db()
        assert signalement.date_resolution is not None
        suivis = SuiviSignalement.objects.filter(signalement=signalement, auteur=agent)
        assert [(s.ancien_statut, s.nouveau_statut) for s in suivis] == [
            ("SOUMIS", "RECU"), ("RECU", "EN_COURS"), ("EN_COURS", "RESOLU"),
        ]
        assert all(s.visible_citoyen for s in suivis)

    def test_transition_impossible(self, mairie, signalement):
        corps = erreur(
            poster(mairie, signalement, "changer-statut", {"statut": "RESOLU"}),
            CodeErreur.TRANSITION_STATUT_INVALIDE, 409,
        )
        assert corps["details"] == {"statut_actuel": "SOUMIS", "statuts_possibles": ["DOUBLON", "RECU", "REJETE"]}
        assert "« Soumis » à « Résolu »" in corps["message"]

    @pytest.mark.parametrize("final", ["RESOLU", "REJETE"])
    def test_dossier_clos_definitif(self, mairie, signalement, agent, final):
        services.changer_statut(signalement, par=agent, statut="RECU")
        services.changer_statut(signalement, par=agent, statut="EN_COURS")
        services.changer_statut(signalement, par=agent, statut=final, commentaire="Fin")
        corps = erreur(poster(mairie, signalement, "changer-statut", {"statut": "EN_COURS"}), CodeErreur.TRANSITION_STATUT_INVALIDE, 409)
        assert corps["details"]["statuts_possibles"] == []

    def test_soumis_ne_peut_pas_etre_demande(self, mairie, signalement):
        reponse = poster(mairie, signalement, "changer-statut", {"statut": "SOUMIS"})
        assert "statut" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_rejet_avec_motif_obligatoire(self, mairie, signalement):
        assert "commentaire" in erreur(
            poster(mairie, signalement, "changer-statut", {"statut": "REJETE", "commentaire": " "}),
            CodeErreur.VALIDATION_ERREUR, 400,
        )["details"]
        ok(poster(mairie, signalement, "changer-statut", {"statut": "REJETE", "commentaire": "Terrain privé."}))

    def test_doublon(self, mairie, signalement, creer_signalement, citoyen):
        origine = creer_signalement(citoyen)
        donnees = ok(poster(mairie, signalement, "changer-statut", {"statut": "DOUBLON", "doublon_de": origine.pk}))["donnees"]
        assert donnees["doublon_de"]["reference"] == origine.reference
        assert origine.reference in donnees["historique"][-1]["commentaire"]

    def test_doublon_sans_origine(self, mairie, signalement):
        reponse = poster(mairie, signalement, "changer-statut", {"statut": "DOUBLON"})
        assert "doublon_de" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_doublon_de_lui_meme(self, mairie, signalement):
        reponse = poster(mairie, signalement, "changer-statut", {"statut": "DOUBLON", "doublon_de": signalement.pk})
        assert "doublon_de" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_doublon_d_un_doublon(self, mairie, signalement, creer_signalement, citoyen, agent):
        origine, intermediaire = creer_signalement(citoyen), creer_signalement(citoyen)
        services.changer_statut(intermediaire, par=agent, statut="DOUBLON", doublon_de=origine)
        reponse = poster(mairie, signalement, "changer-statut", {"statut": "DOUBLON", "doublon_de": intermediaire.pk})
        erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_reserve_a_la_mairie(self, signalement, creer_utilisateur, client_connecte, role):
        client = client_connecte(creer_utilisateur(role=role))
        erreur(poster(client, signalement, "changer-statut", {"statut": "RECU"}), CodeErreur.PERMISSION_REFUSEE, 403)
        signalement.refresh_from_db()
        assert signalement.statut == Statut.SOUMIS

    def test_admin_mairie_autorise(self, signalement, creer_utilisateur, client_connecte):
        client = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))
        ok(poster(client, signalement, "changer-statut", {"statut": "RECU"}))

    def test_signalement_inconnu(self, mairie, signalement):
        signalement.pk = 999999
        erreur(poster(mairie, signalement, "changer-statut", {"statut": "RECU"}), CodeErreur.RESSOURCE_INTROUVABLE, 404)


class TestAssignation:
    def test_a_un_agent_assigne_aussi_son_service(self, mairie, signalement, creer_utilisateur):
        eclairage = ServiceMunicipal.objects.create(nom="Éclairage public")
        electricien = creer_utilisateur(role=Utilisateur.Role.AGENT, service=eclairage)
        donnees = ok(poster(mairie, signalement, "assigner", {"agent": electricien.pk}))["donnees"]
        assert donnees["service_assigne"]["id"] == eclairage.pk
        assert donnees["agent_assigne"]["id"] == electricien.pk
        suivi = signalement.suivis.get(type_evenement="ASSIGNATION")
        assert suivi.commentaire == "Dossier confié au service « Éclairage public »."
        assert suivi.visible_citoyen

    def test_a_un_service_seul(self, mairie, signalement):
        service = ServiceMunicipal.objects.create(nom="Hygiène")
        donnees = ok(poster(mairie, signalement, "assigner", {"service": service.pk}))["donnees"]
        assert (donnees["service_assigne"]["nom"], donnees["agent_assigne"]) == ("Hygiène", None)

    def test_agent_d_un_autre_service(self, mairie, signalement, agent):
        autre = ServiceMunicipal.objects.create(nom="Hygiène")
        reponse = poster(mairie, signalement, "assigner", {"service": autre.pk, "agent": agent.pk})
        assert "agent" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_service_ou_agent_obligatoire(self, mairie, signalement):
        erreur(poster(mairie, signalement, "assigner", {}), CodeErreur.VALIDATION_ERREUR, 400)

    def test_un_citoyen_n_est_pas_un_agent(self, mairie, signalement, citoyen):
        reponse = poster(mairie, signalement, "assigner", {"agent": citoyen.pk})
        assert "agent" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_dossier_clos(self, mairie, signalement, agent):
        services.changer_statut(signalement, par=agent, statut="REJETE", commentaire="Hors compétence.")
        erreur(poster(mairie, signalement, "assigner", {"agent": agent.pk}), CodeErreur.SIGNALEMENT_CLOTURE, 409)

    def test_le_citoyen_ne_voit_pas_l_agent(self, mairie, signalement, agent, citoyen, client_connecte):
        ok(poster(mairie, signalement, "assigner", {"agent": agent.pk}))
        detail = client_connecte(citoyen).get(url(signalement, "detail")).json()["donnees"]
        assert "agent_assigne" not in detail
        assert "Ahouansou" not in str(detail)


class TestReponses:
    def test_reponse_officielle_visible(self, mairie, signalement, citoyen, client_connecte):
        corps = ok(poster(mairie, signalement, "repondre", {"commentaire": "Travaux prévus lundi."}), 201)
        assert corps["message"] == "Réponse publiée."
        historique = client_connecte(citoyen).get(url(signalement, "detail")).json()["donnees"]["historique"]
        assert historique[-1]["type_evenement"] == "REPONSE"
        assert historique[-1]["commentaire"] == "Travaux prévus lundi."

    def test_note_interne_invisible(self, mairie, signalement, citoyen, client_connecte):
        corps = ok(poster(mairie, signalement, "repondre", {"commentaire": "Voir SBEE.", "interne": True}), 201)
        assert corps["message"] == "Note interne ajoutée."
        assert corps["donnees"]["historique"][-1]["visible_citoyen"] is False
        historique = client_connecte(citoyen).get(url(signalement, "detail")).json()["donnees"]["historique"]
        assert "Voir SBEE." not in str(historique)

    def test_possible_sur_dossier_clos(self, mairie, signalement, agent):
        services.changer_statut(signalement, par=agent, statut="REJETE", commentaire="Hors compétence.")
        ok(poster(mairie, signalement, "repondre", {"commentaire": "Contactez la SONEB."}), 201)

    def test_commentaire_obligatoire(self, mairie, signalement):
        erreur(poster(mairie, signalement, "repondre", {"commentaire": ""}), CodeErreur.VALIDATION_ERREUR, 400)

    def test_reserve_a_la_mairie(self, signalement, citoyen, client_connecte):
        reponse = poster(client_connecte(citoyen), signalement, "repondre", {"commentaire": "Je réponds"})
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE, 403)
