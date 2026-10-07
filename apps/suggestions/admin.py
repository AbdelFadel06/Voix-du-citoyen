from django.contrib import admin

from .models import Suggestion, SuiviSuggestion


class SuiviSuggestionInline(admin.TabularInline):
    model = SuiviSuggestion
    extra = 0
    fields = ["cree_le", "type_evenement", "commentaire", "visible_citoyen", "auteur"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    """Consultation ; la marque « pertinente », les réponses et les soutiens passent par l'API."""

    list_display = ["reference", "titre", "est_pertinente", "secteur", "quartier", "nb_soutiens", "cree_le"]
    list_filter = ["commune", "est_pertinente", "secteur"]
    search_fields = ["reference", "titre", "description", "auteur__telephone"]
    list_select_related = ["secteur", "quartier"]
    date_hierarchy = "cree_le"
    inlines = [SuiviSuggestionInline]
    readonly_fields = [
        "reference", "titre", "description", "secteur", "quartier", "auteur", "est_pertinente", "nb_soutiens",
        "medias", "reponse_officielle", "repondu_par", "repondu_le", "cree_le", "maj_le",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
