from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.medias.models import Media
from apps.referentiel.models import Secteur
from apps.suggestions import services
from apps.suggestions.models import Soutien, Suggestion, SuiviSuggestion
from apps.territoire.models import Arrondissement, Quartier

pytestmark = pytest.mark.django_db

URL = reverse("suggestions:suggestion-list")
ANNEE = timezone.localdate().year


def url(suggestion, action="detail"):
    return reverse(f"suggestions:suggestion-{action}", args=[suggestion.pk])


def ok(reponse, statut=200):
    assert reponse.status_code == statut, reponse.json()
    return reponse.json()


def erreur(reponse, code, statut):
    assert reponse.status_code == statut, reponse.json()
    assert reponse.json()["erreur"]["code"] == code, reponse.json()
    return reponse.json()["erreur"]


@pytest.fixture
def secteur():
    return Secteur.objects.create(nom="Cadre de vie", code="CADRE_VIE", pour_suggestion=True)


@pytest.fixture
def quartier(commune):
    arrondissement = Arrondissement.objects.create(commune=commune, nom="Abomey-Calavi", code="ABC")
    return Quartier.objects.create(arrondissement=arrondissement, nom="Zogbadjè", code="ZOG")


@pytest.fixture
def citoyen(creer_utilisateur):
    return creer_utilisateur(nom="Hounkpatin", prenoms="Afiavi")


@pytest.fixture
def voisin(creer_utilisateur):
    return creer_utilisateur(nom="Zinsou", prenoms="Codjo")


@pytest.fixture
def agent(creer_utilisateur):
    service = ServiceMunicipal.objects.create(nom="Marchés")
    return creer_utilisateur(role=Utilisateur.Role.AGENT, service=service, nom="Ahouansou", prenoms="Rodrigue")


@pytest.fixture
def creer(secteur):
    def _creer(auteur, **kwargs):
        options = {"titre": "Des bancs au marché", "description": "Les clients attendent debout.", "secteur": secteur, **kwargs}
        return services.creer_suggestion(auteur=auteur, **options)

    return _creer


@pytest.fixture
def suggestion(creer, citoyen):
    return creer(citoyen)


class TestCreation:
    def test_suggestion_recue_avec_reference(self, citoyen, client_connecte, secteur, quartier, televerser):
        photo = televerser(citoyen)
        corps = ok(client_connecte(citoyen).post(URL, {
            "titre": "Des bancs au marché", "description": "Les clients attendent debout.",
            "secteur": secteur.pk, "quartier": quartier.pk, "medias": [str(photo.id)],
        }, format="json"), 201)

        assert corps["message"] == f"Suggestion envoyée. Votre référence : SUG-{ANNEE}-00001."
        donnees = corps["donnees"]
        assert (donnees["nb_soutiens"], donnees["je_soutiens"]) == (0, False)
        assert "statut" not in donnees and "est_pertinente" not in donnees
        assert donnees["quartier"]["nom"] == "Zogbadjè"
        assert donnees["historique"] == []
        assert not Suggestion.objects.get().est_pertinente
        photo.refresh_from_db()
        assert photo.statut == Media.Statut.ATTACHE

    def test_sans_quartier_pour_toute_la_commune_et_sans_photo(self, citoyen, client_connecte, secteur):
        donnees = ok(client_connecte(citoyen).post(URL, {
            "titre": "Journée de salubrité", "description": "Le premier samedi du mois.", "secteur": secteur.pk,
        }, format="json"), 201)["donnees"]
        assert donnees["quartier"] is None and donnees["medias"] == []

    @pytest.mark.parametrize("champ", ["titre", "description", "secteur"])
    def test_champs_obligatoires(self, citoyen, client_connecte, secteur, champ):
        corps = {"titre": "T", "description": "D", "secteur": secteur.pk}
        del corps[champ]
        reponse = client_connecte(citoyen).post(URL, corps, format="json")
        assert champ in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_secteur_non_propose_pour_suggestion(self, citoyen, client_connecte):
        autre = Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_signalement=True)
        reponse = client_connecte(citoyen).post(URL, {"titre": "T", "description": "D", "secteur": autre.pk}, format="json")
        assert "secteur" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_quatre_photos_refusees(self, citoyen, client_connecte, secteur, televerser):
        ids = [str(televerser(citoyen).id) for _ in range(4)]
        reponse = client_connecte(citoyen).post(URL, {"titre": "T", "description": "D", "secteur": secteur.pk, "medias": ids}, format="json")
        erreur(reponse, CodeErreur.MEDIAS_NON_CONFORMES, 400)
        assert not Suggestion.objects.exists()

    def test_video_refusee(self, citoyen, client_connecte, secteur, televerser):
        video = televerser(citoyen, Media.Type.VIDEO)
        reponse = client_connecte(citoyen).post(
            URL, {"titre": "T", "description": "D", "secteur": secteur.pk, "medias": [str(video.id)]}, format="json"
        )
        erreur(reponse, CodeErreur.MEDIAS_NON_CONFORMES, 400)

    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ORGANISATION])
    def test_reserve_aux_citoyens(self, creer_utilisateur, client_connecte, secteur, role):
        reponse = client_connecte(creer_utilisateur(role=role)).post(
            URL, {"titre": "T", "description": "D", "secteur": secteur.pk}, format="json"
        )
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE, 403)


