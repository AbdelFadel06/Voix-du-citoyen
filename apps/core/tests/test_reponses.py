import pytest
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import INFOS_ERREURS, CodeErreur
from apps.core.exceptions import ErreurMetier

URL = "/api/v1/test/"


@pytest.fixture
def client_test(api_client, settings):
    settings.ROOT_URLCONF = "apps.core.tests.urls_test"
    return api_client


class TestSucces:
    def test_reponse_succes_avec_message_et_statut(self, client_test):
        reponse = client_test.get(URL + "succes/")
        assert reponse.status_code == 201
        assert reponse.json() == {
            "succes": True,
            "message": "Opération réussie.",
            "donnees": {"valeur": 1},
        }

    def test_donnees_brutes_enveloppees_automatiquement(self, client_test):
        assert client_test.get(URL + "brut/").json() == {
            "succes": True,
            "message": None,
            "donnees": {"valeur": 1},
        }

    def test_204_sans_contenu(self, client_test):
        reponse = client_test.post(URL + "validation/", {"telephone": "x", "age": 3}, format="json")
        assert reponse.status_code == 204
        assert reponse.content == b""


class TestPagination:
    def test_premiere_page(self, client_test):
        corps = client_test.get(URL + "liste/").json()
        assert corps["succes"] is True
        assert corps["message"] is None
        assert [e["valeur"] for e in corps["donnees"]] == list(range(1, 21))
        pagination = corps["pagination"]
        assert {k: pagination[k] for k in ("total", "page", "pages", "taille")} == {
            "total": 45, "page": 1, "pages": 3, "taille": 20,
        }
        assert pagination["precedent"] is None
        assert pagination["suivant"].endswith("/api/v1/test/liste/?page=2")

    def test_page_et_taille_personnalisees(self, client_test):
        corps = client_test.get(URL + "liste/?page=2&taille=10").json()
        assert [e["valeur"] for e in corps["donnees"]] == list(range(11, 21))
        assert corps["pagination"]["pages"] == 5
        assert corps["pagination"]["taille"] == 10
        assert "page=3" in corps["pagination"]["suivant"]
        assert corps["pagination"]["precedent"] is not None

    def test_taille_plafonnee_a_100(self, client_test):
        assert client_test.get(URL + "liste/?taille=500").json()["pagination"]["taille"] == 100

    def test_page_inexistante(self, client_test):
        reponse = client_test.get(URL + "liste/?page=99")
        assert reponse.status_code == 404
        assert reponse.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE


