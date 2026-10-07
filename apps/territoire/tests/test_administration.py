from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.territoire.models import Arrondissement, Commune, Quartier

pytestmark = pytest.mark.django_db

URL_COMMUNES = reverse("territoire:communes")
URL_ARRONDISSEMENTS = reverse("territoire:arrondissements")
URL_QUARTIERS = reverse("territoire:quartiers")
URL_IMPORT = reverse("territoire:quartiers-import")

PARAKOU = {
    "nom": "Parakou", "code": "PKO", "departement": "Borgou",
    "lat_min": "9.232900", "lat_max": "9.441900", "lng_min": "2.480800", "lng_max": "2.771800",
}


@pytest.fixture
def admin(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))


@pytest.fixture
def agent(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur(role=Utilisateur.Role.AGENT))


@pytest.fixture
def citoyen(creer_utilisateur, client_connecte, parakou):
    return client_connecte(creer_utilisateur(commune=parakou))


@pytest.fixture
def parakou():
    return Commune.objects.create(**PARAKOU)


@pytest.fixture
def premier(parakou):
    return Arrondissement.objects.create(commune=parakou, nom="1er arrondissement", code="PKO-1")


class TestCommune:
    def test_creer(self, admin):
        reponse = admin.post(URL_COMMUNES, PARAKOU, format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["message"] == "Commune « Parakou » créée."
        assert Commune.objects.get().contient(Decimal("9.34"), Decimal("2.62"))

    def test_emprise_incoherente(self, admin):
        reponse = admin.post(URL_COMMUNES, {**PARAKOU, "lat_min": "9.5"}, format="json")
        assert reponse.json()["erreur"]["details"] == {"lat_max": ["Doit être supérieur à lat_min."]}

    def test_modifier_l_emprise(self, admin, parakou):
        url = reverse("territoire:commune-detail", args=[parakou.pk])
        assert admin.patch(url, {"lat_max": "9.5"}, format="json").status_code == 200
        assert admin.patch(url, {"lat_max": "9.0"}, format="json").status_code == 400

    def test_liste_publique_pour_l_inscription(self, api_client, parakou):
        reponse = api_client.get(URL_COMMUNES)
        assert reponse.status_code == 200
        assert [c["code"] for c in reponse.json()["donnees"]] == ["PKO"]

    def test_seul_l_admin_de_la_plateforme_ajoute_une_commune(self, creer_utilisateur, client_connecte, parakou):
        admin_parakou = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, commune=parakou))
        reponse = admin_parakou.post(URL_COMMUNES, {**PARAKOU, "code": "COT", "nom": "Cotonou"}, format="json")
        assert reponse.status_code == 403
        url = reverse("territoire:commune-detail", args=[parakou.pk])
        assert admin_parakou.patch(url, {"lat_max": "9.5"}, format="json").status_code == 200

    def test_creation_reservee_aux_admins(self, agent):
        assert agent.post(URL_COMMUNES, PARAKOU, format="json").status_code == 403


