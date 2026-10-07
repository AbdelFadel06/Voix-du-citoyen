"""
Cloisonnement par commune : chaque commune ne voit et ne traite que ses dossiers ; les
organisations et l'admin de la plateforme voient toutes les communes.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.suggestions import services as suggestions
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL_SIGNALEMENTS = reverse("signalements:signalement-list")
URL_SUGGESTIONS = reverse("suggestions:suggestion-list")
URL_REGISTER = reverse("accounts:register")


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


def quartier_de(commune):
    return Quartier.objects.get(arrondissement__commune=commune)


@pytest.fixture
def secteur():
    return Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_signalement=True, pour_suggestion=True)


@pytest.fixture
def signaler(secteur, televerser):
    def _signaler(auteur, quartier=None):
        dossier, _ = signalements.creer_signalement(
            auteur=auteur, secteur=secteur, quartier=quartier or quartier_de(auteur.commune),
            mode_localisation="MANUEL", medias_ids=[televerser(auteur).id],
            titre="Trou", description_texte="Gros trou", repere="Marché",
        )
        return dossier

    return _signaler


@pytest.fixture
def agent_de(creer_utilisateur):
    def _agent(commune):
        service = ServiceMunicipal.objects.create(commune=commune, nom=f"Voirie {commune.code}")
        return creer_utilisateur(role=Utilisateur.Role.AGENT, service=service)

    return _agent


class TestInscription:
    def corps(self, commune, **surcharges):
        return {"commune": commune.pk, "telephone": "0197123456", "nom": "Hounkpatin", "prenoms": "Afiavi",
                "password": "Barometre!2026", **surcharges}

    def test_le_citoyen_choisit_sa_commune(self, api_client, sms, parakou):
        assert api_client.post(URL_REGISTER, self.corps(parakou), format="json").status_code == 201
        assert Utilisateur.objects.get().commune == parakou

    def test_commune_obligatoire(self, api_client, sms, parakou):
        corps = self.corps(parakou)
        del corps["commune"]
        reponse = api_client.post(URL_REGISTER, corps, format="json")
        assert "commune" in reponse.json()["erreur"]["details"]

    def test_commune_non_desservie(self, api_client, sms, parakou):
        corps = {**self.corps(parakou), "commune": 999999}
        reponse = api_client.post(URL_REGISTER, corps, format="json")
        assert "commune" in reponse.json()["erreur"]["details"]

    def test_quartier_d_une_autre_commune(self, api_client, sms, parakou, cotonou):
        corps = self.corps(parakou, quartier_residence=quartier_de(cotonou).pk)
        assert "quartier_residence" in api_client.post(URL_REGISTER, corps, format="json").json()["erreur"]["details"]


class TestProfil:
    def test_changer_de_commune_efface_l_ancien_quartier(self, creer_utilisateur, client_connecte, parakou, cotonou):
        citoyen = creer_utilisateur(commune=parakou, quartier_residence=quartier_de(parakou))
        donnees = client_connecte(citoyen).patch(reverse("accounts:me"), {"commune": cotonou.pk}, format="json").json()["donnees"]
        assert (donnees["commune"], donnees["commune_nom"], donnees["quartier_residence"]) == (cotonou.pk, "Cotonou", None)

    def test_la_mairie_ne_change_pas_de_commune_par_son_profil(self, agent_de, client_connecte, parakou, cotonou):
        agent = agent_de(parakou)
        client_connecte(agent).patch(reverse("accounts:me"), {"commune": cotonou.pk}, format="json")
        agent.refresh_from_db()
        assert agent.commune == parakou


class TestSignalements:
    def test_commune_deduite_de_l_auteur(self, creer_utilisateur, signaler, parakou):
        assert signaler(creer_utilisateur(commune=parakou)).commune == parakou

    def test_quartier_d_une_autre_commune_refuse(self, creer_utilisateur, signaler, parakou, cotonou):
        from apps.core.exceptions import ErreurMetier

        with pytest.raises(ErreurMetier) as exc:
            signaler(creer_utilisateur(commune=parakou), quartier=quartier_de(cotonou))
        assert "quartier" in exc.value.details

    def test_compte_sans_commune(self, creer_utilisateur, client_connecte, secteur, cotonou, televerser):
        citoyen = creer_utilisateur(commune=None)
        reponse = client_connecte(citoyen).post(URL_SIGNALEMENTS, {
            "secteur": secteur.pk, "titre": "T", "description_texte": "D", "medias": [str(televerser(citoyen).id)],
            "mode_localisation": "MANUEL", "repere": "R", "quartier": quartier_de(cotonou).pk,
        }, format="json")
        assert reponse.json()["erreur"]["code"] == CodeErreur.COMMUNE_NON_RENSEIGNEE

    def test_chaque_citoyen_ne_voit_que_sa_commune(self, creer_utilisateur, client_connecte, signaler, parakou, cotonou):
        a_parakou = signaler(creer_utilisateur(commune=parakou))
        a_cotonou = signaler(creer_utilisateur(commune=cotonou))
        voisin_parakou = client_connecte(creer_utilisateur(commune=parakou))
        assert [d["id"] for d in voisin_parakou.get(URL_SIGNALEMENTS).json()["donnees"]] == [a_parakou.pk]
        # Le paramètre ?commune= ne permet pas de sortir de sa commune.
        assert [d["id"] for d in voisin_parakou.get(URL_SIGNALEMENTS, {"commune": cotonou.pk}).json()["donnees"]] == [a_parakou.pk]
        detail = reverse("signalements:signalement-detail", args=[a_cotonou.pk])
        assert voisin_parakou.get(detail).status_code == 404

    def test_un_agent_ne_traite_que_sa_commune(self, creer_utilisateur, client_connecte, signaler, agent_de, parakou, cotonou):
        dossier = signaler(creer_utilisateur(commune=cotonou))
        agent_parakou = client_connecte(agent_de(parakou))
        url = reverse("signalements:signalement-changer-statut", args=[dossier.pk])
        assert agent_parakou.post(url, {"statut": "RECU"}, format="json").status_code == 404
        assert client_connecte(agent_de(cotonou)).post(url, {"statut": "RECU"}, format="json").status_code == 200

    def test_assigner_a_un_service_d_une_autre_commune(self, creer_utilisateur, client_connecte, signaler, agent_de, parakou, cotonou):
        dossier = signaler(creer_utilisateur(commune=parakou))
        service_cotonou = ServiceMunicipal.objects.create(commune=cotonou, nom="Hygiène")
        url = reverse("signalements:signalement-assigner", args=[dossier.pk])
        reponse = client_connecte(agent_de(parakou)).post(url, {"service": service_cotonou.pk}, format="json")
        assert "service" in reponse.json()["erreur"]["details"]

    def test_service_par_defaut_d_une_autre_commune_ignore(self, creer_utilisateur, signaler, secteur, parakou, cotonou):
        secteur.service_par_defaut = ServiceMunicipal.objects.create(commune=cotonou, nom="Voirie Cotonou")
        secteur.save()
        assert signaler(creer_utilisateur(commune=parakou)).service_assigne is None

    def test_une_organisation_voit_toutes_les_communes(self, creer_utilisateur, client_connecte, signaler, parakou, cotonou):
        signaler(creer_utilisateur(commune=parakou))
        a_cotonou = signaler(creer_utilisateur(commune=cotonou))
        ong = client_connecte(creer_utilisateur(role=Utilisateur.Role.ORGANISATION))
        assert len(ong.get(URL_SIGNALEMENTS).json()["donnees"]) == 2
        assert [d["id"] for d in ong.get(URL_SIGNALEMENTS, {"commune": cotonou.pk}).json()["donnees"]] == [a_cotonou.pk]
        assert ong.get(URL_SIGNALEMENTS).json()["donnees"][0]["commune"]["nom"] in ("Parakou", "Cotonou")


class TestSuggestionsEtTableaux:
    def test_suggestions_cloisonnees(self, creer_utilisateur, client_connecte, secteur, parakou, cotonou):
        suggestions.creer_suggestion(auteur=creer_utilisateur(commune=cotonou), titre="T", description="D", secteur=secteur)
        mienne = suggestions.creer_suggestion(auteur=creer_utilisateur(commune=parakou), titre="T", description="D", secteur=secteur)
        assert mienne.commune == parakou
        voisin = client_connecte(creer_utilisateur(commune=parakou))
        assert [d["id"] for d in voisin.get(URL_SUGGESTIONS).json()["donnees"]] == [mienne.pk]

    def test_tableau_de_bord_cloisonne(self, creer_utilisateur, client_connecte, signaler, agent_de, parakou, cotonou):
        signaler(creer_utilisateur(commune=parakou))
        signaler(creer_utilisateur(commune=cotonou))
        signaler(creer_utilisateur(commune=cotonou))
        url = reverse("dashboard:synthese")
        assert client_connecte(agent_de(parakou)).get(url, {"commune": cotonou.pk}).json()["donnees"]["signalements"]["total"] == 1
        ong = client_connecte(creer_utilisateur(role=Utilisateur.Role.ORGANISATION))
        assert ong.get(url).json()["donnees"]["signalements"]["total"] == 3
        assert ong.get(url, {"commune": cotonou.pk}).json()["donnees"]["signalements"]["total"] == 2


class TestAdministration:
    def test_services_et_agents_de_la_commune_de_l_admin(self, creer_utilisateur, client_connecte, agent_de, parakou, cotonou):
        admin = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=parakou))
        reponse = admin.post(reverse("accounts:services"), {"nom": "Hygiène"}, format="json")
        assert reponse.json()["donnees"]["commune"] == {"id": parakou.pk, "nom": "Parakou"}
        agent_de(cotonou)
        noms = [a["commune"]["nom"] for a in admin.get(reverse("accounts:agents")).json()["donnees"]]
        assert "Cotonou" not in noms

    def test_un_agent_ne_peut_pas_etre_mis_dans_un_service_d_une_autre_commune(self, creer_utilisateur, client_connecte, parakou, cotonou):
        admin = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=parakou))
        service_cotonou = ServiceMunicipal.objects.create(commune=cotonou, nom="Voirie")
        reponse = admin.post(reverse("accounts:agents"), {
            "telephone": "0196000007", "email": "a@mairie-parakou.bj", "nom": "A", "prenoms": "B",
            "role": "AGENT", "service": service_cotonou.pk, "mot_de_passe": "Parakou!2026",
        }, format="json")
        assert "service" in reponse.json()["erreur"]["details"]

    def test_quartiers_de_sa_commune(self, creer_utilisateur, client_connecte, parakou, cotonou):
        citoyen = client_connecte(creer_utilisateur(commune=parakou))
        assert [q["nom"] for q in citoyen.get(reverse("territoire:quartiers")).json()["donnees"]] == ["Centre Parakou"]

    def test_quartier_proche_dans_sa_commune(self, creer_utilisateur, client_connecte, parakou, cotonou):
        Quartier.objects.filter(arrondissement__commune=parakou).update(latitude_centre="9.34", longitude_centre="2.62")
        citoyen = client_connecte(creer_utilisateur(commune=parakou))
        url = reverse("territoire:quartier-proche")
        assert citoyen.get(url, {"lat": 9.341, "lng": 2.621}).json()["donnees"]["quartier"]["nom"] == "Centre Parakou"
        reponse = citoyen.get(url, {"lat": 6.37, "lng": 2.42})  # position à Cotonou
        assert reponse.json()["erreur"]["code"] == CodeErreur.COORDONNEES_HORS_COMMUNE


class TestCommandes:
    def test_charger_services_dans_une_commune(self, parakou, cotonou, tmp_path):
        from django.core.management import call_command

        fichier = tmp_path / "services.csv"
        fichier.write_text("nom;description\nVoirie;Routes\n", encoding="utf-8")
        call_command("charger_services", str(fichier), commune="PKO")
        call_command("charger_services", str(fichier), commune="COT")
        assert sorted(ServiceMunicipal.objects.values_list("commune__code", flat=True)) == ["COT", "PKO"]
