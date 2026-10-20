"""Notifications des organisations et statistiques de leur périmètre."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Organisation, ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.notifications.models import Notification
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.signalements.models import Signalement
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL = reverse("accounts:organisations")


def creer_commune(nom, code, lat, lng):
    commune = Commune.objects.create(
        nom=nom, code=code, departement="Test",
        lat_min=Decimal(lat) - 1, lat_max=Decimal(lat) + 1, lng_min=Decimal(lng) - 1, lng_max=Decimal(lng) + 1,
    )
    arrondissement = Arrondissement.objects.create(commune=commune, nom=f"1er arrondissement de {nom}")
    Quartier.objects.create(arrondissement=arrondissement, nom=f"Centre {nom}")
    return commune


@pytest.fixture
def parakou():
    return creer_commune("Parakou", "PKO", "9.34", "2.62")


@pytest.fixture
def cotonou():
    return creer_commune("Cotonou", "COT", "6.37", "2.42")


@pytest.fixture
def eau():
    return Secteur.objects.create(nom="Eau", code="EAU", pour_signalement=True)


@pytest.fixture
def voirie():
    return Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_signalement=True)


@pytest.fixture
def signaler(creer_utilisateur, televerser):
    def _signaler(commune, secteur):
        auteur = creer_utilisateur(commune=commune, nom="Hounkpatin", prenoms="Afiavi")
        dossier, _ = signalements.creer_signalement(
            auteur=auteur, secteur=secteur, quartier=Quartier.objects.get(arrondissement__commune=commune),
            mode_localisation="MANUEL", medias_ids=[televerser(auteur).id],
            titre="Fuite sur la canalisation", description_texte="L'eau coule depuis hier", repere="Marché",
        )
        return dossier

    return _signaler


@pytest.fixture
def membre_ong(creer_utilisateur):
    """Compte d'une organisation au périmètre donné."""

    def _membre(communes, secteurs, **organisation):
        compte = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, communes=communes, secteurs=secteurs)
        if organisation:
            Organisation.objects.filter(pk=compte.organisation_id).update(**organisation)
        return compte

    return _membre


def notifications_de(compte):
    return list(Notification.objects.filter(destinataire=compte, type="NOUVEAU_SIGNALEMENT"))


