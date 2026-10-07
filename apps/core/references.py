"""
Références lisibles des dossiers : `SIG-2026-00001`, `SUG-2026-00001`, `REA-2026-00001`.

La numérotation repart à 1 chaque année. Un verrou PostgreSQL propre à (préfixe, année),
tenu jusqu'à la fin de la transaction, garantit que deux créations simultanées n'obtiennent
jamais le même numéro.
"""

import zlib

from django.db import connection
from django.db.models.functions import Length
from django.utils import timezone


def prochaine_reference(modele, prefixe, champ="reference"):
    """À appeler dans une transaction, juste avant de créer l'objet."""
    if not connection.in_atomic_block:
        raise RuntimeError("prochaine_reference() doit être appelée dans une transaction.")
    debut = f"{prefixe}-{timezone.localdate().year}-"
    with connection.cursor() as curseur:
        curseur.execute("SELECT pg_advisory_xact_lock(%s)", [zlib.crc32(debut.encode())])
    derniere = (
        modele.objects.filter(**{f"{champ}__startswith": debut})
        # Tri par longueur d'abord : SIG-2026-100000 vient après SIG-2026-99999.
        .order_by(Length(champ).desc(), f"-{champ}")
        .values_list(champ, flat=True)
        .first()
    )
    numero = int(derniere.removeprefix(debut)) + 1 if derniere else 1
    return f"{debut}{numero:05d}"
