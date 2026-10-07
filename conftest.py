import itertools
import re

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import Organisation, ServiceMunicipal, Utilisateur
from apps.core.sms.backends.memoire import MemoireSMS

MOT_DE_PASSE = "Barometre!2026"
_numeros = itertools.count(1)


@pytest.fixture(autouse=True)
def _cache_vide():
    """Le throttling utilise le cache : on repart de zéro à chaque test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sms_en_memoire(settings):
    """Aucun SMS ne part pendant les tests : ils sont gardés dans MemoireSMS.boite."""
    settings.SMS_BACKEND = "apps.core.sms.backends.memoire.MemoireSMS"
    MemoireSMS.vider()
    yield
    MemoireSMS.vider()


@pytest.fixture(autouse=True)
def _push_en_memoire(settings):
    """Aucune notification push ne part pendant les tests : elles sont gardées dans MemoirePush.boite."""
    from apps.core.push.backends.memoire import MemoirePush

    settings.PUSH_BACKEND = "apps.core.push.backends.memoire.MemoirePush"
    MemoirePush.vider()
    yield
    MemoirePush.vider()


@pytest.fixture(autouse=True)
def _hachage_rapide(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def nouveau_telephone():
    """Renvoie un numéro béninois valide et unique à chaque appel."""
    return lambda: f"+229019700{next(_numeros):04d}"


@pytest.fixture
def creer_utilisateur(db, nouveau_telephone):
    def _creer(role=Utilisateur.Role.CITOYEN, **kwargs):
        kwargs.setdefault("telephone", nouveau_telephone())
        kwargs.setdefault("nom", "Dossou")
        kwargs.setdefault("prenoms", "Koffi")
        kwargs.setdefault("telephone_verifie", True)
        if role != Utilisateur.Role.CITOYEN:
            # La mairie et les organisations se connectent avec leur e-mail (obligatoire).
            chiffres = "".join(c for c in str(kwargs["telephone"]) if c.isdigit())
            kwargs.setdefault("email", f"compte{chiffres}@mairie.test")
        if role == Utilisateur.Role.AGENT and "service" in kwargs:
            kwargs.setdefault("commune", kwargs["service"].commune)
        if role in (Utilisateur.Role.CITOYEN, Utilisateur.Role.AGENT):
            kwargs.setdefault("commune", commune_de_test())
        if role == Utilisateur.Role.AGENT and "service" not in kwargs:
            kwargs["service"], _ = ServiceMunicipal.objects.get_or_create(nom="Voirie", commune=kwargs["commune"])
        if role == Utilisateur.Role.ORGANISATION and "organisation" not in kwargs:
            kwargs["organisation"] = Organisation.objects.create(
                nom="ONG Test",
                type=Organisation.Type.ONG,
                numero_enregistrement=f"ONG-{kwargs['telephone']}",
                statut_habilitation=Organisation.StatutHabilitation.HABILITEE,
            )
        return Utilisateur.objects.create_user(password=MOT_DE_PASSE, role=role, **kwargs)

    return _creer


@pytest.fixture
def client_connecte():
    """Renvoie un APIClient authentifié par JWT pour l'utilisateur donné."""

    def _client(utilisateur):
        client = APIClient()
        jeton = services.generer_jetons(utilisateur)["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
        return client

    return _client


@pytest.fixture
def sms():
    """SMS envoyés pendant le test ; `sms.dernier_code()` renvoie le dernier code OTP."""

    class BoiteSMS:
        def __len__(self):
            return len(MemoireSMS.boite)

        def __getitem__(self, index):
            return MemoireSMS.boite[index]

        def dernier_code(self):
            return re.search(r"\b(\d{6})\b", MemoireSMS.boite[-1].message).group(1)

        def simuler_echec(self):
            MemoireSMS.simuler_echec = True

    return BoiteSMS()


def commune_de_test():
    """Commune de test unique (emprise approximative d'Abomey-Calavi), créée au premier besoin."""
    from decimal import Decimal

    from apps.territoire.models import Commune

    commune, _ = Commune.objects.get_or_create(
        code="ABC",
        defaults={
            "nom": "Abomey-Calavi",
            "departement": "Atlantique",
            "lat_min": Decimal("6.380000"),
            "lat_max": Decimal("6.650000"),
            "lng_min": Decimal("2.230000"),
            "lng_max": Decimal("2.450000"),
        },
    )
    return commune


@pytest.fixture
def commune(db):
    return commune_de_test()


@pytest.fixture(autouse=True)
def _medias_dans_un_dossier_temporaire(settings, tmp_path):
    """Les fichiers envoyés pendant les tests ne vont jamais dans le dossier media/ du projet."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def televerser(db):
    """Envoie un vrai fichier (photo par défaut) au nom de `auteur` ; renvoie le Media TEMPORAIRE."""
    from apps.medias.models import Media
    from apps.medias.services import televerser_media
    from apps.medias.tests import fichiers

    def _televerser(auteur, type_=Media.Type.IMAGE):
        if type_ == Media.Type.IMAGE:
            return televerser_media(auteur=auteur, type=type_, fichier=fichiers.image("JPEG", "RGB"))
        if type_ == Media.Type.VIDEO:
            return televerser_media(
                auteur=auteur, type=type_, fichier=fichiers.video_mp4(), miniature=fichiers.image(), duree_secondes=20
            )
        return televerser_media(auteur=auteur, type=type_, fichier=fichiers.audio_m4a(), duree_secondes=30)

    return _televerser


