from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.referentiel.models import Secteur
from apps.signalements import services
from apps.signalements.models import Signalement

pytestmark = pytest.mark.django_db

URL_LISTE = reverse("signalements:signalement-list")
URL_MES = reverse("signalements:signalement-mes-signalements")
CHAMPS_MAIRIE = {"service_assigne", "agent_assigne"}


def url_detail(signalement):
    return reverse("signalements:signalement-detail", args=[signalement.pk])


def liste(client, **params):
    reponse = client.get(URL_LISTE, params)
    assert reponse.status_code == 200, reponse.json()
    return reponse.json()


@pytest.fixture
def autre_citoyen(creer_utilisateur):
    return creer_utilisateur(nom="Zinsou", prenoms="Codjo")


@pytest.fixture
def organisation(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.ORGANISATION)


class TestVisibiliteDeLAuteur:
    """Les citoyens restent anonymes : seul l'auteur voit son identité, la mairie non plus."""

    def test_un_autre_citoyen_ne_voit_pas_l_auteur(self, creer_signalement, citoyen, autre_citoyen, client_connecte):
        creer_signalement(citoyen)
        element = liste(client_connecte(autre_citoyen))["donnees"][0]
        assert element["auteur"] is None
        assert element["est_auteur"] is False
        assert not CHAMPS_MAIRIE & element.keys()

    def test_l_auteur_se_voit_en_entier(self, creer_signalement, citoyen, client_connecte):
        creer_signalement(citoyen)
        element = liste(client_connecte(citoyen))["donnees"][0]
        assert element["auteur"]["telephone"] == str(citoyen.telephone)
        assert element["est_auteur"] is True

    def test_la_mairie_ne_voit_pas_l_auteur(self, creer_signalement, citoyen, agent, client_connecte, voirie):
        creer_signalement(citoyen)
        client = client_connecte(agent)
        element = liste(client)["donnees"][0]
        assert element["auteur"] is None
        assert element["service_assigne"] == {"id": voirie.pk, "nom": voirie.nom}
        detail = client.get(url_detail(Signalement.objects.get())).json()["donnees"]
        assert detail["auteur"] is None
        # Le dépôt figure dans l'historique, sans le nom du citoyen.
        assert detail["historique"][0]["nouveau_statut"] == "SOUMIS"
        assert detail["historique"][0]["auteur_nom"] is None
        for trace in (str(citoyen.telephone), citoyen.nom, citoyen.prenoms):
            assert trace not in str(detail)

    def test_une_organisation_ne_voit_jamais_l_auteur(self, creer_signalement, citoyen, organisation, client_connecte):
        creer_signalement(citoyen)
        client = client_connecte(organisation)
        element = liste(client)["donnees"][0]
        assert element["auteur"] is None
        assert not CHAMPS_MAIRIE & element.keys()
        detail = client.get(url_detail(Signalement.objects.get())).json()["donnees"]
        assert detail["auteur"] is None
        assert str(citoyen.telephone) not in str(detail)


class TestListe:
    def test_pagination_et_miniatures_seulement(self, creer_signalement, citoyen, client_connecte):
        for _ in range(3):
            creer_signalement(citoyen)
        corps = liste(client_connecte(citoyen), taille=2)
        assert corps["pagination"]["total"] == 3 and corps["pagination"]["pages"] == 2
        assert len(corps["donnees"]) == 2
        media = corps["donnees"][0]["medias"][0]
        assert set(media) == {"id", "type", "miniature", "duree_secondes"}

    def test_plus_recent_d_abord(self, creer_signalement, citoyen, client_connecte):
        premier, second = creer_signalement(citoyen), creer_signalement(citoyen)
        refs = [e["reference"] for e in liste(client_connecte(citoyen))["donnees"]]
        assert refs == [second.reference, premier.reference]

    def test_filtres(self, creer_signalement, citoyen, agent, client_connecte, quartier):
        eclairage = Secteur.objects.create(nom="Éclairage", code="ECLAIRAGE", pour_signalement=True)
        a = creer_signalement(citoyen)
        b = creer_signalement(citoyen, secteur=eclairage)
        services.changer_statut(b, par=agent, statut="RECU")
        Signalement.objects.filter(pk=a.pk).update(cree_le=timezone.now() - timedelta(days=10))
        client = client_connecte(citoyen)

        def refs(**params):
            return {e["reference"] for e in liste(client, **params)["donnees"]}

        assert refs(statut="RECU") == {b.reference}
        assert refs(secteur=eclairage.pk) == {b.reference}
        assert refs(quartier=quartier.pk) == {a.reference, b.reference}
        aujourd_hui = timezone.localdate().isoformat()
        assert refs(date_debut=aujourd_hui) == {b.reference}
        assert refs(date_fin=(timezone.localdate() - timedelta(days=5)).isoformat()) == {a.reference}

    def test_recherche(self, creer_signalement, citoyen, client_connecte):
        cible = creer_signalement(citoyen, titre="Caniveau bouché")
        creer_signalement(citoyen)
        client = client_connecte(citoyen)
        assert [e["id"] for e in liste(client, recherche="caniveau")["donnees"]] == [cible.pk]
        assert [e["id"] for e in liste(client, recherche=cible.reference)["donnees"]] == [cible.pk]

    def test_non_authentifie(self, api_client):
        assert api_client.get(URL_LISTE).status_code == 401


