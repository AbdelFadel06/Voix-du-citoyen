from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Organisation, Utilisateur
from apps.core.permissions import (
    EstAdminMairie,
    EstAgentMairie,
    EstCitoyen,
    EstMairieOuOrganisation,
    EstOrganisationHabilitee,
    LectureSeuleOrganisation,
)

pytestmark = pytest.mark.django_db

Role = Utilisateur.Role
ROLES = [Role.CITOYEN, Role.AGENT, Role.ADMIN_MAIRIE, Role.ORGANISATION]


def autorise(permission, utilisateur, methode="get"):
    requete = getattr(APIRequestFactory(), methode)("/")
    requete.user = utilisateur
    return permission().has_permission(requete, None)


@pytest.mark.parametrize(
    "permission, roles_autorises",
    [
        (EstCitoyen, {Role.CITOYEN}),
        (EstAgentMairie, {Role.AGENT, Role.ADMIN_MAIRIE}),
        (EstAdminMairie, {Role.ADMIN_MAIRIE}),
        (EstOrganisationHabilitee, {Role.ORGANISATION}),
        (EstMairieOuOrganisation, {Role.AGENT, Role.ADMIN_MAIRIE, Role.ORGANISATION}),
    ],
)
@pytest.mark.parametrize("role", ROLES)
def test_permission_par_role(creer_utilisateur, permission, roles_autorises, role):
    assert autorise(permission, creer_utilisateur(role=role)) == (role in roles_autorises)


@pytest.mark.parametrize(
    "permission",
    [EstCitoyen, EstAgentMairie, EstAdminMairie, EstOrganisationHabilitee, EstMairieOuOrganisation],
)
def test_anonyme_toujours_refuse(permission):
    assert not autorise(permission, AnonymousUser())


@pytest.mark.parametrize("permission", [EstOrganisationHabilitee, EstMairieOuOrganisation])
def test_organisation_suspendue_refusee(creer_utilisateur, permission):
    compte = creer_utilisateur(role=Role.ORGANISATION)
    compte.organisation.statut_habilitation = Organisation.StatutHabilitation.SUSPENDUE
    assert not autorise(permission, compte)


@pytest.mark.parametrize("permission", [EstOrganisationHabilitee, EstMairieOuOrganisation])
def test_organisation_expiree_refusee(creer_utilisateur, permission):
    compte = creer_utilisateur(role=Role.ORGANISATION)
    compte.organisation.date_expiration = timezone.localdate() - timedelta(days=1)
    assert not autorise(permission, compte)


@pytest.mark.parametrize("permission", [EstOrganisationHabilitee, EstMairieOuOrganisation])
def test_organisation_expirant_aujourd_hui_acceptee(creer_utilisateur, permission):
    compte = creer_utilisateur(role=Role.ORGANISATION)
    compte.organisation.date_expiration = timezone.localdate()
    assert autorise(permission, compte)


@pytest.mark.parametrize("methode", ["post", "put", "patch", "delete"])
def test_organisation_en_lecture_seule(creer_utilisateur, methode):
    compte = creer_utilisateur(role=Role.ORGANISATION)
    assert autorise(LectureSeuleOrganisation, compte, "get")
    assert not autorise(LectureSeuleOrganisation, compte, methode)


@pytest.mark.parametrize("role", [Role.CITOYEN, Role.AGENT, Role.ADMIN_MAIRIE])
def test_lecture_seule_ne_concerne_que_les_organisations(creer_utilisateur, role):
    assert autorise(LectureSeuleOrganisation, creer_utilisateur(role=role), "post")
