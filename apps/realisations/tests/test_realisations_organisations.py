"""Réalisations des organisations : chacune publie et gère les siennes, dans son périmètre."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.notifications.models import Notification
from apps.realisations import services
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.suggestions import services as suggestions
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL = reverse("realisations:realisation-list")


def url(realisation):
    return reverse("realisations:realisation-detail", args=[realisation.pk])


@pytest.fixture
def parakou():
    commune = Commune.objects.create(
        nom="Parakou", code="PKO", departement="Borgou",
        lat_min=Decimal("9.2"), lat_max=Decimal("9.5"), lng_min=Decimal("2.4"), lng_max=Decimal("2.8"),
    )
    arrondissement = Arrondissement.objects.create(commune=commune, nom="3e arrondissement")
    Quartier.objects.create(arrondissement=arrondissement, nom="Gah")
    return commune


@pytest.fixture
def cotonou():
    commune = Commune.objects.create(
        nom="Cotonou", code="COT", departement="Littoral",
        lat_min=Decimal("6.3"), lat_max=Decimal("6.5"), lng_min=Decimal("2.3"), lng_max=Decimal("2.5"),
    )
    arrondissement = Arrondissement.objects.create(commune=commune, nom="1er arrondissement")
    Quartier.objects.create(arrondissement=arrondissement, nom="Akpakpa")
    return commune


def quartier_de(commune):
    return Quartier.objects.get(arrondissement__commune=commune)


@pytest.fixture
def eau():
    return Secteur.objects.create(nom="Eau", code="EAU", pour_realisation=True, pour_signalement=True, pour_suggestion=True)


@pytest.fixture
def voirie():
    return Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_realisation=True, pour_signalement=True)


@pytest.fixture
def ong(creer_utilisateur, parakou, eau):
    return creer_utilisateur(role=Utilisateur.Role.ORGANISATION, communes=[parakou], secteurs=[eau])


@pytest.fixture
def agent(creer_utilisateur, parakou):
    service = ServiceMunicipal.objects.create(commune=parakou, nom="Eau")
    return creer_utilisateur(role=Utilisateur.Role.AGENT, service=service)


def corps(secteur, commune, **surcharges):
    return {
        "titre": "Forage d'eau potable à l'école de Gah",
        "description": "Forage de 80 m et château d'eau de 10 m³.",
        "secteur": secteur.pk,
        "quartiers": [quartier_de(commune).pk],
        **surcharges,
    }


class TestCreation:
    def test_l_organisation_publie_a_son_nom(self, ong, client_connecte, parakou, eau, creer_utilisateur):
        habitant = creer_utilisateur(commune=parakou, quartier_residence=quartier_de(parakou))
        reponse = client_connecte(ong).post(URL, corps(eau, parakou, publie=True), format="json")
        assert reponse.status_code == 201, reponse.json()
        donnees = reponse.json()["donnees"]
        assert donnees["organisation"]["id"] == ong.organisation_id
        assert donnees["commune"]["nom"] == "Parakou"
        assert donnees["peut_modifier"] is True and donnees["cree_par"]["id"] == ong.pk
        # Les habitants du quartier sont prévenus, avec le nom de l'organisation.
        notification = Notification.objects.get(destinataire=habitant, type="NOUVELLE_REALISATION")
        assert notification.titre == f"Nouvelle réalisation : {ong.organisation.nom}"

    def test_hors_perimetre(self, ong, client_connecte, cotonou, parakou, voirie):
        client = client_connecte(ong)
        hors_commune = client.post(URL, corps(Secteur.objects.get(code="EAU"), cotonou), format="json")
        assert "quartiers" in hors_commune.json()["erreur"]["details"]
        hors_secteur = client.post(URL, corps(voirie, parakou), format="json")
        assert "secteur" in hors_secteur.json()["erreur"]["details"]

    def test_signalements_du_perimetre_mais_pas_de_suggestions(self, ong, client_connecte, creer_utilisateur, televerser, parakou, eau, voirie):
        citoyen = creer_utilisateur(commune=parakou)

        def signaler(secteur):
            dossier, _ = signalements.creer_signalement(
                auteur=citoyen, secteur=secteur, quartier=quartier_de(parakou), mode_localisation="MANUEL",
                medias_ids=[televerser(citoyen).id], titre="Fuite", description_texte="Fuite", repere="École",
            )
            return dossier

        client = client_connecte(ong)
        ok = client.post(URL, corps(eau, parakou, signalements=[signaler(eau).pk]), format="json")
        assert ok.status_code == 201, ok.json()
        hors_secteur = client.post(URL, corps(eau, parakou, signalements=[signaler(voirie).pk]), format="json")
        assert "signalements" in hors_secteur.json()["erreur"]["details"]
        idee = suggestions.creer_suggestion(auteur=citoyen, titre="Forage", description="Un forage", secteur=eau)
        refus = client.post(URL, corps(eau, parakou, suggestions=[idee.pk]), format="json")
        assert "suggestions" in refus.json()["erreur"]["details"]


class TestGestion:
    def test_chacun_modifie_les_siennes(self, ong, agent, client_connecte, creer_utilisateur, parakou, eau):
        de_l_ong = services.creer_realisation(
            par=ong, titre="Forage", description="Forage", secteur=eau, quartiers=[quartier_de(parakou)], publie=True
        )
        de_la_mairie = services.creer_realisation(
            par=agent, titre="Borne-fontaine", description="Borne", secteur=eau, quartiers=[quartier_de(parakou)], publie=True
        )
        autre_ong = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, communes=[parakou], secteurs=[eau])

        assert client_connecte(ong).patch(url(de_l_ong), {"taux_avancement": 50}, format="json").status_code == 200
        for client, realisation in (
            (client_connecte(agent), de_l_ong),
            (client_connecte(ong), de_la_mairie),
            (client_connecte(autre_ong), de_l_ong),
        ):
            reponse = client.patch(url(realisation), {"titre": "Modifié"}, format="json")
            assert reponse.status_code == 403
            assert reponse.json()["erreur"]["code"] == CodeErreur.PERMISSION_REFUSEE
        assert client_connecte(agent).patch(url(de_la_mairie), {"taux_avancement": 20}, format="json").status_code == 200

    def test_brouillons_visibles_par_leur_seul_auteur(self, ong, agent, client_connecte, api_client, creer_utilisateur, parakou, eau):
        brouillon_ong = services.creer_realisation(
            par=ong, titre="Forage", description="Forage", secteur=eau, quartiers=[quartier_de(parakou)]
        )
        brouillon_mairie = services.creer_realisation(
            par=agent, titre="Borne", description="Borne", secteur=eau, quartiers=[quartier_de(parakou)]
        )
        autre_ong = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, communes=[parakou], secteurs=[eau])

        def ids(client, **params):
            return {d["id"] for d in client.get(URL, params).json()["donnees"]}

        assert ids(client_connecte(ong)) == {brouillon_ong.pk}
        assert ids(client_connecte(agent)) == {brouillon_mairie.pk}
        assert ids(client_connecte(autre_ong)) == set() and ids(api_client) == set()
        assert ids(client_connecte(ong), publie="false") == {brouillon_ong.pk}

    def test_filtres_et_affichage_public(self, ong, agent, api_client, parakou, eau):
        de_l_ong = services.creer_realisation(
            par=ong, titre="Forage", description="Forage", secteur=eau, quartiers=[quartier_de(parakou)], publie=True
        )
        de_la_mairie = services.creer_realisation(
            par=agent, titre="Borne", description="Borne", secteur=eau, quartiers=[quartier_de(parakou)], publie=True
        )
        assert [d["id"] for d in api_client.get(URL, {"par_la_mairie": "true"}).json()["donnees"]] == [de_la_mairie.pk]
        publique = api_client.get(URL, {"organisation": ong.organisation_id}).json()["donnees"]
        assert [d["id"] for d in publique] == [de_l_ong.pk]
        assert publique[0]["organisation"]["nom"] == ong.organisation.nom
        assert publique[0]["peut_modifier"] is False and "publie" not in publique[0]

    def test_tableau_de_bord_de_la_mairie_sans_brouillons_des_ong(self, ong, agent, client_connecte, parakou, eau):
        services.creer_realisation(par=ong, titre="Forage", description="Forage", secteur=eau, quartiers=[quartier_de(parakou)])
        services.creer_realisation(par=agent, titre="Borne", description="Borne", secteur=eau, quartiers=[quartier_de(parakou)])
        realisations = client_connecte(agent).get(reverse("dashboard:synthese")).json()["donnees"]["realisations"]
        assert (realisations["total"], realisations["brouillons"]) == (1, 1)


def test_statistiques_des_organisations(ong, agent, client_connecte, parakou, eau):
    services.creer_realisation(par=ong, titre="Forage", description="Forage", secteur=eau, quartiers=[quartier_de(parakou)], publie=True)
    services.creer_realisation(par=ong, titre="Puits", description="Puits", secteur=eau, quartiers=[quartier_de(parakou)])
    [organisation] = client_connecte(agent).get(reverse("accounts:organisations")).json()["donnees"]
    assert organisation["statistiques"]["realisations_publiees"] == 1


def test_photos_d_une_realisation_d_organisation(ong, client_connecte, televerser, parakou, eau):
    photo = televerser(ong)
    reponse = client_connecte(ong).post(
        URL, corps(eau, parakou, medias=[{"media": str(photo.id), "phase": "APRES"}], publie=True), format="json"
    )
    assert reponse.status_code == 201, reponse.json()
    assert reponse.json()["donnees"]["nb_medias"] == 1