class TestErreurs:
    def test_validation(self, client_test):
        reponse = client_test.post(URL + "validation/", {"age": "abc"}, format="json")
        assert reponse.status_code == 400
        corps = reponse.json()
        assert corps["succes"] is False
        assert corps["erreur"]["code"] == "VALIDATION_ERREUR"
        assert corps["erreur"]["message"] == "Certaines informations sont invalides."
        assert set(corps["erreur"]["details"]) == {"telephone", "age"}
        assert isinstance(corps["erreur"]["details"]["age"], list)

    def test_json_mal_forme(self, client_test):
        reponse = client_test.post(
            URL + "validation/", "{pas du json", content_type="application/json"
        )
        assert reponse.status_code == 400
        assert reponse.json()["erreur"]["code"] == "VALIDATION_ERREUR"

    def test_401_non_authentifie(self, client_test):
        reponse = client_test.get(URL + "admin/")
        assert reponse.status_code == 401
        assert reponse.json()["erreur"] == {
            "code": "NON_AUTHENTIFIE",
            "message": "Vous devez être connecté pour accéder à ce service.",
            "details": None,
        }

    def test_403_permission_refusee(self, client_test, creer_utilisateur, client_connecte):
        settings_client = client_connecte(creer_utilisateur(role=Utilisateur.Role.CITOYEN))
        reponse = settings_client.get(URL + "admin/")
        assert reponse.status_code == 403
        erreur = reponse.json()["erreur"]
        assert erreur["code"] == "PERMISSION_REFUSEE"
        assert erreur["message"] == "Action réservée aux administrateurs de la mairie."

    def test_404_dans_une_vue(self, client_test):
        reponse = client_test.get(URL + "introuvable/")
        assert reponse.status_code == 404
        assert reponse.json()["erreur"] == {
            "code": "RESSOURCE_INTROUVABLE",
            "message": "L'élément demandé est introuvable.",
            "details": None,
        }
        assert "interne" not in reponse.content.decode()

    def test_404_url_inconnue(self, api_client):
        reponse = api_client.get("/api/v1/nexiste-pas/")
        assert reponse.status_code == 404
        assert reponse["Content-Type"] == "application/json"
        assert reponse.json()["erreur"]["code"] == "RESSOURCE_INTROUVABLE"

    def test_405(self, client_test):
        reponse = client_test.delete(URL + "succes/")
        assert reponse.status_code == 405
        assert reponse.json()["erreur"]["code"] == "METHODE_NON_AUTORISEE"

    def test_429_avec_delai(self, client_test):
        assert client_test.get(URL + "limitee/").status_code == 200
        reponse = client_test.get(URL + "limitee/")
        assert reponse.status_code == 429
        erreur = reponse.json()["erreur"]
        assert erreur["code"] == "TROP_DE_REQUETES"
        assert 0 < erreur["details"]["attente_secondes"] <= 60
        assert "Réessayez dans" in erreur["message"]
        assert reponse["Retry-After"] == str(erreur["details"]["attente_secondes"])

    def test_500_sans_fuite_de_detail(self, client_test, caplog):
        reponse = client_test.get(URL + "plantage/")
        assert reponse.status_code == 500
        assert reponse.json() == {
            "succes": False,
            "erreur": {
                "code": "ERREUR_SERVEUR",
                "message": "Une erreur inattendue s'est produite. Veuillez réessayer plus tard.",
                "details": None,
            },
        }
        assert "secret123" not in reponse.content.decode()
        # La trace complète est bien journalisée.
        assert "secret123" in caplog.text
        assert "Traceback" in caplog.text

    def test_erreur_renvoyee_a_la_main_est_mise_au_format(self, client_test):
        reponse = client_test.get(URL + "manuelle/")
        assert reponse.status_code == 409
        assert reponse.json()["erreur"] == {
            "code": "CONFLIT",
            "message": "Cette action entre en conflit avec des données existantes.",
            "details": {"champ": ["déjà pris"]},
        }


class TestErreurMetier:
    def test_dans_une_vue(self, client_test):
        reponse = client_test.get(URL + "metier/")
        assert reponse.status_code == 409
        assert reponse.json()["erreur"] == {
            "code": "CONFLIT",
            "message": "Cette action entre en conflit avec des données existantes.",
            "details": {"reference": "SIG-2026-00001"},
        }

    def test_statut_et_message_par_defaut(self):
        exc = ErreurMetier(CodeErreur.OTP_EXPIRE)
        assert exc.status_code == 400
        assert exc.message == "Ce code a expiré. Demandez-en un nouveau."
        assert exc.details is None

    def test_message_et_statut_personnalises(self):
        exc = ErreurMetier(CodeErreur.OTP_INVALIDE, "Autre message.", status_code=422, details={"a": 1})
        assert (exc.message, exc.status_code, exc.details) == ("Autre message.", 422, {"a": 1})

    def test_code_inconnu_refuse(self):
        with pytest.raises(ValueError):
            ErreurMetier("CODE_INVENTE")

    def test_chaque_code_a_un_statut_et_un_message(self):
        assert set(INFOS_ERREURS) == set(CodeErreur)
        for code in CodeErreur:
            statut, message = INFOS_ERREURS[code]
            assert 400 <= statut < 600 and message
            assert code.value == code.value.upper()


class TestHorsEnveloppe:
    def test_schema_openapi_non_modifie(self, api_client):
        reponse = api_client.get(reverse("schema"), {"format": "json"})
        assert reponse.status_code == 200
        corps = reponse.json()
        assert "openapi" in corps and "succes" not in corps

    def test_documentation_accessible(self, api_client):
        assert api_client.get(reverse("docs")).status_code == 200

    def test_composants_documentes(self, api_client):
        composants = api_client.get(reverse("schema"), {"format": "json"}).json()["components"]["schemas"]
        assert {"ReponseErreur", "Erreur", "ReponseJetons", "ReponseSimple"} <= composants.keys()
        assert set(composants["CodeErreurEnum"]["enum"]) == {c.value for c in CodeErreur}
