from datetime import date
from pathlib import Path

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ServiceMunicipal, Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.medias.models import Media
from apps.realisations import services
from apps.realisations.models import Realisation, RealisationMedia
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.territoire.models import Arrondissement, Quartier
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

URL = reverse("realisations:realisation-list")
ANNEE = timezone.localdate().year


def url(realisation):
    return reverse("realisations:realisation-detail", args=[realisation.pk])


def ok(reponse, statut=200):
    assert reponse.status_code == statut, reponse.json()
    return reponse.json()


def erreur(reponse, code, statut):
    assert reponse.status_code == statut, reponse.json()
    assert reponse.json()["erreur"]["code"] == code, reponse.json()
    return reponse.json()["erreur"]


@pytest.fixture
def secteur():
    return Secteur.objects.create(nom="Voirie", code="VOIRIE", pour_realisation=True, pour_signalement=True)


@pytest.fixture
def quartier(commune):
    godomey = Arrondissement.objects.create(commune=commune, nom="Godomey", code="GOD")
    return Quartier.objects.create(arrondissement=godomey, nom="Togoudo", code="TOG")


@pytest.fixture
def agent(creer_utilisateur):
    service = ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie et assainissement")
    return creer_utilisateur(role=Utilisateur.Role.AGENT, service=service, nom="Ahouansou", prenoms="Rodrigue")


@pytest.fixture
def mairie(agent, client_connecte):
    return client_connecte(agent)


@pytest.fixture
def creer(agent, secteur, quartier):
    def _creer(**champs):
        options = {
            "titre": "Pavage de la rue de l'école",
            "description": "850 m de pavés et des caniveaux couverts.",
            "secteur": secteur,
            "quartiers": [quartier],
            **champs,
        }
        return services.creer_realisation(par=agent, **options)

    return _creer


def corps(secteur, quartier, **surcharges):
    return {
        "titre": "Pavage de la rue de l'école",
        "description": "850 m de pavés et des caniveaux couverts.",
        "secteur": secteur.pk,
        "quartiers": [quartier.pk],
        **surcharges,
    }