class TestMesSignalements:
    def test_seulement_les_miens(self, creer_signalement, citoyen, autre_citoyen, client_connecte):
        mien = creer_signalement(citoyen)
        creer_signalement(autre_citoyen)
        corps = client_connecte(citoyen).get(URL_MES).json()
        assert [e["id"] for e in corps["donnees"]] == [mien.pk]
        assert corps["pagination"]["total"] == 1

    def test_reserve_aux_citoyens(self, agent, client_connecte):
        reponse = client_connecte(agent).get(URL_MES)
        assert reponse.status_code == 403
        assert reponse.json()["erreur"]["code"] == CodeErreur.PERMISSION_REFUSEE


class TestDetail:
    @pytest.fixture
    def signalement(self, creer_signalement, citoyen, agent):
        signalement = creer_signalement(citoyen)
        services.repondre(signalement, par=agent, commentaire="Merci, c'est noté.")
        services.repondre(signalement, par=agent, commentaire="Voir avec la SBEE.", interne=True)
        return signalement

    def test_le_citoyen_ne_voit_pas_les_notes_internes(self, signalement, autre_citoyen, client_connecte):
        historique = client_connecte(autre_citoyen).get(url_detail(signalement)).json()["donnees"]["historique"]
        assert [e["type_evenement"] for e in historique] == ["CHANGEMENT_STATUT", "REPONSE"]
        assert historique[1]["par_la_mairie"] is True
        assert "auteur_nom" not in historique[1] and "visible_citoyen" not in historique[1]
        assert "SBEE" not in str(historique)

    def test_l_organisation_ne_voit_pas_les_notes_internes(self, signalement, organisation, client_connecte):
        historique = client_connecte(organisation).get(url_detail(signalement)).json()["donnees"]["historique"]
        assert "NOTE_INTERNE" not in [e["type_evenement"] for e in historique]

    def test_la_mairie_voit_tout_l_historique(self, signalement, agent, client_connecte):
        historique = client_connecte(agent).get(url_detail(signalement)).json()["donnees"]["historique"]
        assert [e["type_evenement"] for e in historique] == ["CHANGEMENT_STATUT", "REPONSE", "NOTE_INTERNE"]
        assert historique[2]["auteur_nom"] == "Rodrigue Ahouansou"
        assert historique[2]["visible_citoyen"] is False

    def test_fichiers_complets_dans_le_detail(self, signalement, citoyen, client_connecte):
        donnees = client_connecte(citoyen).get(url_detail(signalement)).json()["donnees"]
        assert donnees["medias"][0]["fichier"].startswith("http://testserver/media/")
        assert donnees["description_texte"] == "Plus de lumière depuis une semaine."
        assert donnees["doublon_de"] is None

    def test_signalement_inconnu(self, citoyen, client_connecte):
        reponse = client_connecte(citoyen).get(reverse("signalements:signalement-detail", args=[999999]))
        assert reponse.status_code == 404
        assert reponse.json()["erreur"]["code"] == CodeErreur.RESSOURCE_INTROUVABLE


class TestPerformance:
    def compter(self, client, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as requetes:
            assert client.get(url).status_code == 200
        return len(requetes)

    def test_liste_sans_requetes_en_cascade(self, creer_signalement, citoyen, agent, client_connecte):
        client = client_connecte(agent)
        creer_signalement(citoyen)
        avec_un = self.compter(client, URL_LISTE)
        for _ in range(5):
            creer_signalement(citoyen)
        assert self.compter(client, URL_LISTE) == avec_un

    def test_detail_sans_requetes_en_cascade(self, creer_signalement, citoyen, agent, client_connecte):
        client = client_connecte(agent)
        signalement = creer_signalement(citoyen)
        avant = self.compter(client, url_detail(signalement))
        for i in range(5):
            services.repondre(signalement, par=agent, commentaire=f"Réponse {i}")
        assert self.compter(client, url_detail(signalement)) == avant
