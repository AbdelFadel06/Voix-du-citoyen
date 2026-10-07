"""Vues factices utilisées uniquement par test_reponses.py (sous /api/v1/ comme les vraies)."""

from django.http import Http404
from django.urls import include, path
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.core.codes_erreur import CodeErreur
from apps.core.exceptions import ErreurMetier
from apps.core.permissions import EstAdminMairie
from apps.core.reponses import reponse_succes


class VuePublique(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class SuccesAvecMessage(VuePublique):
    def get(self, request):
        return reponse_succes({"valeur": 1}, "Opération réussie.", status=201)


class DonneesBrutes(VuePublique):
    def get(self, request):
        return Response({"valeur": 1})


class ElementSerializer(serializers.Serializer):
    valeur = serializers.IntegerField()


class Liste(ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    filter_backends = []
    serializer_class = ElementSerializer

    def get_queryset(self):
        return [{"valeur": i} for i in range(1, 46)]


class Validation(VuePublique):
    class Entree(serializers.Serializer):
        telephone = serializers.CharField()
        age = serializers.IntegerField()

    def post(self, request):
        self.Entree(data=request.data).is_valid(raise_exception=True)
        return Response(status=204)


class Metier(VuePublique):
    def get(self, request):
        raise ErreurMetier(CodeErreur.CONFLIT, details={"reference": "SIG-2026-00001"})


class ReserveeAdmin(APIView):
    permission_classes = [IsAuthenticated, EstAdminMairie]

    def get(self, request):
        return reponse_succes()


class Introuvable(VuePublique):
    def get(self, request):
        raise Http404("détail interne à ne pas montrer")


class Plantage(VuePublique):
    def get(self, request):
        raise RuntimeError("mot de passe de la base = secret123")


class UneParMinute(SimpleRateThrottle):
    rate = "1/minute"

    def get_cache_key(self, request, view):
        return "test-throttle"


class Limitee(VuePublique):
    throttle_classes = [UneParMinute]

    def get(self, request):
        return reponse_succes()


class ErreurManuelle(VuePublique):
    def get(self, request):
        return Response({"champ": ["déjà pris"]}, status=409)


urlpatterns = [
    path(
        "api/v1/test/",
        include(
            [
                path("succes/", SuccesAvecMessage.as_view()),
                path("brut/", DonneesBrutes.as_view()),
                path("liste/", Liste.as_view()),
                path("validation/", Validation.as_view()),
                path("metier/", Metier.as_view()),
                path("admin/", ReserveeAdmin.as_view()),
                path("introuvable/", Introuvable.as_view()),
                path("plantage/", Plantage.as_view()),
                path("limitee/", Limitee.as_view()),
                path("manuelle/", ErreurManuelle.as_view()),
            ]
        ),
    ),
]