class TestVisibilite:
    def test_le_public_ne_voit_que_les_publiees(self, creer, api_client):
        publiee, _brouillon = creer(publie=True), creer()
        donnees = ok(api_client.get(URL))["donnees"]
        assert [d["id"] for d in donnees] == [publiee.pk]
        assert "publie" not in donnees[0]

    @pytest.mark.parametrize("role", [None, Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_brouillon_introuvable_hors_mairie(self, creer, creer_utilisateur, client_connecte, api_client, role):
        client = api_client if role is None else client_connecte(creer_utilisateur(role=role))
        erreur(client.get(url(creer())), CodeErreur.RESSOURCE_INTROUVABLE, 404)

    def test_la_mairie_voit_les_brouillons(self, creer, mairie, agent):
        brouillon = creer()
        donnees = ok(mairie.get(URL))["donnees"]
        assert [(d["id"], d["publie"]) for d in donnees] == [(brouillon.pk, False)]
        detail = ok(mairie.get(url(brouillon)))["donnees"]
        assert detail["cree_par"] == {"id": agent.pk, "nom": "Ahouansou", "prenoms": "Rodrigue"}

    def test_le_public_ne_voit_pas_l_agent(self, creer, api_client):
        detail = ok(api_client.get(url(creer(publie=True))))["donnees"]
        assert "cree_par" not in detail and "Ahouansou" not in str(detail)

    def test_filtre_brouillons_reserve_a_la_mairie(self, creer, mairie, creer_utilisateur, client_connecte):
        publiee, brouillon = creer(publie=True), creer()
        assert [d["id"] for d in ok(mairie.get(URL, {"publie": "false"}))["donnees"]] == [brouillon.pk]
        citoyen = client_connecte(creer_utilisateur())
        assert [d["id"] for d in ok(citoyen.get(URL, {"publie": "false"}))["donnees"]] == [publiee.pk]

    def test_filtres(self, creer, api_client, quartier, commune):
        autre_quartier = Quartier.objects.create(arrondissement=quartier.arrondissement, nom="Cococodji", code="COC")
        a = creer(publie=True, statut=Realisation.Statut.TERMINEE)
        b = creer(publie=True, quartiers=[autre_quartier, quartier])

        def ids(**params):
            return {d["id"] for d in ok(api_client.get(URL, params))["donnees"]}

        assert ids(statut="TERMINEE") == {a.pk}
        assert ids(quartier=autre_quartier.pk) == {b.pk}
        assert ids(quartier=quartier.pk) == {a.pk, b.pk}
        assert ids(recherche=a.reference) == {a.pk}


class TestCreation:
    def test_brouillon_avec_medias_et_liens(self, mairie, agent, secteur, quartier, televerser, creer_utilisateur):
        photo, video = televerser(agent), televerser(agent, Media.Type.VIDEO)
        citoyen = creer_utilisateur()
        dossier, _ = signalements.creer_signalement(
            auteur=citoyen, secteur=secteur, quartier=quartier, mode_localisation="MANUEL",
            medias_ids=[televerser(citoyen).id], titre="Trou", description_texte="Gros trou", repere="École",
        )
        reponse = ok(mairie.post(URL, corps(
            secteur, quartier, budget=185000000, latitude=6.4012345, longitude=2.3412345,
            date_debut_prevue="2026-09-01", date_fin_prevue="2026-12-15", signalements=[dossier.pk],
            medias=[
                {"media": str(photo.id), "phase": "AVANT", "legende": "Avant les pluies"},
                {"media": str(video.id), "phase": "PENDANT"},
            ],
        ), format="json"), 201)

        assert reponse["message"] == f"Réalisation enregistrée. Référence : REA-{ANNEE}-00001."
        donnees = reponse["donnees"]
        assert (donnees["statut"], donnees["taux_avancement"], donnees["publie"]) == ("PLANIFIEE", 0, False)
        assert donnees["budget"] == 185000000
        assert donnees["signalements"][0]["reference"] == dossier.reference
        assert [(m["phase"], m["ordre"]) for m in donnees["medias"]] == [("AVANT", 0), ("PENDANT", 1)]
        assert donnees["couverture"]["phase"] == "AVANT" and donnees["nb_medias"] == 2
        assert set(Media.objects.filter(pk__in=[photo.pk, video.pk]).values_list("statut", flat=True)) == {"ATTACHE"}
        assert Realisation.objects.get().cree_par == agent

    def test_ordre_explicite(self, mairie, agent, secteur, quartier, televerser):
        premier, second = televerser(agent), televerser(agent)
        donnees = ok(mairie.post(URL, corps(secteur, quartier, medias=[
            {"media": str(premier.id), "phase": "AVANT", "ordre": 5},
            {"media": str(second.id), "phase": "APRES", "ordre": 1},
        ]), format="json"), 201)["donnees"]
        assert [m["media"]["id"] for m in donnees["medias"]] == [str(second.id), str(premier.id)]
        assert donnees["couverture"]["media"]["id"] == str(second.id)

    @pytest.mark.parametrize("champ", ["titre", "description", "secteur", "quartiers"])
    def test_champs_obligatoires(self, mairie, secteur, quartier, champ):
        donnees = corps(secteur, quartier)
        del donnees[champ]
        assert champ in erreur(mairie.post(URL, donnees, format="json"), CodeErreur.VALIDATION_ERREUR, 400)["details"]

    @pytest.mark.parametrize(
        "surcharges, champ",
        [
            ({"quartiers": []}, "quartiers"),
            ({"taux_avancement": 101}, "taux_avancement"),
            ({"budget": -1}, "budget"),
            ({"date_debut_prevue": "2026-12-01", "date_fin_prevue": "2026-11-01"}, "date_fin_prevue"),
            ({"date_debut_reelle": "2026-12-01", "date_fin_reelle": "2026-11-01"}, "date_fin_reelle"),
            ({"latitude": 6.4}, "latitude"),
        ],
    )
    def test_valeurs_invalides(self, mairie, secteur, quartier, surcharges, champ):
        reponse = mairie.post(URL, corps(secteur, quartier, **surcharges), format="json")
        assert champ in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]
        assert not Realisation.objects.exists()

    def test_secteur_non_utilise_pour_les_realisations(self, mairie, quartier):
        autre = Secteur.objects.create(nom="Éclairage", code="ECLAIRAGE", pour_signalement=True)
        reponse = mairie.post(URL, corps(autre, quartier), format="json")
        assert "secteur" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_position_hors_commune(self, mairie, secteur, quartier):
        reponse = mairie.post(URL, corps(secteur, quartier, latitude=6.36, longitude=2.42), format="json")
        erreur(reponse, CodeErreur.COORDONNEES_HORS_COMMUNE, 400)

    def test_onze_photos_refusees(self, mairie, agent, secteur, quartier, televerser):
        medias = [{"media": str(televerser(agent).id), "phase": "APRES"} for _ in range(11)]
        erreur(mairie.post(URL, corps(secteur, quartier, medias=medias), format="json"), CodeErreur.MEDIAS_NON_CONFORMES, 400)

    def test_audio_refuse(self, mairie, agent, secteur, quartier, televerser):
        medias = [{"media": str(televerser(agent, Media.Type.AUDIO).id), "phase": "APRES"}]
        erreur(mairie.post(URL, corps(secteur, quartier, medias=medias), format="json"), CodeErreur.MEDIAS_NON_CONFORMES, 400)

    def test_media_d_un_autre(self, mairie, secteur, quartier, televerser, creer_utilisateur):
        medias = [{"media": str(televerser(creer_utilisateur()).id), "phase": "APRES"}]
        erreur(mairie.post(URL, corps(secteur, quartier, medias=medias), format="json"), CodeErreur.MEDIA_INTROUVABLE, 400)

    def test_meme_media_deux_fois(self, mairie, agent, secteur, quartier, televerser):
        media = str(televerser(agent).id)
        reponse = mairie.post(URL, corps(secteur, quartier, medias=[{"media": media, "phase": "AVANT"}, {"media": media, "phase": "APRES"}]), format="json")
        assert "medias" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    @pytest.mark.parametrize("role", [Utilisateur.Role.CITOYEN, Utilisateur.Role.ORGANISATION])
    def test_reserve_a_la_mairie(self, creer_utilisateur, client_connecte, secteur, quartier, role):
        reponse = client_connecte(creer_utilisateur(role=role)).post(URL, corps(secteur, quartier), format="json")
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE, 403)

    def test_non_authentifie(self, api_client, secteur, quartier):
        erreur(api_client.post(URL, corps(secteur, quartier), format="json"), CodeErreur.NON_AUTHENTIFIE, 401)

    def test_admin_mairie_autorise(self, creer_utilisateur, client_connecte, secteur, quartier):
        client = client_connecte(creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE))
        ok(client.post(URL, corps(secteur, quartier), format="json"), 201)


