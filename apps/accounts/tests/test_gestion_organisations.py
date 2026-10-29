"""Gestion des organisations par la mairie (application web ou plateforme IBDC par clé d'API)."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Organisation, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.interop import services as interop
from apps.referentiel.models import Secteur
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL = reverse("accounts:organisations")


def url(organisation, action="detail", **kwargs):
    noms = {"detail": "organisation-detail", "membres": "organisation-membres", "membre": "organisation-membre",
            "retirer": "organisation-retirer-commune", "suspendre": "organisation-suspendre",
            "rehabiliter": "organisation-rehabiliter"}
    return reverse(f"accounts:{noms[action]}", kwargs={"pk": organisation if isinstance(organisation, int) else organisation.pk, **kwargs})


def creer_commune(nom, code):
    commune = Commune.objects.create(
        nom=nom, code=code, departement="Test",
        lat_min=Decimal("6"), lat_max=Decimal("10"), lng_min=Decimal("1"), lng_max=Decimal("4"),
    )
    arrondissement = Arrondissement.objects.create(commune=commune, nom=f"Centre {nom}")
    Quartier.objects.create(arrondissement=arrondissement, nom=f"Quartier {nom}")
    return commune


@pytest.fixture
def parakou():
    return creer_commune("Parakou", "PKO")


@pytest.fixture
def cotonou():
    return creer_commune("Cotonou", "COT")


@pytest.fixture
def eau():
    return Secteur.objects.create(nom="Eau", code="EAU", pour_signalement=True)


@pytest.fixture
def sante():
    return Secteur.objects.create(nom="Santé", code="SANTE", pour_signalement=True)


@pytest.fixture
def admin_de(creer_utilisateur, client_connecte):
    def _admin(commune):
        compte = creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=commune)
        client = client_connecte(compte)
        client.compte = compte
        return client

    return _admin


@pytest.fixture
def admin_plateforme(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=None))


def corps(**surcharges):
    return {"nom": "ONG Eau Pour Tous", "sigle": "EPT", "type": "ONG", "numero_enregistrement": "2019/0457", **surcharges}


class TestCreation:
    def test_par_la_mairie(self, admin_de, parakou, eau):
        mairie = admin_de(parakou)
        reponse = mairie.post(URL, corps(secteurs=[eau.pk]), format="json")
        assert reponse.status_code == 201, reponse.json()
        donnees = reponse.json()["donnees"]
        assert donnees["communes"] == [{"id": parakou.pk, "nom": "Parakou"}]
        assert [s["code"] for s in donnees["secteurs"]] == ["EAU"]
        assert donnees["statut_habilitation"] == "HABILITEE" and donnees["acces_actif"] is True
        organisation = Organisation.objects.get()
        assert organisation.habilitee_par == mairie.compte and organisation.date_habilitation == timezone.localdate()

    def test_par_la_plateforme_ibdc(self, parakou, eau):
        institution, cle = interop.creer_institution(
            id_externe="IBDC-12", nom="Mairie de Parakou", commune=parakou,
            email="ibdc@mairie.bj", telephone="+2290196000101",
        )
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=cle)
        reponse = client.post(reverse("mairie:accounts:organisations"), corps(secteurs=[eau.pk]), format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["donnees"]["communes"][0]["nom"] == "Parakou"
        # La clé d'une mairie ne sert que dans l'espace mairie.
        assert client.get(URL).json()["erreur"]["code"] == CodeErreur.ESPACE_MAIRIE_REQUIS

    def test_meme_numero_dans_une_autre_commune_sans_doublon(self, admin_de, parakou, cotonou, eau, sante):
        premiere = admin_de(parakou).post(URL, corps(secteurs=[eau.pk]), format="json").json()["donnees"]
        reponse = admin_de(cotonou).post(URL, corps(numero_enregistrement=" 2019/0457 ", secteurs=[sante.pk]), format="json")
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["message"].startswith("Organisation déjà enregistrée")
        donnees = reponse.json()["donnees"]
        assert donnees["id"] == premiere["id"] and Organisation.objects.count() == 1
        assert {c["nom"] for c in donnees["communes"]} == {"Parakou", "Cotonou"}
        assert {s["code"] for s in donnees["secteurs"]} == {"EAU", "SANTE"}

    @pytest.mark.parametrize("numero", [None, "", "   "])
    def test_numero_facultatif(self, admin_de, parakou, numero):
        mairie = admin_de(parakou)
        champs = corps(numero_enregistrement=numero)
        assert mairie.post(URL, champs, format="json").status_code == 201
        assert mairie.post(URL, champs, format="json").status_code == 201  # sans numéro : deux fiches
        assert list(Organisation.objects.values_list("numero_enregistrement", flat=True)) == [None, None]

    def test_admin_de_la_plateforme_indique_les_communes(self, admin_plateforme, parakou, cotonou):
        assert "communes" in admin_plateforme.post(URL, corps(), format="json").json()["erreur"]["details"]
        reponse = admin_plateforme.post(URL, corps(communes=[parakou.pk, cotonou.pk]), format="json")
        assert {c["nom"] for c in reponse.json()["donnees"]["communes"]} == {"Parakou", "Cotonou"}

    def test_reserve_aux_admins(self, creer_utilisateur, client_connecte, parakou):
        agent = client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT))
        assert agent.post(URL, corps(), format="json").status_code == 403


@pytest.fixture
def ong(admin_de, parakou, eau):
    mairie = admin_de(parakou)
    identifiant = mairie.post(URL, corps(secteurs=[eau.pk]), format="json").json()["donnees"]["id"]
    return Organisation.objects.get(pk=identifiant)


class TestModificationEtPerimetre:
    def test_modifier(self, admin_de, ong, parakou, sante):
        reponse = admin_de(parakou).patch(url(ong), {"secteurs": [sante.pk], "date_expiration": "2028-12-31"}, format="json")
        assert reponse.status_code == 200, reponse.json()
        donnees = reponse.json()["donnees"]
        assert [s["code"] for s in donnees["secteurs"]] == ["SANTE"] and donnees["date_expiration"] == "2028-12-31"

    def test_numero_deja_pris(self, admin_de, ong, parakou):
        mairie = admin_de(parakou)
        autre = mairie.post(URL, corps(numero_enregistrement="AUTRE-1"), format="json").json()["donnees"]["id"]
        reponse = mairie.patch(url(autre), {"numero_enregistrement": "2019/0457"}, format="json")
        assert reponse.status_code == 409 and reponse.json()["erreur"]["code"] == CodeErreur.CONFLIT

    def test_une_mairie_ne_gere_que_les_organisations_de_sa_commune(self, admin_de, ong, cotonou):
        mairie_cotonou = admin_de(cotonou)
        assert mairie_cotonou.patch(url(ong), {"nom": "Piratée"}, format="json").status_code == 404
        assert mairie_cotonou.get(url(ong, "membres")).status_code == 404

    def test_retirer_sa_commune(self, admin_de, ong, parakou, cotonou):
        admin_de(cotonou).post(URL, corps(), format="json")  # rattache Cotonou
        mairie = admin_de(parakou)
        reponse = mairie.post(url(ong, "retirer"), {}, format="json")
        assert reponse.status_code == 200, reponse.json()
        ong.refresh_from_db()
        assert list(ong.communes.values_list("nom", flat=True)) == ["Cotonou"]
        assert mairie.get(url(ong)).status_code == 404  # n'est plus dans sa liste


class TestSuspension:
    def test_reservee_a_l_admin_de_la_plateforme(self, admin_de, admin_plateforme, ong, parakou, creer_utilisateur, client_connecte):
        assert admin_de(parakou).post(url(ong, "suspendre"), {"motif": "Non"}, format="json").status_code == 403
        membre = creer_utilisateur(role=Utilisateur.Role.ORGANISATION, organisation=ong)

        reponse = admin_plateforme.post(url(ong, "suspendre"), {"motif": "Rapport non transmis."}, format="json")
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["donnees"]["statut_habilitation"] == "SUSPENDUE"
        acces = client_connecte(membre).get(reverse("signalements:signalement-list"))
        assert acces.json()["erreur"]["code"] == CodeErreur.ORGANISATION_NON_HABILITEE

        reponse = admin_plateforme.post(url(ong, "rehabiliter"))
        assert reponse.json()["donnees"]["statut_habilitation"] == "HABILITEE"
        assert client_connecte(membre).get(reverse("signalements:signalement-list")).status_code == 200

    def test_motif_obligatoire(self, admin_plateforme, ong):
        reponse = admin_plateforme.post(url(ong, "suspendre"), {"motif": ""}, format="json")
        assert "motif" in reponse.json()["erreur"]["details"]


class TestMembres:
    def membre(self, **surcharges):
        return {"telephone": "0195000015", "nom": "Dossou", "prenoms": "Mireille", "email": "M.Dossou@ong-eau.bj",
                "mot_de_passe": "EauPourTous!2026", **surcharges}

    def test_creer_puis_se_connecter(self, admin_de, ong, parakou, api_client):
        mairie = admin_de(parakou)
        reponse = mairie.post(url(ong, "membres"), self.membre(), format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["donnees"]["email"] == "m.dossou@ong-eau.bj"
        connexion = api_client.post(
            reverse("accounts:login"), {"email": "m.dossou@ong-eau.bj", "password": "EauPourTous!2026"}, format="json"
        )
        assert connexion.status_code == 200
        utilisateur = connexion.json()["donnees"]["utilisateur"]
        assert utilisateur["role"] == "ORGANISATION" and utilisateur["organisation"]["id"] == ong.pk
        assert [m["nom"] for m in mairie.get(url(ong, "membres")).json()["donnees"]] == ["Dossou"]

    def test_email_et_telephone_uniques(self, admin_de, ong, parakou):
        mairie = admin_de(parakou)
        mairie.post(url(ong, "membres"), self.membre(), format="json")
        doublon = mairie.post(url(ong, "membres"), self.membre(telephone="0195000016"), format="json")
        assert doublon.json()["erreur"]["code"] == CodeErreur.EMAIL_DEJA_UTILISE
        doublon = mairie.post(url(ong, "membres"), self.membre(email="autre@ong.bj"), format="json")
        assert doublon.json()["erreur"]["code"] == CodeErreur.TELEPHONE_DEJA_UTILISE

    def test_desactiver(self, admin_de, ong, parakou, client_connecte):
        mairie = admin_de(parakou)
        membre_id = mairie.post(url(ong, "membres"), self.membre(), format="json").json()["donnees"]["id"]
        reponse = mairie.patch(url(ong, "membre", membre_id=membre_id), {"actif": False}, format="json")
        assert reponse.status_code == 200 and reponse.json()["donnees"]["actif"] is False
        acces = client_connecte(Utilisateur.objects.get(pk=membre_id)).get(reverse("accounts:me"))
        assert acces.status_code == 403, acces.json()

    def test_membre_d_une_autre_organisation(self, admin_de, ong, parakou, creer_utilisateur):
        etranger = creer_utilisateur(role=Utilisateur.Role.ORGANISATION)
        reponse = admin_de(parakou).patch(url(ong, "membre", membre_id=etranger.pk), {"nom": "X"}, format="json")
        assert reponse.status_code == 404
