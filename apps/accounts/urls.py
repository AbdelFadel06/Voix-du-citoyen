from django.urls import path

from . import views
from . import views_administration as admin_views

app_name = "accounts"

urlpatterns = [
    path("auth/register/", views.InscriptionView.as_view(), name="register"),
    path("auth/otp/verify/", views.VerificationOTPView.as_view(), name="otp-verify"),
    path("auth/otp/resend/", views.RenvoiOTPView.as_view(), name="otp-resend"),
    path("auth/login/", views.ConnexionView.as_view(), name="login"),
    path("auth/refresh/", views.RafraichissementView.as_view(), name="refresh"),
    path("auth/logout/", views.DeconnexionView.as_view(), name="logout"),
    path("auth/me/", views.MoiView.as_view(), name="me"),
    path("auth/password/reset/", views.DemandeReinitialisationView.as_view(), name="password-reset"),
    path("auth/password/reset/confirm/", views.ReinitialisationView.as_view(), name="password-reset-confirm"),
]

# Gestion par les admins mairie
LECTURE_CREATION = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "patch": "partial_update"}

urlpatterns += [
    path("services/", admin_views.ServiceMunicipalViewSet.as_view(LECTURE_CREATION), name="services"),
    path("services/import/", admin_views.ServiceMunicipalViewSet.as_view({"post": "importer"}), name="services-import"),
    path("services/<int:pk>/", admin_views.ServiceMunicipalViewSet.as_view(DETAIL), name="service-detail"),
    path("agents/", admin_views.AgentViewSet.as_view(LECTURE_CREATION), name="agents"),
    path("agents/<int:pk>/", admin_views.AgentViewSet.as_view(DETAIL), name="agent-detail"),
]
