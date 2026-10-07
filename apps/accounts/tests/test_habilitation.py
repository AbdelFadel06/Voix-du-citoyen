import importlib

import pytest
from django.apps import apps as registre
from django.contrib.admin import helpers
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import Organisation, Utilisateur

pytestmark = pytest.mark.django_db

Statut = Organisation.StatutHabilitation
URL_LISTE = reverse("admin:accounts_organisation_changelist")
URL_AJOUT = reverse("admin:accounts_organisation_add")


@pytest.fixture
def organisation():
    return Organisation.objects.create(
        nom="ONG Eau Pour Tous", sigle="EPT", type=Organisation.Type.ONG, numero_enregistrement="ONG-001"
    )


@pytest.fixture
def admin_mairie(creer_utilisateur):
    return creer_utilisateur(role=Utilisateur.Role.ADMIN_MAIRIE, is_staff=True, is_superuser=True)


@pytest.fixture
def client_admin(client, admin_mairie):
    client.force_login(admin_mairie)
    return client


def lancer_action(client, action, organisations, **donnees):
    return client.post(
        URL_LISTE,
        {
            "action": action,
            helpers.ACTION_CHECKBOX_NAME: [o.pk for o in organisations],
            **donnees,
        },
    )


class TestModele:
    def test_suspendue_sans_motif_refusee_a_la_validation(self, organisation):
        organisation.statut_habilitation = Statut.SUSPENDUE
        organisation.motif_suspension = "   "
        with pytest.raises(ValidationError) as exc:
            organisation.clean()
        assert "motif_suspension" in exc.value.message_dict

    def test_suspendue_sans_motif_refusee_en_base(self, organisation):
        with pytest.raises(IntegrityError):
            Organisation.objects.filter(pk=organisation.pk).update(statut_habilitation=Statut.SUSPENDUE)

    def test_le_motif_est_vide_quand_habilitee(self, organisation):
        organisation.motif_suspension = "reste d'une ancienne suspension"
        organisation.clean()
        assert organisation.motif_suspension == ""

    def test_date_expiration_facultative(self, organisation):
        organisation.full_clean()
        assert organisation.date_expiration is None
        assert organisation.acces_autorise


class TestServices:
    def test_creer_organisation_remplit_date_et_admin(self, admin_mairie):
        organisation = services.creer_organisation(
            Organisation(nom="OSC", type=Organisation.Type.OSC, numero_enregistrement="OSC-1"),
            par=admin_mairie,
        )
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE
        assert organisation.date_habilitation == timezone.localdate()
        assert organisation.habilitee_par == admin_mairie

    def test_suspendre(self, organisation):
        services.suspendre_organisation(organisation, "  Rapport annuel non fourni  ")
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.SUSPENDUE
        assert organisation.motif_suspension == "Rapport annuel non fourni"
        assert not organisation.acces_autorise

    @pytest.mark.parametrize("motif", ["", "   ", None])
    def test_suspendre_sans_motif_refuse(self, organisation, motif):
        with pytest.raises(ValidationError):
            services.suspendre_organisation(organisation, motif)
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE

    def test_rehabiliter_vide_le_motif(self, organisation):
        services.suspendre_organisation(organisation, "Fraude")
        services.rehabiliter_organisation(organisation)
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE
        assert organisation.motif_suspension == ""
        assert organisation.acces_autorise


class TestAdmin:
    def test_creation_remplit_date_et_admin(self, client_admin, admin_mairie):
        reponse = client_admin.post(
            URL_AJOUT,
            {"nom": "ONG Santé", "type": "ONG", "numero_enregistrement": "ONG-777"},
        )
        assert reponse.status_code == 302, reponse.context["adminform"].form.errors
        organisation = Organisation.objects.get(numero_enregistrement="ONG-777")
        assert organisation.statut_habilitation == Statut.HABILITEE
        assert organisation.date_habilitation == timezone.localdate()
        assert organisation.habilitee_par == admin_mairie

    def test_statut_date_et_admin_non_editables_dans_le_formulaire(self, client_admin, organisation):
        reponse = client_admin.get(reverse("admin:accounts_organisation_change", args=[organisation.pk]))
        champs = reponse.context["adminform"].form.fields
        for champ in ("statut_habilitation", "motif_suspension", "date_habilitation", "habilitee_par"):
            assert champ not in champs
        assert "date_expiration" in champs

    def test_suspendre_demande_le_motif(self, client_admin, organisation):
        reponse = lancer_action(client_admin, "suspendre", [organisation])
        assert reponse.status_code == 200
        assert "Motif de la suspension" in reponse.content.decode()
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE

    def test_suspendre_avec_motif(self, client_admin, organisation):
        reponse = lancer_action(
            client_admin, "suspendre", [organisation], confirmer="1", motif="Rapport annuel non fourni"
        )
        assert reponse.status_code == 302
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.SUSPENDUE
        assert organisation.motif_suspension == "Rapport annuel non fourni"

    def test_suspendre_sans_motif_reaffiche_le_formulaire(self, client_admin, organisation):
        reponse = lancer_action(client_admin, "suspendre", [organisation], confirmer="1", motif="  ")
        assert reponse.status_code == 200
        assert "Le motif de suspension est obligatoire." in reponse.content.decode()
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE

    def test_rehabiliter(self, client_admin, organisation):
        services.suspendre_organisation(organisation, "Fraude")
        reponse = lancer_action(client_admin, "rehabiliter", [organisation])
        assert reponse.status_code == 302
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE
        assert organisation.motif_suspension == ""

    def test_actions_reservees_aux_admins_mairie(self, client, creer_utilisateur, organisation):
        agent = creer_utilisateur(role=Utilisateur.Role.AGENT, is_staff=True)
        agent.user_permissions.add(
            *Permission.objects.filter(codename__in=["view_organisation", "change_organisation"])
        )
        client.force_login(agent)

        formulaire = client.get(URL_LISTE).context["action_form"]
        # Sans aucune action autorisée, Django n'affiche même pas le menu des actions.
        choix = dict(formulaire.fields["action"].choices) if formulaire else {}
        assert "suspendre" not in choix and "rehabiliter" not in choix

        lancer_action(client, "suspendre", [organisation], confirmer="1", motif="Tentative")
        organisation.refresh_from_db()
        assert organisation.statut_habilitation == Statut.HABILITEE


def test_migration_convertit_les_anciens_statuts(organisation):
    migration = importlib.import_module("apps.accounts.migrations.0004_habilitation_simplifiee")
    autre = Organisation.objects.create(nom="OSC", type="OSC", numero_enregistrement="OSC-9")
    # Valeurs qui n'existent plus dans les choix, écrites directement comme avant la migration.
    Organisation.objects.filter(pk=organisation.pk).update(statut_habilitation="EN_ATTENTE")
    Organisation.objects.filter(pk=autre.pk).update(statut_habilitation="REVOQUEE")

    migration.convertir_anciens_statuts(registre, None)

    for org, ancien in ((organisation, "en attente"), (autre, "révoquée")):
        org.refresh_from_db()
        assert org.statut_habilitation == Statut.SUSPENDUE
        assert ancien in org.motif_suspension
