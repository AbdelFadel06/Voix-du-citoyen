from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("auth/register/", views.InscriptionView.as_view(), name="register"),
    path("auth/otp/verify/", views.VerificationOTPView.as_view(), name="otp-verify"),
    path("auth/otp/resend/", views.RenvoiOTPView.as_view(), name="otp-resend"),
    path("auth/login/", views.ConnexionView.as_view(), name="login"),
    path("auth/refresh/", views.RafraichissementView.as_view(), name="refresh"),
    path("auth/logout/", views.DeconnexionView.as_view(), name="logout"),
    path("auth/me/", views.MoiView.as_view(), name="me"),
]
