import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.referentiel.models import Secteur
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

URL = reverse("referentiel:secteurs")
URL_IMPORT = reverse("referentiel:secteurs-import")


def url(secteur):
    return reverse("referentiel:secteur-detail", args=[secteur.pk])


def csv(contenu, nom="secteurs.csv", encodage="utf-8"):
    return SimpleUploadedFile(nom, contenu.encode(encodage), content_type="text/csv")


@pytest.fixture
def admin(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))


@pytest.fixture
def citoyen(creer_utilisateur, client_connecte):
    return client_connecte(creer_utilisateur())


@pytest.fixture
def voirie():
    return ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie et assainissement")


class TestCreationModification:
    def test_creer(self, admin, voirie):
        reponse = admin.post(URL, {
            "nom": "Voirie", "code": "voirie", "couleur": "#F57C00",
            "pour_signalement": True, "service_par_defaut": voirie.pk,
        }, format="json")
        assert reponse.status_code == 201, reponse.json()
        assert reponse.json()["message"] == "Secteur « Voirie » créé."
        donnees = reponse.json()["donnees"]
        assert donnees["code"] == "VOIRIE"
        assert donnees["service_par_defaut"] == {"id": voirie.pk, "nom": voirie.nom}
        assert donnees["actif"] is True

    def test_code_et_nom_uniques(self, admin):
        Secteur.objects.create(nom="Voirie", code="VOIRIE")
        reponse = admin.post(URL, {"nom": "Voirie", "code": "VOIRIE"}, format="json")
        assert reponse.status_code == 400
        details = reponse.json()["erreur"]["details"]
        assert details["code"] == ["Un secteur utilise déjà ce code."]
        assert details["nom"] == ["Un secteur porte déjà ce nom."]

    def test_couleur_invalide(self, admin):
        reponse = admin.post(URL, {"nom": "X", "code": "X", "couleur": "bleu"}, format="json")
        assert "couleur" in reponse.json()["erreur"]["details"]

    def test_modifier(self, admin):
        secteur = Secteur.objects.create(nom="Voirie", code="VOIRIE")
        reponse = admin.patch(url(secteur), {"ordre": 5, "pour_suggestion": True}, format="json")
        assert reponse.json()["message"] == "Secteur « Voirie » modifié."
        secteur.refresh_from_db()
        assert (secteur.ordre, secteur.pour_suggestion, secteur.nom) == (5, True, "Voirie")

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.AGENT, Utilisateur.Role.ORGANISATION])
    def test_reserve_aux_admins(self, creer_utilisateur, client_connecte, role):
        client = client_connecte(creer_utilisateur(role=role))
        secteur = Secteur.objects.create(nom="Voirie", code="VOIRIE")
        assert client.post(URL, {"nom": "X", "code": "X"}, format="json").status_code == 403
        assert client.patch(url(secteur), {"nom": "Y"}, format="json").status_code == 403
        assert client.post(URL_IMPORT, {"fichier": csv("code;nom\nA;B\n")}, format="multipart").status_code == 403


class TestDesactivation:
    def test_desactive_invisible_pour_les_citoyens(self, admin, citoyen):
        secteur = Secteur.objects.create(nom="Voirie", code="VOIRIE")
        admin.patch(url(secteur), {"actif": False}, format="json")
        assert citoyen.get(URL).json()["donnees"] == []
        assert citoyen.get(url(secteur)).status_code == 404
        # La mairie le voit encore, et peut filtrer les secteurs désactivés.
        assert [s["actif"] for s in admin.get(URL).json()["donnees"]] == [False]
        assert len(admin.get(URL, {"actif": "true"}).json()["donnees"]) == 0

    def test_champs_internes_caches_aux_citoyens(self, citoyen):
        Secteur.objects.create(nom="Voirie", code="VOIRIE")
        secteur = citoyen.get(URL).json()["donnees"][0]
        assert "actif" not in secteur and "service_par_defaut" not in secteur


