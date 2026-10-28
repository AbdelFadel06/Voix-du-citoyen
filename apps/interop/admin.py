from django.contrib import admin, messages

from . import services
from .models import Institution


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ["nom", "id_externe", "commune", "actif", "cle_prefixe", "cle_generee_le"]
    list_filter = ["actif", "commune"]
    search_fields = ["nom", "id_externe"]
    # Création par la commande « creer_institution » (elle crée aussi le compte technique).
    fields = ["nom", "id_externe", "commune", "compte", "actif", "cle_prefixe", "cle_generee_le", "cree_le", "maj_le"]
    readonly_fields = ["id_externe", "commune", "compte", "cle_prefixe", "cle_generee_le", "cree_le", "maj_le"]
    actions = ["nouvelle_cle"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Générer une nouvelle clé (l'ancienne ne fonctionnera plus)")
    def nouvelle_cle(self, request, queryset):
        for institution in queryset:
            cle = services.generer_cle(institution)
            self.message_user(
                request,
                f"Nouvelle clé de « {institution.nom} », à transmettre à IBDC (elle ne sera plus affichée) : {cle}",
                messages.WARNING,
            )
