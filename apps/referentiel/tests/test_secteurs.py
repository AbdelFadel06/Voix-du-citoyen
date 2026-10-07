import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from apps.accounts.models import Organisation, ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.referentiel.models import Secteur
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

URL = reverse("referentiel:secteurs")


@pytest.fixture
def secteurs():
    voirie = ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie")
    return [
        Secteur.objects.create(
            nom="Voirie", code="VOIRIE", pour_signalement=True, ordre=2, service_par_defaut=voirie
        ),
        Secteur.objects.create(nom="Éclairage", code="ECLAIRAGE", pour_signalement=True, ordre=1),
        Secteur.objects.create(nom="Éducation", code="EDUCATION", pour_suggestion=True, ordre=1),
        Secteur.objects.create(nom="Ancienne", code="ANCIENNE", pour_signalement=True, actif=False),
    ]


class TestModele:
    def test_nom_et_code_uniques(self, secteurs):
        with pytest.raises(IntegrityError):
            Secteur.objects.create(nom="Voirie", code="AUTRE")

    def test_code_unique(self, secteurs):
        with pytest.raises(IntegrityError):
            Secteur.objects.create(nom="Autre", code="VOIRIE")

    @pytest.mark.parametrize("couleur", ["#1E88E5", "#abcdef", ""])
    def test_couleur_valide(self, couleur):
        Secteur(nom="X", code="X", couleur=couleur).full_clean()

    @pytest.mark.parametrize("couleur", ["bleu", "#12345", "1E88E5", "#GGGGGG"])
    def test_couleur_invalide(self, couleur):
        with pytest.raises(ValidationError) as exc:
            Secteur(nom="X", code="X", couleur=couleur).full_clean()
        assert "couleur" in exc.value.message_dict

    def test_secteurs_d_une_organisation(self, secteurs):
        organisation = Organisation.objects.create(
            nom="ONG Eau", type=Organisation.Type.ONG, numero_enregistrement="ONG-1"
        )
        organisation.secteurs.set(secteurs[:2])
        assert set(secteurs[0].organisations.all()) == {organisation}


class TestListe:
    def test_non_authentifie(self, api_client):
        reponse = api_client.get(URL)
        assert reponse.status_code == 401
        assert reponse.json()["erreur"]["code"] == CodeErreur.NON_AUTHENTIFIE

    def test_actives_triees_par_ordre_puis_nom_sans_pagination(
        self, secteurs, creer_utilisateur, client_connecte
    ):
        corps = client_connecte(creer_utilisateur()).get(URL).json()
        assert corps["succes"] is True
        assert "pagination" not in corps
        assert [c["code"] for c in corps["donnees"]] == ["ECLAIRAGE", "EDUCATION", "VOIRIE"]

    def test_champs_exposes(self, secteurs, creer_utilisateur, client_connecte):
        secteur = client_connecte(creer_utilisateur()).get(URL).json()["donnees"][0]
        assert set(secteur) == {
            "id", "nom", "code", "description", "icone", "couleur",
            "pour_signalement", "pour_suggestion", "pour_realisation", "ordre",
        }

    def test_filtre_par_usage(self, secteurs, creer_utilisateur, client_connecte):
        client = client_connecte(creer_utilisateur())
        signalement = client.get(URL, {"pour_signalement": "true"}).json()["donnees"]
        suggestion = client.get(URL, {"pour_suggestion": "true"}).json()["donnees"]
        assert [c["code"] for c in signalement] == ["ECLAIRAGE", "VOIRIE"]
        assert [c["code"] for c in suggestion] == ["EDUCATION"]

    @pytest.mark.parametrize("role", list(Utilisateur.Role))
    def test_accessible_a_tous_les_roles(self, secteurs, creer_utilisateur, client_connecte, role):
        assert client_connecte(creer_utilisateur(role=role)).get(URL).status_code == 200

    def test_creation_reservee_aux_admins(self, secteurs, creer_utilisateur, client_connecte):
        reponse = client_connecte(creer_utilisateur()).post(URL, {"nom": "X"}, format="json")
        assert reponse.status_code == 403
