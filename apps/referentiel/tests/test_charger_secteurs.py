import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import ServiceMunicipal
from apps.referentiel.models import Secteur
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

EN_TETE = (
    "code;nom;description;icone;couleur;pour_signalement;pour_suggestion;"
    "pour_realisation;service_par_defaut;ordre\n"
)


@pytest.fixture
def csv(tmp_path):
    def _ecrire(contenu, en_tete=EN_TETE):
        chemin = tmp_path / "secteurs.csv"
        chemin.write_text(en_tete + contenu, encoding="utf-8")
        return chemin

    return _ecrire


@pytest.fixture
def voirie():
    return ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie et assainissement")


def charger(chemin, *options):
    call_command("charger_secteurs", str(chemin), *options)


def test_charge_les_secteurs(csv, voirie):
    charger(csv(
        "VOIRIE;Voirie;Routes;route;#F57C00;oui;oui;oui;Voirie et assainissement;1\n"
        "ECLAIRAGE;Éclairage public;;lampadaire;#FBC02D;1;non;x;;2\n"
    ))
    route = Secteur.objects.get(code="VOIRIE")
    assert (route.nom, route.icone, route.couleur, route.ordre) == ("Voirie", "route", "#F57C00", 1)
    assert route.pour_signalement and route.pour_suggestion and route.pour_realisation
    assert route.service_par_defaut == voirie
    eclairage = Secteur.objects.get(code="ECLAIRAGE")
    assert eclairage.pour_signalement and not eclairage.pour_suggestion and eclairage.pour_realisation
    assert eclairage.service_par_defaut is None


def test_relancer_met_a_jour_par_code(csv):
    charger(csv("VOIRIE;Voirie;;;;oui;non;non;;1\n"))
    charger(csv("VOIRIE;Voirie et routes;;;;oui;oui;non;;3\n"))
    assert Secteur.objects.count() == 1
    secteur = Secteur.objects.get()
    assert (secteur.nom, secteur.pour_suggestion, secteur.ordre) == ("Voirie et routes", True, 3)


def test_colonnes_facultatives_absentes_laissent_les_valeurs(csv):
    Secteur.objects.create(code="VOIRIE", nom="Voirie", couleur="#000000", pour_signalement=True, ordre=5)
    charger(csv("VOIRIE;Voirie renommée\n", en_tete="code;nom\n"))
    secteur = Secteur.objects.get()
    assert secteur.nom == "Voirie renommée"
    assert (secteur.couleur, secteur.pour_signalement, secteur.ordre) == ("#000000", True, 5)


def test_reactive_et_desactive_les_absents(csv):
    Secteur.objects.create(code="ANCIEN", nom="Ancien")
    Secteur.objects.create(code="VOIRIE", nom="Voirie", actif=False)
    charger(csv("VOIRIE;Voirie\n", en_tete="code;nom\n"), "--desactiver-absents")
    assert Secteur.objects.get(code="VOIRIE").actif
    assert not Secteur.objects.get(code="ANCIEN").actif


def test_simulation_n_enregistre_rien(csv):
    charger(csv("VOIRIE;Voirie\n", en_tete="code;nom\n"), "--simulation")
    assert not Secteur.objects.exists()


@pytest.mark.parametrize(
    "contenu, message",
    [
        (";Voirie;;;;;;;;\n", "« code » est vide"),
        ("VOIRIE;;;;;;;;;\n", "« nom » est vide"),
        ("VOIRIE;Voirie;;;bleu;;;;;\n", "couleur « bleu » invalide"),
        ("VOIRIE;Voirie;;;;peut-être;;;;\n", "« pour_signalement » doit valoir oui ou non"),
        ("VOIRIE;Voirie;;;;;;;Service fantôme;\n", "service « Service fantôme » introuvable"),
        ("VOIRIE;Voirie;;;;;;;;-1\n", "« ordre » doit être un nombre entier"),
        ("VOIRIE;Voirie;;;;;;;;\nVOIRIE;Autre;;;;;;;;\n", "le code « VOIRIE » apparaît déjà ligne 2"),
        ("VOIRIE;Voirie;;;;;;;;\nROUTE;voirie;;;;;;;;\n", "le nom « voirie » apparaît déjà ligne 2"),
    ],
)
def test_lignes_invalides(csv, contenu, message):
    with pytest.raises(CommandError, match=message):
        charger(csv(contenu))
    assert not Secteur.objects.exists()


def test_nom_deja_pris_par_un_autre_code(csv):
    Secteur.objects.create(code="ROUTE", nom="Voirie")
    with pytest.raises(CommandError, match="déjà utilisé par le secteur « ROUTE »"):
        charger(csv("VOIRIE;Voirie\n", en_tete="code;nom\n"))


def test_colonnes_obligatoires(csv):
    with pytest.raises(CommandError, match="Colonnes manquantes : code"):
        charger(csv("Voirie\n", en_tete="nom\n"))


def test_fichier_vide(tmp_path):
    chemin = tmp_path / "vide.csv"
    chemin.write_text("", encoding="utf-8")
    with pytest.raises(CommandError, match="Fichier vide"):
        charger(chemin)
