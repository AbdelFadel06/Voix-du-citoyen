from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm
from django.template.response import TemplateResponse

from . import services

from .models import Appareil, CodeOTP, Organisation, ServiceMunicipal, Utilisateur


class UtilisateurCreationForm(BaseUserCreationForm):
    class Meta:
        model = Utilisateur
        fields = ["telephone", "nom", "prenoms", "role", "service", "organisation"]


class UtilisateurChangeForm(UserChangeForm):
    class Meta:
        model = Utilisateur
        fields = "__all__"


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    form = UtilisateurChangeForm
    add_form = UtilisateurCreationForm

    list_display = ["telephone", "nom", "prenoms", "role", "telephone_verifie", "is_active"]
    list_filter = ["role", "telephone_verifie", "is_active", "is_staff"]
    search_fields = ["telephone", "nom", "prenoms", "email"]
    ordering = ["nom", "prenoms"]
    list_select_related = ["service", "organisation"]
    autocomplete_fields = ["quartier_residence", "service", "organisation"]
    readonly_fields = ["last_login", "date_joined", "cree_le", "maj_le"]

    fieldsets = [
        (None, {"fields": ["telephone", "password"]}),
        ("Identité", {"fields": ["nom", "prenoms", "email", "quartier_residence"]}),
        ("Rôle", {"fields": ["role", "service", "organisation"]}),
        (
            "Statut et permissions",
            {
                "fields": [
                    "telephone_verifie",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ]
            },
        ),
        ("Dates", {"fields": ["last_login", "date_joined", "cree_le", "maj_le"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": [
                    "telephone",
                    "nom",
                    "prenoms",
                    "role",
                    "service",
                    "organisation",
                    "password1",
                    "password2",
                ],
            },
        ),
    ]


class SuspensionForm(forms.Form):
    motif = forms.CharField(
        label="Motif de la suspension",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        help_text="Ce motif est conservé jusqu'à la réhabilitation.",
        error_messages={"required": "Le motif de suspension est obligatoire."},
    )


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = [
        "nom",
        "sigle",
        "type",
        "statut_habilitation",
        "date_habilitation",
        "date_expiration",
    ]
    list_filter = ["type", "statut_habilitation"]
    search_fields = ["nom", "sigle", "numero_enregistrement"]
    filter_horizontal = ["secteurs"]
    # Le statut ne change que par les actions « Suspendre » / « Réhabiliter ».
    readonly_fields = [
        "statut_habilitation",
        "motif_suspension",
        "date_habilitation",
        "habilitee_par",
        "cree_le",
        "maj_le",
    ]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "nom",
                    "sigle",
                    "type",
                    "numero_enregistrement",
                    "secteurs",
                    "logo",
                ]
            },
        ),
        ("Contact", {"fields": ["email", "telephone", "adresse"]}),
        (
            "Habilitation",
            {
                "fields": [
                    "statut_habilitation",
                    "motif_suspension",
                    "date_habilitation",
                    "habilitee_par",
                    "date_expiration",
                ]
            },
        ),
        ("Dates", {"fields": ["cree_le", "maj_le"]}),
    ]
    actions = ["suspendre", "rehabiliter"]

    def has_habilitation_permission(self, request):
        """Les actions d'habilitation sont réservées aux admins mairie."""
        utilisateur = request.user
        return utilisateur.is_superuser or utilisateur.role == Utilisateur.Role.ADMIN_MAIRIE

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
        else:
            services.creer_organisation(obj, par=request.user)

    @admin.action(description="Suspendre les organisations sélectionnées", permissions=["habilitation"])
    def suspendre(self, request, queryset):
        a_suspendre = queryset.filter(statut_habilitation=Organisation.StatutHabilitation.HABILITEE)
        form = SuspensionForm(request.POST if "confirmer" in request.POST else None)
        if form.is_valid():
            for organisation in a_suspendre:
                services.suspendre_organisation(organisation, form.cleaned_data["motif"])
            self.message_user(
                request, f"{len(a_suspendre)} organisation(s) suspendue(s).", messages.SUCCESS
            )
            return None
        return TemplateResponse(
            request,
            "admin/accounts/organisation/suspendre.html",
            {
                **self.admin_site.each_context(request),
                "title": "Suspendre des organisations",
                "opts": self.model._meta,
                "form": form,
                "organisations": a_suspendre,
                "ignorees": queryset.count() - a_suspendre.count(),
                "selection": request.POST.getlist(helpers.ACTION_CHECKBOX_NAME),
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
            },
        )

    @admin.action(description="Réhabiliter les organisations sélectionnées", permissions=["habilitation"])
    def rehabiliter(self, request, queryset):
        a_rehabiliter = queryset.filter(statut_habilitation=Organisation.StatutHabilitation.SUSPENDUE)
        nombre = 0
        for organisation in a_rehabiliter:
            services.rehabiliter_organisation(organisation)
            nombre += 1
        self.message_user(request, f"{nombre} organisation(s) réhabilitée(s).", messages.SUCCESS)


@admin.register(ServiceMunicipal)
class ServiceMunicipalAdmin(admin.ModelAdmin):
    list_display = ["nom", "responsable", "actif"]
    list_filter = ["actif"]
    search_fields = ["nom"]
    list_select_related = ["responsable"]
    autocomplete_fields = ["responsable"]


@admin.register(CodeOTP)
class CodeOTPAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "motif", "expire_le", "tentatives", "utilise"]
    list_filter = ["motif", "utilise"]
    search_fields = ["utilisateur__telephone"]
    list_select_related = ["utilisateur"]
    # Lecture seule : les codes sont gérés uniquement par l'API.
    readonly_fields = ["utilisateur", "code_hash", "motif", "expire_le", "tentatives", "utilise"]

    def has_add_permission(self, request):
        return False


@admin.register(Appareil)
class AppareilAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "plateforme", "actif", "maj_le"]
    list_filter = ["plateforme", "actif"]
    search_fields = ["utilisateur__telephone", "token_fcm"]
    list_select_related = ["utilisateur"]
    autocomplete_fields = ["utilisateur"]
