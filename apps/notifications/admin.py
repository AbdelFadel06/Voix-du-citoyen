from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Consultation uniquement : les notifications sont créées par les services métier."""

    list_display = ["cree_le", "destinataire", "type", "titre", "lu", "envoye_push"]
    list_filter = ["type", "lu", "envoye_push"]
    search_fields = ["destinataire__telephone", "titre", "message"]
    list_select_related = ["destinataire"]
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