class TestSoutiens:
    def test_soutenir_puis_retirer(self, suggestion, voisin, client_connecte):
        client = client_connecte(voisin)
        corps = ok(client.post(url(suggestion, "soutenir")))
        assert corps == {"succes": True, "message": "Merci pour votre soutien !", "donnees": {"nb_soutiens": 1, "je_soutiens": True}}
        assert client.get(url(suggestion)).json()["donnees"]["je_soutiens"] is True

        corps = ok(client.delete(url(suggestion, "soutenir")))
        assert corps["donnees"] == {"nb_soutiens": 0, "je_soutiens": False}
        assert not Soutien.objects.exists()

    def test_soutenir_deux_fois_ne_compte_qu_une_fois(self, suggestion, voisin, client_connecte):
        client = client_connecte(voisin)
        ok(client.post(url(suggestion, "soutenir")))
        assert ok(client.post(url(suggestion, "soutenir")))["donnees"]["nb_soutiens"] == 1
        assert Soutien.objects.count() == 1

    def test_retirer_sans_soutenir_est_sans_effet(self, suggestion, voisin, client_connecte):
        assert ok(client_connecte(voisin).delete(url(suggestion, "soutenir")))["donnees"]["nb_soutiens"] == 0

    def test_plusieurs_citoyens(self, suggestion, creer_utilisateur, client_connecte):
        for _ in range(3):
            ok(client_connecte(creer_utilisateur()).post(url(suggestion, "soutenir")))
        suggestion.refresh_from_db()
        assert suggestion.nb_soutiens == 3 == suggestion.soutiens.count()

    def test_pas_sa_propre_suggestion(self, suggestion, citoyen, client_connecte):
        erreur(client_connecte(citoyen).post(url(suggestion, "soutenir")), CodeErreur.SOUTIEN_PROPRE_SUGGESTION, 400)

    def test_toujours_possible_meme_marquee_pertinente(self, suggestion, voisin, client_connecte):
        services.marquer_pertinente(suggestion)
        assert ok(client_connecte(voisin).post(url(suggestion, "soutenir")))["donnees"]["nb_soutiens"] == 1

    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ORGANISATION])
    def test_reserve_aux_citoyens(self, suggestion, creer_utilisateur, client_connecte, role):
        erreur(client_connecte(creer_utilisateur(role=role)).post(url(suggestion, "soutenir")), CodeErreur.PERMISSION_REFUSEE, 403)

    def test_un_soutien_par_citoyen_en_base(self, suggestion, voisin):
        Soutien.objects.create(suggestion=suggestion, citoyen=voisin)
        with pytest.raises(IntegrityError), transaction.atomic():
            Soutien.objects.create(suggestion=suggestion, citoyen=voisin)

    def test_suggestion_inconnue(self, voisin, client_connecte):
        reponse = client_connecte(voisin).post(reverse("suggestions:suggestion-soutenir", args=[999999]))
        erreur(reponse, CodeErreur.RESSOURCE_INTROUVABLE, 404)


@pytest.mark.django_db(transaction=True)
def test_soutiens_simultanes_comptes_exactement(creer_utilisateur, secteur):
    """Des soutiens envoyés en même temps ne doivent ni se perdre ni compter double."""
    auteur = creer_utilisateur()
    suggestion = services.creer_suggestion(auteur=auteur, titre="T", description="D", secteur=secteur)
    citoyens = [creer_utilisateur() for _ in range(8)]

    def soutenir(citoyen):
        try:
            services.soutenir(suggestion, citoyen)
            services.soutenir(suggestion, citoyen)  # renvoi : sans effet
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=8) as executeur:
        list(executeur.map(soutenir, citoyens))
    suggestion.refresh_from_db()
    assert suggestion.nb_soutiens == 8 == suggestion.soutiens.count()


