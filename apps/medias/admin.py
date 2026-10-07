from django.contrib import admin
from django.utils.html import format_html

from . import services
from .models import Media


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    """Consultation et suppression uniquement : les médias sont créés par l'API."""

    list_display = ["apercu", "type", "auteur", "statut", "taille_ko", "cree_le"]
    list_filter = ["type", "statut"]
    search_fields = ["id", "auteur__telephone", "auteur__nom"]
    list_select_related = ["auteur"]
    readonly_fields = [
        "id",
        "apercu",
        "auteur",
        "type",
        "statut",
        "fichier",
        "miniature",
        "mime_type",
        "taille_octets",
        "duree_secondes",
        "largeur",
        "hauteur",
        "cree_le",
        "maj_le",
    ]
    fields = readonly_fields

    @admin.display(description="aperçu")
    def apercu(self, media):
        if media.miniature:
            return format_html('<img src="{}" style="max-height:80px">', media.miniature.url)
        return "—"

    @admin.display(description="taille (Ko)", ordering="taille_octets")
    def taille_ko(self, media):
        return round(media.taille_octets / 1024)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        services.supprimer_media(obj)

    def delete_queryset(self, request, queryset):
        for media in queryset:
            services.supprimer_media(media)
