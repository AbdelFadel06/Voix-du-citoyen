from django.contrib import admin

from .models import Realisation, RealisationMedia


class RealisationMediaInline(admin.TabularInline):
    model = RealisationMedia
    extra = 0
    fields = ["phase", "legende", "ordre", "media"]
    readonly_fields = ["media"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Realisation)
class RealisationAdmin(admin.ModelAdmin):
    """Consultation et corrections ; la création et les médias passent par l'API."""

    list_display = ["reference", "titre", "statut", "taux_avancement", "secteur", "publie", "maj_le"]
    list_filter = ["commune", "publie", "statut", "secteur"]
    search_fields = ["reference", "titre", "description", "prestataire"]
    list_select_related = ["secteur"]
    filter_horizontal = ["quartiers"]
    raw_id_fields = ["signalements", "suggestions"]
    readonly_fields = ["reference", "cree_par", "cree_le", "maj_le"]
    inlines = [RealisationMediaInline]

    def has_add_permission(self, request):
        return False