class TestPertinence:
    def test_cocher_puis_decocher(self, suggestion, agent, client_connecte):
        client = client_connecte(agent)
        corps = ok(client.post(url(suggestion, "pertinente")))
        assert corps["donnees"] == {"est_pertinente": True}
        assert corps["message"] == "Suggestion marquée comme pertinente."
        suggestion.refresh_from_db()
        assert suggestion.est_pertinente

        corps = ok(client.delete(url(suggestion, "pertinente")))
        assert corps["donnees"] == {"est_pertinente": False}
        suggestion.refresh_from_db()
        assert not suggestion.est_pertinente

    def test_sans_effet_si_deja_dans_l_etat_demande(self, suggestion, agent, client_connecte):
        client = client_connecte(agent)
        ok(client.post(url(suggestion, "pertinente")))
        assert ok(client.post(url(suggestion, "pertinente")))["donnees"] == {"est_pertinente": True}
        ok(client.delete(url(suggestion, "pertinente")))
        assert ok(client.delete(url(suggestion, "pertinente")))["donnees"] == {"est_pertinente": False}

    def test_admin_mairie_autorise(self, suggestion, creer_utilisateur, client_connecte):
        ok(client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE)).post(url(suggestion, "pertinente")))

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    @pytest.mark.parametrize("methode", ["post", "delete"])
    def test_reserve_a_la_mairie(self, suggestion, creer_utilisateur, client_connecte, role, methode):
        reponse = getattr(client_connecte(creer_utilisateur(role=role)), methode)(url(suggestion, "pertinente"))
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE, 403)
        suggestion.refresh_from_db()
        assert not suggestion.est_pertinente

    def test_la_mairie_filtre_les_pertinentes(self, creer, citoyen, agent, client_connecte):
        retenue, autre = creer(citoyen, titre="Retenue"), creer(citoyen, titre="Autre")
        services.marquer_pertinente(retenue)
        client = client_connecte(agent)
        donnees = client.get(URL, {"est_pertinente": "true"}).json()["donnees"]
        assert [(d["id"], d["est_pertinente"]) for d in donnees] == [(retenue.pk, True)]
        assert [d["id"] for d in client.get(URL, {"est_pertinente": "false"}).json()["donnees"]] == [autre.pk]

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_jamais_visible_ni_filtrable_hors_mairie(self, creer, citoyen, creer_utilisateur, client_connecte, role):
        retenue = creer(citoyen)
        creer(citoyen)
        services.marquer_pertinente(retenue)
        client = client_connecte(creer_utilisateur(role=role))
        # Le filtre est ignoré : on ne peut pas deviner les suggestions cochées.
        donnees = client.get(URL, {"est_pertinente": "true"}).json()["donnees"]
        assert len(donnees) == 2
        assert all("est_pertinente" not in d for d in donnees)
        assert "est_pertinente" not in client.get(url(retenue)).json()["donnees"]

    def test_suggestion_inconnue(self, agent, client_connecte):
        reponse = client_connecte(agent).post(reverse("suggestions:suggestion-pertinente", args=[999999]))
        erreur(reponse, CodeErreur.RESSOURCE_INTROUVABLE, 404)

    def test_plus_d_endpoint_changer_statut(self, suggestion, agent, client_connecte):
        assert client_connecte(agent).post(f"/api/v1/suggestions/{suggestion.pk}/changer-statut/", {}, format="json").status_code == 404


