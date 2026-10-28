"""
Institutions (mairies) connectées par clé d'API depuis IBDC.

Format d'une clé : `vdc_<préfixe>_<secret>`. Le préfixe (public) sert à retrouver
l'institution, le secret n'est jamais stocké : seulement l'empreinte SHA-256 de la clé
complète, comparée en temps constant. Les clés sont longues et aléatoires, une empreinte
rapide suffit (contrairement aux mots de passe).
"""

import hashlib
import hmac
import secrets

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utilisateur

from .models import Institution

PREFIXE_CLE = "vdc"


def _empreinte(cle):
    return hashlib.sha256(cle.encode()).hexdigest()


def generer_cle(institution):
    """Crée une nouvelle clé (l'ancienne cesse de fonctionner) et la renvoie, en clair, une seule fois."""
    prefixe = secrets.token_hex(6)
    cle = f"{PREFIXE_CLE}_{prefixe}_{secrets.token_urlsafe(32)}"
    institution.cle_prefixe = prefixe
    institution.cle_empreinte = _empreinte(cle)
    institution.cle_generee_le = timezone.now()
    institution.save(update_fields=["cle_prefixe", "cle_empreinte", "cle_generee_le", "maj_le"])
    return cle


@transaction.atomic
def creer_institution(*, id_externe, nom, commune, email, telephone):
    """
    Enregistre une mairie connectée et son compte technique (admin mairie de la commune, sans
    mot de passe). Renvoie (institution, clé en clair).
    """
    compte = Utilisateur.objects.create_user(
        telephone,
        password=None,  # mot de passe inutilisable : connexion par clé uniquement
        nom=nom[:100],
        prenoms="Compte technique IBDC",
        email=email,
        role=Utilisateur.Role.ADMIN_MAIRIE,
        commune=commune,
        telephone_verifie=True,
    )
    institution = Institution(
        id_externe=id_externe,
        nom=nom,
        commune=commune,
        compte=compte,
        cle_prefixe=secrets.token_hex(6),  # remplacé par generer_cle
    )
    institution.save()
    return institution, generer_cle(institution)


def institution_pour_cle(cle):
    """Institution active correspondant à la clé, ou None."""
    morceaux = (cle or "").split("_", 2)
    if len(morceaux) != 3 or morceaux[0] != PREFIXE_CLE:
        return None
    institution = (
        Institution.objects.select_related("compte", "commune").filter(cle_prefixe=morceaux[1], actif=True).first()
    )
    if institution is None or not hmac.compare_digest(institution.cle_empreinte, _empreinte(cle)):
        return None
    if not institution.compte.is_active:
        return None
    return institution
