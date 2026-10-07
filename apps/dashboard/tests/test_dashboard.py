from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.realisations import services as realisations
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.signalements.models import Signalement
from apps.suggestions import services as suggestions
from apps.territoire.models import Arrondissement, Quartier

pytestmark = pytest.mark.django_db

URLS = {nom: reverse(f"dashboard:{nom}") for nom in ("synthese", "par-secteur", "par-quartier", "evolution", "carte")}


@pytest.fixture
def donnees(commune, creer_utilisateur, televerser):
    """
    Voirie : 3 signalements (1 résolu en 2 jours, 1 en cours, 1 soumis) à Togoudo, dont 2 en GPS.
    Éclairage : 1 signalement rejeté à Cococodji. 2 suggestions, 2 réalisations (1 brouillon).
    """
    godomey = Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")
    calavi = Arrondissement.objects.create(commune=commune, nom="Calavi", code="CAL")
    togoudo = Quartier.objects.create(
        arrondissement=godomey, nom="Togoudo", code="TOG", latitude_centre=Decimal("6.4"), longitude_centre=Decimal("2.34")
    )
    cococodji = Quartier.objects.create(arrondissement=calavi, nom="Cococodji", code="COC")
    voirie = Secteur.objects.create(nom="Voirie", code="VOIRIE", couleur="#F57C00", pour_signalement=True, pour_suggestion=True, pour_realisation=True)
    eclairage = Secteur.objects.create(nom="Éclairage", code="ECLAIRAGE", pour_signalement=True, pour_realisation=True)
    agent = creer_utilisateur(role=Utilisateur.Role.AGENT, service=ServiceMunicipal.objects.create(nom="Voirie"))
    citoyen = creer_utilisateur()

    def signaler(secteur, quartier, gps=False):
        options = (
            {"mode_localisation": "GPS", "latitude": 6.401, "longitude": 2.341, "precision_gps": 10}
            if gps else {"mode_localisation": "MANUEL", "repere": "Marché"}
        )
        dossier, _ = signalements.creer_signalement(
            auteur=citoyen, secteur=secteur, quartier=quartier, medias_ids=[televerser(citoyen).id],
            titre="Problème", description_texte="Description", **options,
        )
        return dossier

    resolu, en_cours, soumis = signaler(voirie, togoudo, gps=True), signaler(voirie, togoudo, gps=True), signaler(voirie, togoudo)
    rejete = signaler(eclairage, cococodji)
    for statut in ("RECU", "EN_COURS", "RESOLU"):
        signalements.changer_statut(resolu, par=agent, statut=statut)
    # Envoyé il y a 2 jours, résolu maintenant.
    Signalement.objects.filter(pk=resolu.pk).update(cree_le=timezone.now() - timedelta(days=2), date_resolution=timezone.now())
    for statut in ("RECU", "EN_COURS"):
        signalements.changer_statut(en_cours, par=agent, statut=statut)
    signalements.changer_statut(rejete, par=agent, statut="REJETE", commentaire="Hors compétence.")

    idee = suggestions.creer_suggestion(auteur=citoyen, titre="Bancs", description="D", secteur=voirie, quartier=togoudo)
    suggestions.creer_suggestion(auteur=citoyen, titre="Salubrité", description="D", secteur=voirie)
    suggestions.soutenir(idee, creer_utilisateur())
    suggestions.marquer_pertinente(idee)

    realisations.creer_realisation(
        par=agent, titre="Pavage", description="D", secteur=voirie, quartiers=[togoudo], publie=True,
        budget=1000000, taux_avancement=40, statut="EN_COURS", latitude=6.4015, longitude=2.3418,
    )
    realisations.creer_realisation(par=agent, titre="Brouillon", description="D", secteur=eclairage, quartiers=[cococodji], budget=500000)
    return {"togoudo": togoudo, "cococodji": cococodji, "voirie": voirie, "eclairage": eclairage, "agent": agent, "citoyen": citoyen}


