"""Filtres de liste à plusieurs valeurs (`?secteur=1,3` ou `?secteur=1&secteur=3`), apps/core/filters.py."""

import pytest
from django.urls import reverse

from apps.accounts.models import Utilisateur
from apps.core.codes_erreur import CodeErreur
from apps.realisations import services as realisations
from apps.referentiel.models import Secteur
from apps.signalements import services as signalements
from apps.suggestions import services as suggestions
from apps.territoire.models import Arrondissement, Quartier
from conftest import commune_de_test

pytestmark = pytest.mark.django_db


@pytest.fixture
def donnees(creer_utilisateur, televerser):
    """Trois secteurs, trois quartiers : un signalement, une suggestion et une réalisation par couple."""
    arrondissement = Arrondissement.objects.create(commune=commune_de_test(), nom="Godomey")
    quartiers = [Quartier.objects.create(arrondissement=arrondissement, nom=nom) for nom in ("Togoudo", "Cococodji", "Zogbadjè")]
    secteurs = [
        Secteur.objects.create(nom=nom, code=nom.upper(), pour_signalement=True, pour_suggestion=True, pour_realisation=True)
        for nom in ("Voirie", "Eclairage", "Eau")
    ]
    citoyen = creer_utilisateur()
    agent = creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE)
    for secteur, quartier in zip(secteurs, quartiers):
        signalements.creer_signalement(
            auteur=citoyen, secteur=secteur, quartier=quartier, mode_localisation="MANUEL",
            medias_ids=[televerser(citoyen).id], titre="Problème", description_texte="D", repere="Marché",
        )
        suggestions.creer_suggestion(auteur=citoyen, titre="Idée", description="D", secteur=secteur, quartier=quartier)
    # Une réalisation dans les deux premiers quartiers : elle ne doit apparaître qu'une fois.
    realisations.creer_realisation(
        par=agent, titre="Pavage", description="D", secteur=secteurs[0], quartiers=quartiers[:2], publie=True
    )
    realisations.creer_realisation(
        par=agent, titre="Forage", description="D", secteur=secteurs[2], quartiers=[quartiers[2]], publie=True,
        statut="TERMINEE",
    )
    return {"secteurs": secteurs, "quartiers": quartiers, "agent": agent}


def ids(client, nom, **params):
    reponse = client.get(reverse(nom), params)
    assert reponse.status_code == 200, reponse.json()
    return reponse.json()["donnees"]


LISTES = ["signalements:signalement-list", "suggestions:suggestion-list", "realisations:realisation-list"]


@pytest.mark.parametrize("liste", LISTES)
def test_plusieurs_secteurs_et_quartiers(donnees, client_connecte, liste):
    client = client_connecte(donnees["agent"])
    voirie, eclairage, eau = (s.pk for s in donnees["secteurs"])
    togoudo, cococodji, _ = (q.pk for q in donnees["quartiers"])
    tous = len(ids(client, liste))
    # Une seule valeur : comme avant.
    un = len(ids(client, liste, secteur=voirie))
    # Paramètre répété ou virgules : même résultat, plus large qu'une seule valeur.
    repete = ids(client, liste, secteur=[voirie, eau])
    virgules = ids(client, liste, secteur=f"{voirie},{eau}")
    assert {d["id"] for d in repete} == {d["id"] for d in virgules}
    assert un < len(repete) <= tous
    # Quartiers : une réalisation dans deux des quartiers demandés n'apparaît qu'une fois.
    par_quartiers = ids(client, liste, quartier=f"{togoudo}, {cococodji}")
    assert len(par_quartiers) == len({d["id"] for d in par_quartiers})
    assert len(par_quartiers) == (1 if liste.startswith("realisations") else 2)
    # Les deux filtres se croisent : Éclairage à Togoudo n'a rien.
    assert ids(client, liste, secteur=eclairage, quartier=togoudo) == []


def test_plusieurs_statuts(donnees, client_connecte, api_client):
    client = client_connecte(donnees["agent"])
    assert len(ids(client, "signalements:signalement-list", statut="SOUMIS,RESOLU")) == 3
    assert ids(client, "signalements:signalement-list", statut=["RECU", "RESOLU"]) == []
    titres = {d["titre"] for d in ids(api_client, "realisations:realisation-list", statut="EN_COURS,TERMINEE")}
    assert titres == {"Forage"}  # « Pavage » est PLANIFIEE (statut par défaut)


@pytest.mark.parametrize(
    "liste, params, champ",
    [
        ("signalements:signalement-list", {"secteur": "1,abc"}, "secteur"),
        ("signalements:signalement-list", {"statut": "SOUMIS,INCONNU"}, "statut"),
        ("realisations:realisation-list", {"quartier": "x"}, "quartier"),
    ],
)
def test_valeur_invalide(donnees, client_connecte, liste, params, champ):
    reponse = client_connecte(donnees["agent"]).get(reverse(liste), params)
    assert reponse.status_code == 400
    erreur = reponse.json()["erreur"]
    assert erreur["code"] == CodeErreur.VALIDATION_ERREUR and champ in erreur["details"]
