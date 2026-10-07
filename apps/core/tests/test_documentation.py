"""
Garde-fou de la documentation Swagger : tout endpoint de /api/v1/ (actuel ou futur) doit être
documenté complètement, sinon ces tests échouent.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

from apps.core.codes_erreur import CodeErreur
from apps.core.schema import TAGS

METHODES = {"get", "post", "put", "patch", "delete"}
NOMS_TAGS = {tag["name"] for tag in TAGS}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def operations(schema):
    for chemin, item in schema["paths"].items():
        for methode, operation in item.items():
            if methode in METHODES:
                yield f"{methode.upper()} {chemin}", operation


def resoudre(schema, objet):
    while "$ref" in objet:
        objet = schema["components"]["schemas"][objet["$ref"].rsplit("/", 1)[-1]]
    return objet


def test_introduction_et_tags(schema):
    description = schema["info"]["description"]
    for section in ("Démarrage rapide", "Format des réponses", "Codes d'erreur", "Rôles"):
        assert section in description
    for code in CodeErreur:
        assert f"`{code.value}`" in description, f"{code} absent du tableau des codes"
    assert all(tag.get("description") for tag in schema["tags"])


def test_chaque_operation_a_un_tag_un_resume_et_une_description(schema):
    for nom, operation in operations(schema):
        assert operation.get("summary"), f"{nom} : summary manquant"
        assert len(operation.get("description", "")) > 80, f"{nom} : description trop courte"
        assert operation.get("tags") and set(operation["tags"]) <= NOMS_TAGS, f"{nom} : tag inconnu"


def test_chaque_parametre_est_decrit(schema):
    for nom, operation in operations(schema):
        for parametre in operation.get("parameters", []):
            assert parametre.get("description"), f"{nom} : paramètre {parametre['name']} sans description"


def test_reponses_au_format_commun_avec_exemples(schema):
    for nom, operation in operations(schema):
        reponses = operation["responses"]
        assert any(code.startswith(("4", "5")) for code in reponses), f"{nom} : aucune erreur documentée"
        for code, reponse in reponses.items():
            contenu = reponse.get("content", {}).get("application/json")
            if contenu is None:
                assert code == "204", f"{nom} {code} : réponse sans contenu"
                continue
            proprietes = resoudre(schema, contenu["schema"]).get("properties", {})
            assert "succes" in proprietes, f"{nom} {code} : réponse hors enveloppe"
            assert contenu.get("examples"), f"{nom} {code} : aucun exemple"


def test_chaque_requete_a_un_exemple(schema):
    for nom, operation in operations(schema):
        corps = operation.get("requestBody", {}).get("content", {}).get("application/json")
        if corps:
            assert corps.get("examples"), f"{nom} : aucun exemple de requête"


def test_chaque_champ_des_composants_est_decrit(schema):
    for nom, composant in schema["components"]["schemas"].items():
        if "enum" in composant:
            continue
        for champ, definition in composant.get("properties", {}).items():
            assert definition.get("description"), f"{nom}.{champ} sans description"


def test_les_endpoints_publics_ne_demandent_pas_de_jeton(schema):
    publics = {
        "POST /api/v1/auth/register/",
        "POST /api/v1/auth/otp/verify/",
        "POST /api/v1/auth/otp/resend/",
        "POST /api/v1/auth/password/reset/",
        "POST /api/v1/auth/password/reset/confirm/",
        "POST /api/v1/auth/login/",
        "POST /api/v1/auth/refresh/",
        "GET /api/v1/sante/",
        # Publics, mais un jeton mairie facultatif donne aussi accès aux brouillons.
        "GET /api/v1/realisations/",
        "GET /api/v1/realisations/{id}/",
    }
    for nom, operation in operations(schema):
        securite = operation.get("security", [])
        demande_jeton = any(element for element in securite)
        assert demande_jeton != (nom in publics), f"{nom} : sécurité mal documentée ({securite})"


def test_pages_de_documentation(api_client):
    assert api_client.get("/api/docs/").status_code == 200
    assert api_client.get("/api/redoc/").status_code == 200
