from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.territoire.models import Arrondissement, Quartier

pytestmark = pytest.mark.django_db

EN_TETE = "arrondissement_code;arrondissement_nom;quartier_code;quartier_nom;latitude;longitude\n"


@pytest.fixture
def csv(tmp_path):
    def _ecrire(contenu, en_tete=EN_TETE):
        chemin = tmp_path / "quartiers.csv"
        chemin.write_text(en_tete + contenu, encoding="utf-8")
        return chemin

    return _ecrire


def charger(chemin, *options):
    call_command("charger_quartiers", str(chemin), "--commune", "ABC", *options)


def test_charge_arrondissements_et_quartiers(commune, csv):
    charger(csv("GOD;Godomey;TOG;Togoudo;6.401234;2.341234\nGOD;Godomey;CAL;Calavi Centre;;\n"))

    assert Arrondissement.objects.get().nom == "Godomey"
    togoudo = Quartier.objects.get(nom="Togoudo")
    assert togoudo.code == "TOG"
    assert togoudo.latitude_centre == Decimal("6.401234")
    assert Quartier.objects.get(nom="Calavi Centre").latitude_centre is None


def test_relancer_met_a_jour_sans_doublon(commune, csv):
    charger(csv("GOD;Godomey;TOG;Togoudo;;\n"))
    charger(csv("GOD;Godomey;TOG2;Togoudo;6.4;2.34\n"))

    assert Quartier.objects.count() == 1
    quartier = Quartier.objects.get()
    assert quartier.code == "TOG2"
    assert quartier.latitude_centre == Decimal("6.400000")


def test_separateur_virgule_et_virgule_decimale(commune, csv):
    en_tete = EN_TETE.replace(";", ",")
    charger(csv('GOD,Godomey,TOG,Togoudo,"6,4","2,34"\n', en_tete=en_tete))
    assert Quartier.objects.get().longitude_centre == Decimal("2.340000")


def test_desactiver_absents(commune, csv):
    charger(csv("GOD;Godomey;TOG;Togoudo;;\nGOD;Godomey;CAL;Calavi;;\n"))
    charger(csv("GOD;Godomey;TOG;Togoudo;;\n"), "--desactiver-absents")
    assert not Quartier.objects.get(nom="Calavi").actif
    assert Quartier.objects.get(nom="Togoudo").actif


def test_simulation_n_enregistre_rien(commune, csv):
    charger(csv("GOD;Godomey;TOG;Togoudo;;\n"), "--simulation")
    assert not Quartier.objects.exists()
    assert not Arrondissement.objects.exists()


def test_coordonnees_hors_commune_refusent_tout_le_fichier(commune, csv):
    with pytest.raises(CommandError, match="Ligne 3 .* hors de l'emprise"):
        charger(csv("GOD;Godomey;TOG;Togoudo;6.4;2.34\nGOD;Godomey;COT;Cotonou;6.36;2.42\n"))
    assert not Quartier.objects.exists()


@pytest.mark.parametrize(
    "contenu, message",
    [
        ("GOD;;TOG;Togoudo;;\n", "arrondissement_nom"),
        ("GOD;Godomey;TOG;;;\n", "quartier_nom"),
        ("GOD;Godomey;TOG;Togoudo;abc;2.3\n", "invalides"),
        ("GOD;Godomey;TOG;Togoudo;6.4;\n", "invalides"),
        ("GOD;Godomey;TOG;Togoudo;;\nGOD;Godomey;TOG;togoudo;;\n", "apparaît déjà ligne 2"),
    ],
)
def test_lignes_invalides(commune, csv, contenu, message):
    with pytest.raises(CommandError, match=message):
        charger(csv(contenu))
    assert not Quartier.objects.exists()


def test_colonnes_manquantes(commune, csv):
    with pytest.raises(CommandError, match="Colonnes manquantes : latitude, longitude"):
        charger(csv("GOD;Godomey;TOG;Togoudo\n", en_tete="arrondissement_code;arrondissement_nom;quartier_code;quartier_nom\n"))


def test_commune_inconnue(db, csv):
    with pytest.raises(CommandError, match="Commune « ABC » introuvable"):
        charger(csv("GOD;Godomey;TOG;Togoudo;;\n"))


def test_fichier_introuvable(commune, tmp_path):
    with pytest.raises(CommandError, match="Fichier introuvable"):
        charger(tmp_path / "absent.csv")
