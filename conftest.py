import itertools
import re

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import Organisation, ServiceMunicipal, Utilisateur
from apps.core.sms.backends.memoire import MemoireSMS
from apps.referentiel.models import Secteur
from apps.territoire.models import Commune

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
    def _creer(role=Utilisateur.Role.CITOYEN, secteurs=None, communes=None, **kwargs):
        """
        `secteurs` / `communes` : périmètre d'intervention d'une organisation créée ici
        (défaut : tous les secteurs et toutes les communes qui existent).
        """
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
            kwargs["organisation"].secteurs.set(Secteur.objects.all() if secteurs is None else secteurs)
            if communes is None:
                commune_de_test()
            kwargs["organisation"].communes.set(Commune.objects.all() if communes is None else communes)
        return Utilisateur.objects.create_user(password=MOT_DE_PASSE, role=role, **kwargs)

    return _creer


# Volets que la mairie d'une commune utilise par /api/v1/mairie/… (config/urls.py).
VOLETS_MAIRIE = {
    "signalements", "suggestions", "realisations", "secteurs", "quartiers", "arrondissements",
    "communes", "services", "agents", "organisations", "dashboard",
}


class ClientMairie(APIClient):
    """
    Client d'un agent ou admin de commune : envoie dans l'espace /api/v1/mairie/… les appels
    écrits avec les adresses générales (`reverse("signalements:…")`), avec une clé d'API
    d'institution comme le fait IBDC (le compte du test en devient le compte technique, créé avec le client). Les refus hors de cet espace sont testés dans apps/core/tests/test_espaces.py.
    """

    def __init__(self, utilisateur, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur
        self.cle = None
        self._cle()  # tout de suite : les tests qui comptent les requêtes ne voient pas sa création

    def _cle(self):
        if self.cle is None:
            from apps.interop import services as interop
            from apps.interop.models import Institution

            institution = Institution.objects.filter(compte=self.utilisateur).first() or Institution.objects.create(
                id_externe=f"test-{self.utilisateur.pk}", nom=f"Mairie {self.utilisateur.nom}",
                commune_id=self.utilisateur.commune_id, compte=self.utilisateur,
                cle_prefixe=f"t{self.utilisateur.pk}",
            )
            self.cle = interop.generer_cle(institution)
        return self.cle

    def generic(self, method, path, *args, **kwargs):
        morceaux = path.split("/")
        if path.startswith("/api/v1/") and len(morceaux) > 3 and morceaux[3] in VOLETS_MAIRIE:
            path = "/".join([*morceaux[:3], "mairie", *morceaux[3:]])
        if path.startswith("/api/v1/mairie/"):
            jeton = self._credentials.pop("HTTP_AUTHORIZATION", None)
            self._credentials["HTTP_X_API_KEY"] = self._cle()
            try:
                return super().generic(method, path, *args, **kwargs)
            finally:
                del self._credentials["HTTP_X_API_KEY"]
                if jeton:
                    self._credentials["HTTP_AUTHORIZATION"] = jeton
        return super().generic(method, path, *args, **kwargs)


def client_pour(utilisateur):
    """APIClient adapté au compte (espace mairie pour un agent ou admin de commune)."""
    from apps.core.espaces import est_mairie_de_commune

    return ClientMairie(utilisateur) if est_mairie_de_commune(utilisateur) else APIClient()


@pytest.fixture
def client_connecte():
    """Renvoie un APIClient authentifié par JWT pour l'utilisateur donné."""

    def _client(utilisateur, routes_generales=False):
        """`routes_generales` : sans passage par l'espace mairie (pour tester les refus)."""
        client = APIClient() if routes_generales else client_pour(utilisateur)
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


