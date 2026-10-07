from django.contrib import admin

from .models import Signalement, SuiviSignalement


class SuiviSignalementInline(admin.TabularInline):
    model = SuiviSignalement
    extra = 0
    fields = ["cree_le", "type_evenement", "ancien_statut", "nouveau_statut", "commentaire", "visible_citoyen", "auteur"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Signalement)
class SignalementAdmin(admin.ModelAdmin):
    """Consultation ; le traitement (statut, assignation, réponses) passe par l'API."""

    list_display = ["reference", "titre", "statut", "priorite", "secteur", "quartier", "service_assigne", "cree_le"]
    list_filter = ["commune", "statut", "priorite", "secteur", "mode_localisation"]
    search_fields = ["reference", "titre", "description_texte", "repere", "auteur__telephone"]
    list_select_related = ["secteur", "quartier", "service_assigne"]
    date_hierarchy = "cree_le"
    inlines = [SuiviSignalementInline]
    # Seuls le titre (correction d'un titre généré) et la priorité sont modifiables ici.
    readonly_fields = [
        "reference", "titre_genere", "description_texte", "description_audio", "secteur", "auteur",
        "mode_localisation", "latitude", "longitude", "precision_gps", "quartier", "repere",
        "statut", "service_assigne", "agent_assigne", "doublon_de", "medias", "date_resolution",
        "cree_le", "maj_le",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if "titre" in form.changed_data:
            obj.titre_genere = False
        super().save_model(request, obj, form, change)
