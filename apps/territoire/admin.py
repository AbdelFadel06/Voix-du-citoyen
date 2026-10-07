from django.contrib import admin

from .models import Arrondissement, Commune, Quartier


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ["nom", "code", "departement"]
    search_fields = ["nom", "code"]


@admin.register(Arrondissement)
class ArrondissementAdmin(admin.ModelAdmin):
    list_display = ["nom", "code", "commune"]
    list_filter = ["commune"]
    search_fields = ["nom", "code"]
    list_select_related = ["commune"]


@admin.register(Quartier)
class QuartierAdmin(admin.ModelAdmin):
    list_display = ["nom", "code", "arrondissement", "actif"]
    list_filter = ["actif", "arrondissement"]
    search_fields = ["nom", "code"]
    list_select_related = ["arrondissement"]