class TestReponses:
    def test_reponse_officielle(self, suggestion, agent, voisin, client_connecte):
        corps = ok(client_connecte(agent).post(url(suggestion, "repondre"), {"commentaire": "Prévu au budget."}, format="json"), 201)
        assert corps["message"] == "Réponse publiée."
        suggestion.refresh_from_db()
        assert (suggestion.reponse_officielle, suggestion.repondu_par) == ("Prévu au budget.", agent)
        assert suggestion.repondu_le is not None
        vue = client_connecte(voisin).get(url(suggestion)).json()["donnees"]
        assert vue["reponse_officielle"] == "Prévu au budget." and vue["a_reponse"] is True
        assert "repondu_par" not in vue

    def test_nouvelle_reponse_remplace_l_ancienne(self, suggestion, agent):
        services.repondre(suggestion, par=agent, commentaire="Première réponse.")
        services.repondre(suggestion, par=agent, commentaire="Réponse corrigée.")
        suggestion.refresh_from_db()
        assert suggestion.reponse_officielle == "Réponse corrigée."
        assert suggestion.suivis.filter(type_evenement="REPONSE").count() == 2

    def test_note_interne(self, suggestion, agent, voisin, client_connecte):
        corps = ok(client_connecte(agent).post(url(suggestion, "repondre"), {"commentaire": "Voir le devis.", "interne": True}, format="json"), 201)
        assert corps["donnees"]["historique"][-1]["visible_citoyen"] is False
        suggestion.refresh_from_db()
        assert suggestion.reponse_officielle == ""
        assert "Voir le devis." not in str(client_connecte(voisin).get(url(suggestion)).json())

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_reserve_a_la_mairie(self, suggestion, creer_utilisateur, client_connecte, role):
        client = client_connecte(creer_utilisateur(role=role))
        erreur(client.post(url(suggestion, "repondre"), {"commentaire": "x"}, format="json"), CodeErreur.PERMISSION_REFUSEE, 403)

    def test_note_interne_jamais_visible_en_base(self, suggestion, agent):
        with pytest.raises(IntegrityError), transaction.atomic():
            SuiviSuggestion.objects.create(suggestion=suggestion, type_evenement="NOTE_INTERNE", visible_citoyen=True, auteur=agent)


class TestConsultation:
    def test_visibilite_de_l_auteur(self, suggestion, citoyen, voisin, agent, creer_utilisateur, client_connecte):
        def auteur(utilisateur):
            return client_connecte(utilisateur).get(URL).json()["donnees"][0]["auteur"]

        assert auteur(voisin) == {"nom_affiche": "Afiavi H.", "id": None, "nom": None, "prenoms": None, "telephone": None}
        assert auteur(citoyen)["telephone"] == str(citoyen.telephone)
        assert auteur(agent)["telephone"] == str(citoyen.telephone)
        assert auteur(creer_utilisateur(role=Utilisateur.Role.ORGANISATION)) is None

    def test_tri_par_soutiens_et_je_soutiens(self, creer, citoyen, voisin, client_connecte, creer_utilisateur):
        peu, beaucoup = creer(citoyen, titre="Peu"), creer(citoyen, titre="Beaucoup")
        services.soutenir(beaucoup, voisin)
        services.soutenir(beaucoup, creer_utilisateur())
        services.soutenir(peu, creer_utilisateur())
        donnees = client_connecte(voisin).get(URL, {"tri": "-nb_soutiens"}).json()["donnees"]
        assert [(d["titre"], d["nb_soutiens"], d["je_soutiens"]) for d in donnees] == [("Beaucoup", 2, True), ("Peu", 1, False)]

    def test_filtres(self, creer, citoyen, voisin, client_connecte, quartier):
        commune_entiere, locale = creer(citoyen), creer(citoyen, quartier=quartier)
        client = client_connecte(voisin)

        def ids(**params):
            return [d["id"] for d in client.get(URL, params).json()["donnees"]]

        assert ids(quartier=quartier.pk) == [locale.pk]
        assert ids(recherche=locale.reference) == [locale.pk]
        assert set(ids()) == {commune_entiere.pk, locale.pk}

    def test_les_citoyens_ne_voient_pas_de_statut(self, suggestion, voisin, client_connecte):
        assert "statut" not in client_connecte(voisin).get(URL).json()["donnees"][0]
        assert "statut" not in client_connecte(voisin).get(url(suggestion)).json()["donnees"]

    def test_liste_paginee_avec_miniatures(self, citoyen, voisin, client_connecte, secteur, televerser):
        services.creer_suggestion(auteur=citoyen, titre="T", description="D", secteur=secteur, medias_ids=[televerser(citoyen).id])
        corps = client_connecte(voisin).get(URL).json()
        assert corps["pagination"]["total"] == 1
        assert set(corps["donnees"][0]["medias"][0]) == {"id", "type", "miniature", "duree_secondes"}
        assert "description" not in corps["donnees"][0]

    def test_nombre_de_requetes_constant(self, creer, citoyen, voisin, client_connecte):
        client = client_connecte(voisin)
        creer(citoyen)

        def compter():
            with CaptureQueriesContext(connection) as requetes:
                client.get(URL)
            return len(requetes)

        avant = compter()
        for _ in range(5):
            services.soutenir(creer(citoyen), voisin)
        assert compter() == avant

    def test_non_authentifie(self, api_client):
        assert api_client.get(URL).status_code == 401