class TestModification:
    def test_mise_a_jour_partielle(self, creer, mairie):
        realisation = creer(budget=1000, prestataire="BTP Bénin")
        reponse = ok(mairie.patch(url(realisation), {"statut": "EN_COURS", "taux_avancement": 60}, format="json"))
        assert reponse["message"] == "Réalisation mise à jour."
        realisation.refresh_from_db()
        assert (realisation.statut, realisation.taux_avancement) == ("EN_COURS", 60)
        assert (realisation.budget, realisation.prestataire) == (1000, "BTP Bénin")

    def test_publication(self, creer, mairie, api_client):
        realisation = creer()
        assert ok(mairie.patch(url(realisation), {"publie": True}, format="json"))["message"] == "Réalisation publiée."
        ok(api_client.get(url(realisation)))

    def test_remplacement_des_medias(self, creer, mairie, agent, televerser, django_capture_on_commit_callbacks):
        garde, retire, nouveau = televerser(agent), televerser(agent), televerser(agent)
        realisation = services.creer_realisation(
            par=agent, titre="T", description="D", secteur=creer().secteur, quartiers=list(creer().quartiers.all()),
            medias=[{"media": garde.id, "phase": "AVANT"}, {"media": retire.id, "phase": "AVANT"}],
        )
        fichier_retire = Path(retire.fichier.path)

        with django_capture_on_commit_callbacks(execute=True):
            donnees = ok(mairie.patch(url(realisation), {"medias": [
                {"media": str(nouveau.id), "phase": "APRES", "legende": "Rue pavée"},
                {"media": str(garde.id), "phase": "PENDANT", "legende": "Corrigée"},
            ]}, format="json"))["donnees"]

        assert [(m["media"]["id"], m["phase"], m["legende"]) for m in donnees["medias"]] == [
            (str(nouveau.id), "APRES", "Rue pavée"), (str(garde.id), "PENDANT", "Corrigée"),
        ]
        assert not Media.objects.filter(pk=retire.pk).exists() and not fichier_retire.exists()
        nouveau.refresh_from_db()
        assert nouveau.statut == Media.Statut.ATTACHE

    def test_sans_medias_la_liste_est_conservee(self, creer, mairie, agent, televerser):
        photo = televerser(agent)
        realisation = creer(medias=[{"media": photo.id, "phase": "AVANT"}])
        ok(mairie.patch(url(realisation), {"titre": "Nouveau titre"}, format="json"))
        assert RealisationMedia.objects.filter(realisation=realisation).count() == 1

    def test_controles_sur_l_etat_final(self, creer, mairie):
        realisation = creer(date_debut_prevue=date(2026, 9, 1))
        reponse = mairie.patch(url(realisation), {"date_fin_prevue": "2026-08-01"}, format="json")
        assert "date_fin_prevue" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]
        reponse = mairie.patch(url(realisation), {"latitude": 6.4}, format="json")
        assert "latitude" in erreur(reponse, CodeErreur.VALIDATION_ERREUR, 400)["details"]

    def test_put_non_autorise(self, creer, mairie):
        erreur(mairie.put(url(creer()), {}, format="json"), CodeErreur.METHODE_NON_AUTORISEE, 405)

    def test_reserve_a_la_mairie(self, creer, creer_utilisateur, client_connecte):
        realisation = creer(publie=True)
        reponse = client_connecte(creer_utilisateur()).patch(url(realisation), {"titre": "Piraté"}, format="json")
        erreur(reponse, CodeErreur.PERMISSION_REFUSEE, 403)

    def test_contraintes_en_base(self, creer):
        realisation = creer()
        with pytest.raises(IntegrityError), transaction.atomic():
            Realisation.objects.filter(pk=realisation.pk).update(taux_avancement=150)


def test_liste_sans_requetes_en_cascade(creer, api_client, agent, televerser):
    creer(publie=True, medias=[{"media": televerser(agent).id, "phase": "AVANT"}])

    def compter():
        with CaptureQueriesContext(connection) as requetes:
            assert api_client.get(URL).status_code == 200
        return len(requetes)

    avant = compter()
    for _ in range(5):
        creer(publie=True, medias=[{"media": televerser(agent).id, "phase": "APRES"}])
    assert compter() == avant