class TestArrondissements:
    def test_commune_par_defaut(self, admin, parakou):
        reponse = admin.post(URL_ARRONDISSEMENTS, {"nom": "2e arrondissement", "code": "PKO-2"}, format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["donnees"]["commune"] == parakou.pk

    def test_commune_obligatoire_s_il_y_en_a_plusieurs(self, admin, parakou):
        Commune.objects.create(**{**PARAKOU, "code": "AUTRE", "nom": "Autre"})
        reponse = admin.post(URL_ARRONDISSEMENTS, {"nom": "2e arrondissement"}, format="json")
        assert "commune" in reponse.json()["erreur"]["details"]

    def test_nom_unique_dans_la_commune(self, admin, premier):
        reponse = admin.post(URL_ARRONDISSEMENTS, {"nom": "1ER ARRONDISSEMENT"}, format="json")
        assert reponse.json()["erreur"]["details"] == {"nom": ["Cet arrondissement existe déjà dans cette commune."]}

    def test_liste_pour_tous(self, citoyen, premier):
        assert [a["nom"] for a in citoyen.get(URL_ARRONDISSEMENTS).json()["donnees"]] == ["1er arrondissement"]


class TestQuartiers:
    def test_creer(self, admin, premier):
        reponse = admin.post(URL_QUARTIERS, {
            "arrondissement": premier.pk, "nom": "Banikanni", "code": "BAN",
            "latitude_centre": "9.324070", "longitude_centre": "2.647370",
        }, format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["donnees"]["arrondissement"] == {"id": premier.pk, "nom": "1er arrondissement"}

    @pytest.mark.parametrize(
        "centre, attendu",
        [
            ({"latitude_centre": "9.32"}, "vont ensemble"),
            ({"latitude_centre": "6.40", "longitude_centre": "2.34"}, "hors de l'emprise de Parakou"),
        ],
    )
    def test_centre_invalide(self, admin, premier, centre, attendu):
        reponse = admin.post(URL_QUARTIERS, {"arrondissement": premier.pk, "nom": "Banikanni", **centre}, format="json")
        assert attendu in reponse.json()["erreur"]["details"]["latitude_centre"][0]

    def test_nom_unique_dans_l_arrondissement(self, admin, premier):
        Quartier.objects.create(arrondissement=premier, nom="Banikanni", code="BAN")
        reponse = admin.post(URL_QUARTIERS, {"arrondissement": premier.pk, "nom": "banikanni"}, format="json")
        assert reponse.json()["erreur"]["details"]["nom"] == ["Ce quartier existe déjà dans cet arrondissement."]

    def test_desactiver(self, admin, citoyen, premier):
        quartier = Quartier.objects.create(arrondissement=premier, nom="Banikanni", code="BAN")
        url = reverse("territoire:quartier-detail", args=[quartier.pk])
        assert admin.patch(url, {"actif": False}, format="json").json()["donnees"]["actif"] is False
        assert citoyen.get(URL_QUARTIERS).json()["donnees"] == []
        assert citoyen.get(url).status_code == 404
        assert admin.get(URL_QUARTIERS, {"actif": "false"}).json()["donnees"][0]["nom"] == "Banikanni"

    def test_le_champ_actif_est_reserve_a_la_mairie(self, citoyen, premier):
        Quartier.objects.create(arrondissement=premier, nom="Banikanni", code="BAN")
        assert "actif" not in citoyen.get(URL_QUARTIERS).json()["donnees"][0]

    def test_creation_reservee_aux_admins(self, agent, premier):
        assert agent.post(URL_QUARTIERS, {"arrondissement": premier.pk, "nom": "X"}, format="json").status_code == 403


class TestImportQuartiers:
    def envoyer(self, client, contenu, **options):
        fichier = SimpleUploadedFile("quartiers.csv", contenu.encode(), content_type="text/csv")
        return client.post(URL_IMPORT, {"fichier": fichier, **options}, format="multipart")

    def test_import_dans_la_commune_par_defaut(self, admin, parakou):
        reponse = self.envoyer(admin, (
            "arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude\n"
            "PKO-1;1er arrondissement;BAN;Banikanni;9,32407;2,64737\n"
            "PKO-1;1er arrondissement;KPE;Kpébié;;\n"
            "PKO-2;2e arrondissement;GAH;Gah;;\n"
        ))
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["donnees"] == {
            "arrondissements_crees": 2, "crees": 3, "mis_a_jour": 0, "desactives": 0, "simulation": False,
        }
        assert Quartier.objects.get(nom="Banikanni").latitude_centre == Decimal("9.324070")

    def test_lignes_en_erreur(self, admin, parakou):
        reponse = self.envoyer(admin, (
            "arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude\n"
            "PKO-1;1er arrondissement;TOU;Tourou;2.54397;9.34531\n"
        ))
        lignes = reponse.json()["erreur"]["details"]["lignes"]
        assert lignes == ["Ligne 2 : le centre de « Tourou » (2.543970, 9.345310) est hors de l'emprise de Parakou."]
        assert not Quartier.objects.exists()

    def test_commune_a_preciser_s_il_y_en_a_plusieurs(self, admin, parakou):
        autre = Commune.objects.create(**{**PARAKOU, "code": "AUTRE", "nom": "Autre"})
        contenu = "arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude\nA;Centre;Q;Quartier;;\n"
        assert "commune" in self.envoyer(admin, contenu).json()["erreur"]["details"]
        assert self.envoyer(admin, contenu, commune=autre.pk).status_code == 200
        assert Arrondissement.objects.get().commune == autre