class TestNotificationsNouveauSignalement:
    def test_organisation_du_perimetre_notifiee(self, membre_ong, signaler, parakou, eau):
        compte = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        [notification] = notifications_de(compte)
        assert (notification.cible_type, notification.cible_id) == ("signalement", dossier.pk)
        assert notification.titre == "Nouveau signalement : Eau"
        assert dossier.reference in notification.message and "Parakou" in notification.message
        # Jamais l'identité de l'auteur.
        assert "Hounkpatin" not in notification.message and "Afiavi" not in notification.message

    def test_hors_commune_ou_hors_secteur(self, membre_ong, signaler, parakou, cotonou, eau, voirie):
        autre_commune = membre_ong([cotonou], [eau])
        autre_secteur = membre_ong([parakou], [voirie])
        signaler(parakou, eau)
        assert notifications_de(autre_commune) == [] and notifications_de(autre_secteur) == []

    @pytest.mark.parametrize(
        "organisation",
        [
            {"statut_habilitation": "SUSPENDUE", "motif_suspension": "Contrôle en cours"},
            {"date_expiration": timezone.localdate() - timedelta(days=1)},
        ],
    )
    def test_organisation_sans_acces(self, membre_ong, signaler, parakou, eau, organisation):
        compte = membre_ong([parakou], [eau], **organisation)
        signaler(parakou, eau)
        assert notifications_de(compte) == []

    def test_compte_desactive(self, membre_ong, signaler, parakou, eau):
        compte = membre_ong([parakou], [eau])
        Utilisateur.objects.filter(pk=compte.pk).update(is_active=False)
        signaler(parakou, eau)
        assert notifications_de(compte) == []

    def test_tous_les_comptes_de_l_organisation(self, creer_utilisateur, membre_ong, signaler, parakou, eau):
        premier = membre_ong([parakou], [eau])
        second = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, organisation=premier.organisation)
        signaler(parakou, eau)
        assert len(notifications_de(premier)) == len(notifications_de(second)) == 1

    def test_visible_dans_ses_notifications(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        signaler(parakou, eau)
        donnees = client_connecte(compte).get(reverse("notifications:notifications")).json()["donnees"]
        assert [n["type"] for n in donnees] == ["NOUVEAU_SIGNALEMENT"]


@pytest.fixture
def agent_de(creer_utilisateur):
    def _agent(commune, role=Utilisateur.Role.AGENT):
        if role == Utilisateur.Role.AGENT:
            service = ServiceMunicipal.objects.create(commune=commune, nom=f"Voirie {commune.code}")
            return creer_utilisateur(role=role, service=service)
        return creer_utilisateur(role=role, commune=commune)

    return _agent


def resoudre(dossier, agent, jours):
    for statut in ("RECU", "EN_COURS", "RESOLU"):
        signalements.changer_statut(dossier, par=agent, statut=statut)
    Signalement.objects.filter(pk=dossier.pk).update(cree_le=timezone.now() - timedelta(days=jours))


class TestStatistiques:
    def test_liste_et_chiffres(self, membre_ong, signaler, agent_de, client_connecte, parakou, eau, voirie):
        membre_ong([parakou], [eau])
        agent = agent_de(parakou)
        resoudre(signaler(parakou, eau), agent, jours=4)
        resoudre(signaler(parakou, eau), agent, jours=6)
        en_cours = signaler(parakou, eau)
        signalements.changer_statut(en_cours, par=agent, statut="RECU")
        signaler(parakou, eau)
        signaler(parakou, voirie)  # hors de ses secteurs

        reponse = client_connecte(agent).get(URL)
        assert reponse.status_code == 200, reponse.json()
        [organisation] = reponse.json()["donnees"]
        assert organisation["nb_comptes"] == 1 and organisation["acces_actif"] is True
        assert organisation["communes"] == [{"id": parakou.pk, "nom": "Parakou"}]
        assert organisation["statistiques"] == {
            "signalements": 4, "en_attente": 1, "en_cours": 1, "ouverts": 2, "resolus": 2, "rejetes": 0,
            "taux_resolution": 50.0, "delai_moyen_resolution_jours": 5.0,
            "pris_en_charge": 0, "resolus_pris_en_charge": 0, "realisations_publiees": 0,
        }

    def test_detail_par_commune_et_par_secteur(self, creer_utilisateur, membre_ong, signaler, client_connecte, parakou, cotonou, eau, voirie):
        compte = membre_ong([parakou, cotonou], [eau, voirie])
        signaler(parakou, eau)
        signaler(cotonou, eau)
        signaler(cotonou, voirie)
        admin_plateforme = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=None))
        donnees = admin_plateforme.get(reverse("accounts:organisation-detail", args=[compte.organisation_id])).json()["donnees"]
        assert donnees["statistiques"]["signalements"] == 3
        assert {c["commune"]["nom"]: c["signalements"] for c in donnees["statistiques_par_commune"]} == {"Parakou": 1, "Cotonou": 2}
        assert {s["secteur"]["code"]: s["signalements"] for s in donnees["statistiques_par_secteur"]} == {"EAU": 2, "VOIRIE": 1}
        # Filtre sur une commune.
        filtre = admin_plateforme.get(reverse("accounts:organisation-detail", args=[compte.organisation_id]), {"commune": cotonou.pk})
        assert filtre.json()["donnees"]["statistiques"]["signalements"] == 2

    def test_mairie_d_une_commune_limitee_a_la_sienne(self, membre_ong, signaler, agent_de, client_connecte, parakou, cotonou, eau):
        a_parakou_et_cotonou = membre_ong([parakou, cotonou], [eau])
        seulement_cotonou = membre_ong([cotonou], [eau])
        signaler(parakou, eau)
        signaler(cotonou, eau)
        mairie = client_connecte(agent_de(parakou, Utilisateur.Role.ADMIN_MAIRIE))
        donnees = mairie.get(URL, {"commune": cotonou.pk}).json()["donnees"]
        assert [o["id"] for o in donnees] == [a_parakou_et_cotonou.organisation_id]
        assert donnees[0]["statistiques"]["signalements"] == 1  # seulement Parakou
        detail = reverse("accounts:organisation-detail", args=[seulement_cotonou.organisation_id])
        assert mairie.get(detail).status_code == 404

    def test_periode(self, membre_ong, signaler, agent_de, client_connecte, parakou, eau):
        membre_ong([parakou], [eau])
        ancien = signaler(parakou, eau)
        Signalement.objects.filter(pk=ancien.pk).update(cree_le=timezone.now() - timedelta(days=40))
        signaler(parakou, eau)
        client = client_connecte(agent_de(parakou))
        depuis = (timezone.localdate() - timedelta(days=7)).isoformat()
        assert client.get(URL, {"date_debut": depuis}).json()["donnees"][0]["statistiques"]["signalements"] == 1
        erreur = client.get(URL, {"date_debut": depuis, "date_fin": "2020-01-01"}).json()["erreur"]
        assert erreur["code"] == CodeErreur.VALIDATION_ERREUR and "date_fin" in erreur["details"]

    def test_sans_signalement(self, membre_ong, agent_de, client_connecte, parakou, eau):
        membre_ong([parakou], [eau])
        statistiques = client_connecte(agent_de(parakou)).get(URL).json()["donnees"][0]["statistiques"]
        assert statistiques["signalements"] == 0 and statistiques["taux_resolution"] is None
        assert statistiques["delai_moyen_resolution_jours"] is None

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_reserve_a_la_mairie(self, creer_utilisateur, client_connecte, role):
        reponse = client_connecte(creer_utilisateur(role=role)).get(URL)
        assert reponse.status_code == 403