class TestImport:
    def test_import(self, admin, voirie):
        reponse = admin.post(URL_IMPORT, {"fichier": csv(
            "code;nom;couleur;pour_signalement;service_par_defaut\n"
            "VOIRIE;Voirie;#F57C00;oui;Voirie et assainissement\n"
            "ECLAIRAGE;Éclairage public;;oui;\n"
        )}, format="multipart")
        assert reponse.status_code == 200, reponse.json()
        assert reponse.json()["donnees"] == {"crees": 2, "mis_a_jour": 0, "desactives": 0, "simulation": False}
        assert reponse.json()["message"] == "Import terminé : 2 secteur(s) créé(s), 0 mis à jour, 0 désactivé(s)."
        assert Secteur.objects.get(code="VOIRIE").service_par_defaut == voirie

    def test_simulation(self, admin):
        reponse = admin.post(URL_IMPORT, {"fichier": csv("code;nom\nVOIRIE;Voirie\n"), "simulation": True}, format="multipart")
        assert reponse.json()["donnees"]["simulation"] is True
        assert reponse.json()["message"].startswith("Simulation : 1 secteur(s) créé(s)")
        assert not Secteur.objects.exists()

    def test_fichier_refuse_avec_les_lignes_en_erreur(self, admin):
        reponse = admin.post(URL_IMPORT, {"fichier": csv(
            "code;nom;couleur;service_par_defaut\nVOIRIE;Voirie;bleu;\n;Sans code;;Fantôme\n"
        )}, format="multipart")
        assert reponse.status_code == 400
        erreur = reponse.json()["erreur"]
        assert erreur["code"] == CodeErreur.IMPORT_CSV_INVALIDE
        assert erreur["details"]["lignes"] == [
            "Ligne 2 : couleur « bleu » invalide (attendu #RRGGBB).",
            "Ligne 3 : « code » est vide.",
            "Ligne 3 : service « Fantôme » introuvable (créez-le d'abord).",
        ]
        assert not Secteur.objects.exists()

    def test_fichier_excel_windows(self, admin):
        reponse = admin.post(URL_IMPORT, {"fichier": csv("code;nom\nECLAIRAGE;Éclairage public\n", encodage="cp1252")}, format="multipart")
        assert reponse.status_code == 200
        assert Secteur.objects.get().nom == "Éclairage public"

    @pytest.mark.parametrize(
        "contenu, message",
        [("", "Fichier vide"), ("nom\nVoirie\n", "Colonnes manquantes : code"), ("code;nom\n", "aucune ligne de données")],
    )
    def test_fichiers_inutilisables(self, admin, contenu, message):
        fichier = SimpleUploadedFile("s.csv", contenu.encode() or b" ", content_type="text/csv")
        reponse = admin.post(URL_IMPORT, {"fichier": fichier}, format="multipart")
        assert reponse.status_code == 400
        assert message in reponse.json()["erreur"]["details"]["lignes"][0]

    def test_fichier_trop_gros(self, admin):
        gros = csv("code;nom\n" + "A;B\n" * 300_000)
        reponse = admin.post(URL_IMPORT, {"fichier": gros}, format="multipart")
        assert reponse.json()["erreur"]["code"] == CodeErreur.IMPORT_CSV_INVALIDE
        assert "1 Mo" in reponse.json()["erreur"]["message"]

    def test_desactiver_absents(self, admin):
        Secteur.objects.create(nom="Ancien", code="ANCIEN")
        reponse = admin.post(URL_IMPORT, {"fichier": csv("code;nom\nVOIRIE;Voirie\n"), "desactiver_absents": True}, format="multipart")
        assert reponse.json()["donnees"]["desactives"] == 1
        assert not Secteur.objects.get(code="ANCIEN").actif

    def test_fichier_obligatoire(self, admin):
        reponse = admin.post(URL_IMPORT, {}, format="multipart")
        assert "fichier" in reponse.json()["erreur"]["details"]
