from django.contrib import admin

from .models import Secteur


@admin.register(Secteur)
class SecteurAdmin(admin.ModelAdmin):
    list_display = [
        "nom",
        "code",
        "pour_signalement",
        "pour_suggestion",
        "pour_realisation",
        "service_par_defaut",
        "ordre",
        "actif",
    ]
    list_editable = ["ordre", "actif"]
    list_filter = ["actif", "pour_signalement", "pour_suggestion", "pour_realisation"]
    search_fields = ["nom", "code"]
    list_select_related = ["service_par_defaut"]
    autocomplete_fields = ["service_par_defaut"]