def url_action(dossier, action):
    return reverse(f"signalements:signalement-{action}", args=[dossier.pk])


class TestPriseEnCharge:
    """Une organisation se confie un dossier libre de son périmètre, puis le fait avancer."""

    def test_prendre_en_charge_puis_faire_avancer(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        ong = client_connecte(compte)

        reponse = ong.post(url_action(dossier, "prendre-en-charge"))
        assert reponse.status_code == 200, reponse.json()
        donnees = reponse.json()["donnees"]
        assert donnees["organisation_assignee"]["id"] == compte.organisation_id
        assert donnees["historique"][-1]["organisation"] == compte.organisation.nom
        # Renvoyer la requête est sans effet.
        assert ong.post(url_action(dossier, "prendre-en-charge")).status_code == 200

        for statut in ("RECU", "EN_COURS", "RESOLU"):
            reponse = ong.post(url_action(dossier, "changer-statut"), {"statut": statut, "commentaire": "Équipe passée."}, format="json")
            assert reponse.status_code == 200, reponse.json()
        dossier.refresh_from_db()
        assert dossier.statut == "RESOLU" and dossier.date_resolution is not None
        # Le citoyen est notifié et voit le nom de l'organisation, jamais l'inverse.
        assert Notification.objects.filter(destinataire=dossier.auteur, type="STATUT_SIGNALEMENT").count() == 3

    def test_rejet_et_doublon_reserves_a_la_mairie(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        ong = client_connecte(compte)
        ong.post(url_action(dossier, "prendre-en-charge"))
        reponse = ong.post(url_action(dossier, "changer-statut"), {"statut": "REJETE", "commentaire": "Non"}, format="json")
        assert reponse.status_code == 403 and reponse.json()["erreur"]["code"] == CodeErreur.PERMISSION_REFUSEE

    def test_deja_pris_par_une_autre(self, membre_ong, signaler, client_connecte, parakou, eau):
        premiere = membre_ong([parakou], [eau])
        seconde = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        client_connecte(premiere).post(url_action(dossier, "prendre-en-charge"))
        autre = client_connecte(seconde)
        reponse = autre.post(url_action(dossier, "prendre-en-charge"))
        assert reponse.status_code == 409
        assert reponse.json()["erreur"]["code"] == CodeErreur.SIGNALEMENT_DEJA_PRIS_EN_CHARGE
        # Elle voit toujours le dossier, avec le nom de l'organisation en charge, mais ne peut pas le faire avancer.
        detail = autre.get(url_action(dossier, "detail")).json()["donnees"]
        assert detail["organisation_assignee"]["nom"] == premiere.organisation.nom
        reponse = autre.post(url_action(dossier, "changer-statut"), {"statut": "RECU"}, format="json")
        assert reponse.json()["erreur"]["code"] == CodeErreur.ORGANISATION_NON_EN_CHARGE

    def test_hors_perimetre_ou_clos(self, membre_ong, signaler, client_connecte, agent_de, parakou, eau, voirie):
        compte = membre_ong([parakou], [eau])
        hors_secteur = signaler(parakou, voirie)
        ong = client_connecte(compte)
        assert ong.post(url_action(hors_secteur, "prendre-en-charge")).status_code == 404
        clos = signaler(parakou, eau)
        signalements.changer_statut(clos, par=agent_de(parakou), statut="REJETE", commentaire="Hors compétence.")
        assert ong.post(url_action(clos, "prendre-en-charge")).json()["erreur"]["code"] == CodeErreur.SIGNALEMENT_CLOTURE

    def test_filtres_libres_et_mes_dossiers(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        pris, libre = signaler(parakou, eau), signaler(parakou, eau)
        ong = client_connecte(compte)
        ong.post(url_action(pris, "prendre-en-charge"))
        liste = reverse("signalements:signalement-list")
        assert [d["id"] for d in ong.get(liste, {"pris_en_charge": "false"}).json()["donnees"]] == [libre.pk]
        assert [d["id"] for d in ong.get(liste, {"organisation": compte.organisation_id}).json()["donnees"]] == [pris.pk]

    def test_le_citoyen_voit_l_organisation_en_charge(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        client_connecte(compte).post(url_action(dossier, "prendre-en-charge"))
        detail = client_connecte(dossier.auteur).get(url_action(dossier, "detail")).json()["donnees"]
        assert detail["organisation_assignee"]["nom"] == compte.organisation.nom
        assert detail["historique"][-1]["commentaire"].startswith("Dossier pris en charge par l'organisation")


class TestAffectationParLaMairie:
    def test_confier_remplacer_retirer(self, membre_ong, signaler, client_connecte, agent_de, parakou, eau):
        premiere = membre_ong([parakou], [eau])
        seconde = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        mairie = client_connecte(agent_de(parakou))
        url = url_action(dossier, "affecter-organisation")

        reponse = mairie.post(url, {"organisation": premiere.organisation_id}, format="json")
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["donnees"]["organisation_assignee"]["id"] == premiere.organisation_id
        assert [n.type for n in Notification.objects.filter(destinataire=premiere, type="AFFECTATION_SIGNALEMENT")] == ["AFFECTATION_SIGNALEMENT"]

        # La mairie peut remplacer l'organisation : l'ancienne ne peut plus agir.
        mairie.post(url, {"organisation": seconde.organisation_id}, format="json")
        reponse = client_connecte(premiere).post(url_action(dossier, "changer-statut"), {"statut": "RECU"}, format="json")
        assert reponse.json()["erreur"]["code"] == CodeErreur.ORGANISATION_NON_EN_CHARGE
        assert client_connecte(seconde).post(url_action(dossier, "changer-statut"), {"statut": "RECU"}, format="json").status_code == 200

        reponse = mairie.post(url, {"organisation": None}, format="json")
        assert reponse.json()["donnees"]["organisation_assignee"] is None
        assert reponse.json()["message"] == "Organisation retirée du dossier."

    def test_organisation_hors_perimetre_ou_suspendue(self, membre_ong, signaler, client_connecte, agent_de, parakou, cotonou, eau):
        a_cotonou = membre_ong([cotonou], [eau])
        suspendue = membre_ong([parakou], [eau], statut_habilitation="SUSPENDUE", motif_suspension="Contrôle")
        dossier = signaler(parakou, eau)
        mairie = client_connecte(agent_de(parakou))
        for organisation in (a_cotonou.organisation_id, suspendue.organisation_id):
            reponse = mairie.post(url_action(dossier, "affecter-organisation"), {"organisation": organisation}, format="json")
            assert reponse.status_code == 400 and "organisation" in reponse.json()["erreur"]["details"]

    def test_reserve_a_la_mairie(self, membre_ong, signaler, client_connecte, parakou, eau):
        compte = membre_ong([parakou], [eau])
        dossier = signaler(parakou, eau)
        reponse = client_connecte(compte).post(url_action(dossier, "affecter-organisation"), {"organisation": compte.organisation_id}, format="json")
        assert reponse.status_code == 403

    def test_statistiques_de_prise_en_charge(self, membre_ong, signaler, client_connecte, agent_de, parakou, eau):
        compte = membre_ong([parakou], [eau])
        ong = client_connecte(compte)
        resolu, en_cours = signaler(parakou, eau), signaler(parakou, eau)
        signaler(parakou, eau)
        for dossier in (resolu, en_cours):
            ong.post(url_action(dossier, "prendre-en-charge"))
        for statut in ("RECU", "EN_COURS", "RESOLU"):
            ong.post(url_action(resolu, "changer-statut"), {"statut": statut}, format="json")
        stats = client_connecte(agent_de(parakou)).get(URL).json()["donnees"][0]["statistiques"]
        assert (stats["signalements"], stats["pris_en_charge"], stats["resolus_pris_en_charge"]) == (3, 2, 1)