@pytest.fixture
def mairie(donnees, client_connecte):
    return client_connecte(donnees["agent"])


@pytest.fixture
def organisation(donnees, creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur(role=Utilisateur.Role.ORGANISATION))


def lire(client, nom, **params):
    reponse = client.get(URLS[nom], params)
    assert reponse.status_code == 200, reponse.json()
    return reponse.json()["donnees"]


class TestSynthese:
    def test_chiffres_vus_par_la_mairie(self, mairie):
        donnees = lire(mairie, "synthese")
        assert donnees["signalements"] == {
            "total": 4,
            "par_statut": {"SOUMIS": 1, "RECU": 0, "EN_COURS": 1, "RESOLU": 1, "REJETE": 1, "DOUBLON": 0},
            "ouverts": 2,
            "resolus": 1,
            "taux_resolution": 25.0,
            "delai_moyen_resolution_jours": 2.0,
        }
        assert donnees["suggestions"] == {"total": 2, "nb_soutiens": 1, "pertinentes": 1}
        assert donnees["realisations"] == {
            "total": 2,
            "par_statut": {"PLANIFIEE": 1, "EN_COURS": 1, "TERMINEE": 0, "SUSPENDUE": 0},
            "budget_total": 1500000,
            "taux_avancement_moyen": 20.0,
            "brouillons": 1,
        }

    def test_une_organisation_ne_voit_ni_brouillons_ni_pertinence(self, organisation):
        donnees = lire(organisation, "synthese")
        assert "pertinentes" not in donnees["suggestions"]
        assert "brouillons" not in donnees["realisations"]
        assert donnees["realisations"]["total"] == 1 and donnees["realisations"]["budget_total"] == 1000000

    def test_filtres(self, mairie, donnees):
        assert lire(mairie, "synthese", secteur=donnees["eclairage"].pk)["signalements"]["total"] == 1
        assert lire(mairie, "synthese", quartier=donnees["togoudo"].pk)["signalements"]["total"] == 3
        demain = (timezone.localdate() + timedelta(days=1)).isoformat()
        vide = lire(mairie, "synthese", date_debut=demain)
        assert vide["signalements"]["total"] == 0 and vide["signalements"]["taux_resolution"] is None
        assert vide["realisations"]["taux_avancement_moyen"] is None

    def test_dates_incoherentes(self, mairie):
        reponse = mairie.get(URLS["synthese"], {"date_debut": "2026-10-10", "date_fin": "2026-10-01"})
        assert reponse.status_code == 400 and "date_fin" in reponse.json()["erreur"]["details"]


class TestRepartitions:
    def test_par_secteur(self, mairie):
        lignes = lire(mairie, "par-secteur")
        assert [l["secteur"]["code"] for l in lignes] == ["VOIRIE", "ECLAIRAGE"]
        assert {k: v for k, v in lignes[0].items() if k != "secteur"} == {
            "signalements": 3, "signalements_ouverts": 2, "signalements_resolus": 1,
            "taux_resolution": 33.3, "suggestions": 2, "realisations": 1,
        }
        assert lignes[1]["realisations"] == 1  # brouillon compté pour la mairie

    def test_par_secteur_organisation_sans_brouillon(self, organisation):
        eclairage = next(l for l in lire(organisation, "par-secteur") if l["secteur"]["code"] == "ECLAIRAGE")
        assert eclairage["realisations"] == 0

    def test_par_quartier(self, mairie, donnees):
        lignes = lire(mairie, "par-quartier")
        assert [l["quartier"]["nom"] for l in lignes] == ["Togoudo", "Cococodji"]
        assert (lignes[0]["signalements"], lignes[0]["suggestions"], lignes[0]["realisations"]) == (3, 1, 1)
        par_arrondissement = lire(mairie, "par-quartier", arrondissement=donnees["cococodji"].arrondissement_id)
        assert [l["quartier"]["nom"] for l in par_arrondissement] == ["Cococodji"]


