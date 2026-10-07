"""Serializers transverses : envoi d'un fichier CSV et bilan d'import."""

from rest_framework import serializers


class ImportCSVSerializer(serializers.Serializer):
    fichier = serializers.FileField(
        allow_empty_file=False,
        help_text="Fichier CSV (séparateur « ; » ou « , », UTF-8 ou enregistré par Excel), 1 Mo au maximum.",
    )
    simulation = serializers.BooleanField(
        default=False,
        help_text="`true` : tout vérifier et compter sans rien enregistrer (aperçu avant confirmation).",
    )
    desactiver_absents = serializers.BooleanField(
        default=False,
        help_text="`true` : désactiver les éléments existants qui ne figurent pas dans le fichier.",
    )


class BilanImportSerializer(serializers.Serializer):
    simulation = serializers.BooleanField(help_text="Vrai si rien n'a été enregistré (simulation).")
    crees = serializers.IntegerField(help_text="Éléments créés (ou qui seraient créés).")
    mis_a_jour = serializers.IntegerField(help_text="Éléments existants mis à jour.")
    desactives = serializers.IntegerField(help_text="Éléments désactivés car absents du fichier.")


def message_bilan(bilan, libelle):
    """« Import terminé : 8 secteurs créés, 2 mis à jour, 0 désactivé(s). » (ou simulation)."""
    texte = (
        f"{bilan['crees']} {libelle} créé(s), {bilan['mis_a_jour']} mis à jour, "
        f"{bilan['desactives']} désactivé(s)."
    )
    if bilan["simulation"]:
        return f"Simulation : {texte} Rien n'a été enregistré."
    return f"Import terminé : {texte}"