class TestEvolution:
    def test_douze_mois_sans_trou(self, mairie):
        donnees = lire(mairie, "evolution")
        assert donnees["periode"] == "mois" and len(donnees["points"]) == 12
        assert donnees["points"][-1]["periode"] == timezone.localdate().replace(day=1).isoformat()
        assert sum(p["signalements_crees"] for p in donnees["points"]) == 4
        assert sum(p["suggestions_creees"] for p in donnees["points"]) == 2
        assert sum(p["signalements_resolus"] for p in donnees["points"]) == 1

    def test_par_jour(self, mairie):
        points = lire(mairie, "evolution", periode="jour")["points"]
        assert len(points) == 30
        assert points[-1] == {
            "periode": timezone.localdate().isoformat(),
            "signalements_crees": 3,
            "signalements_resolus": 1,
            "suggestions_creees": 2,
        }
        assert points[-3]["periode"] == (timezone.localdate() - timedelta(days=2)).isoformat()
        assert points[-3]["signalements_crees"] == 1

    def test_par_semaine_commence_le_lundi(self, mairie):
        assert all(
            timezone.datetime.fromisoformat(p["periode"]).weekday() == 0 for p in lire(mairie, "evolution", periode="semaine")["points"]
        )

    def test_trop_de_points(self, mairie):
        reponse = mairie.get(URLS["evolution"], {"periode": "jour", "date_debut": "2024-01-01", "date_fin": "2026-01-01"})
        assert reponse.status_code == 400 and "periode" in reponse.json()["erreur"]["details"]


class TestCarte:
    def test_points_quartiers_et_realisations(self, mairie):
        donnees = lire(mairie, "carte")
        assert len(donnees["signalements"]) == 2 and donnees["signalements_tronques"] is False
        point = donnees["signalements"][0]
        assert set(point) == {"id", "reference", "titre", "statut", "secteur", "latitude", "longitude", "cree_le"}
        # Cococodji n'a pas de centre connu : seul Togoudo apparaît (3 signalements GPS et manuels).
        assert [(q["quartier"]["nom"], q["signalements"]) for q in donnees["quartiers"]] == [("Togoudo", 3)]
        assert [r["titre"] for r in donnees["realisations"]] == ["Pavage"]

    def test_filtre_statut(self, mairie):
        assert len(lire(mairie, "carte", statut="RESOLU")["signalements"]) == 1

    def test_aucun_auteur(self, organisation, donnees):
        assert str(donnees["citoyen"].telephone) not in str(lire(organisation, "carte"))


class TestAcces:
    @pytest.mark.parametrize("nom", list(URLS))
    def test_citoyen_refuse(self, nom, donnees, client_connecte):
        reponse = client_connecte(donnees["citoyen"]).get(URLS[nom])
        assert reponse.status_code == 403 and reponse.json()["erreur"]["code"] == CodeErreur.PERMISSION_REFUSEE

    @pytest.mark.parametrize("nom", list(URLS))
    def test_non_authentifie(self, nom, api_client):
        assert api_client.get(URLS[nom]).status_code == 401

    @pytest.mark.parametrize("nom", list(URLS))
    def test_organisations_et_admins_autorises(self, nom, organisation, creer_utilisateur, client_connecte):
        lire(organisation, nom)
        lire(client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE)), nom)


@pytest.mark.parametrize("nom", list(URLS))
def test_nombre_de_requetes_independant_du_volume(nom, mairie, donnees, televerser):
    def compter():
        with CaptureQueriesContext(connection) as requetes:
            mairie.get(URLS[nom])
        return len(requetes)

    avant = compter()
    for _ in range(3):
        signalements.creer_signalement(
            auteur=donnees["citoyen"], secteur=donnees["voirie"], quartier=donnees["togoudo"],
            mode_localisation="GPS", latitude=6.401, longitude=2.341, precision_gps=10,
            medias_ids=[televerser(donnees["citoyen"]).id], titre="T", description_texte="D",
        )
    assert compter() == avant
