from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.accounts.models import Organisation, ServiceMunicipal, Utilisateur
from conftest import commune_de_test

pytestmark = pytest.mark.django_db

TELEPHONE = "+2290197000001"


class TestManager:
    def test_create_user_stocke_le_telephone_en_e164(self):
        utilisateur = Utilisateur.objects.create_user(
            "0197000001", password="motdepasse-solide", nom="Dossou", prenoms="Koffi"
        )
        utilisateur.refresh_from_db()
        assert str(utilisateur.telephone) == TELEPHONE
        assert utilisateur.role == Utilisateur.Role.CITOYEN
        assert utilisateur.check_password("motdepasse-solide")
        assert not utilisateur.is_staff
        assert not utilisateur.telephone_verifie

    def test_create_user_refuse_un_telephone_invalide(self):
        with pytest.raises(ValueError, match="invalide"):
            Utilisateur.objects.create_user("123", password="x", nom="A", prenoms="B")

    def test_create_user_refuse_un_telephone_vide(self):
        with pytest.raises(ValueError, match="obligatoire"):
            Utilisateur.objects.create_user("", password="x", nom="A", prenoms="B")

    @pytest.mark.parametrize("champ", ["nom", "prenoms"])
    @pytest.mark.parametrize("valeur", ["", "   ", None])
    def test_create_user_refuse_nom_ou_prenoms_vides(self, champ, valeur):
        donnees = {"nom": "Dossou", "prenoms": "Koffi", champ: valeur}
        with pytest.raises(ValueError, match="obligatoire"):
            Utilisateur.objects.create_user(TELEPHONE, password="x", **donnees)

    def test_email_facultatif(self):
        utilisateur = Utilisateur.objects.create_user(TELEPHONE, nom="Dossou", prenoms="Koffi")
        assert utilisateur.email is None
        utilisateur.full_clean()

    def test_telephone_unique(self):
        Utilisateur.objects.create_user(TELEPHONE, nom="A", prenoms="B")
        with pytest.raises(IntegrityError):
            Utilisateur.objects.create_user("0197000001", nom="C", prenoms="D")

    def test_create_superuser(self):
        admin = Utilisateur.objects.create_superuser(
            TELEPHONE, password="motdepasse-solide", nom="Admin", prenoms="Mairie", email="Admin@Mairie.bj"
        )
        assert admin.email == "admin@mairie.bj"
        assert admin.is_staff and admin.is_superuser
        assert admin.role == Utilisateur.Role.ADMIN_MAIRIE
        assert admin.telephone_verifie


class TestRattachementSelonRole:
    def test_agent_sans_service_refuse_en_base(self):
        with pytest.raises(IntegrityError):
            Utilisateur.objects.create_user(
                TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.AGENT, email="a@mairie.bj"
            )

    def test_agent_sans_service_refuse_a_la_validation(self):
        agent = Utilisateur(telephone=TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.AGENT)
        with pytest.raises(ValidationError) as exc:
            agent.clean()
        assert "service" in exc.value.message_dict

    def test_agent_avec_service_accepte(self):
        service = ServiceMunicipal.objects.create(commune=commune_de_test(), nom="Voirie")
        agent = Utilisateur.objects.create_user(
            TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.AGENT, service=service, email="a@mairie.bj",
            commune=service.commune,
        )
        assert agent.service == service

    def test_compte_organisation_sans_organisation_refuse_en_base(self):
        with pytest.raises(IntegrityError):
            Utilisateur.objects.create_user(
                TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.ORGANISATION, email="ong@exemple.bj"
            )

    def test_compte_organisation_sans_organisation_refuse_a_la_validation(self):
        compte = Utilisateur(
            telephone=TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.ORGANISATION
        )
        with pytest.raises(ValidationError) as exc:
            compte.clean()
        assert "organisation" in exc.value.message_dict


class TestAccesOrganisation:
    def organisation(self, **kwargs):
        return Organisation(nom="ONG Test", type=Organisation.Type.ONG, **kwargs)

    def test_habilitee_par_defaut(self):
        organisation = self.organisation()
        assert organisation.statut_habilitation == Organisation.StatutHabilitation.HABILITEE
        assert organisation.acces_autorise

    def test_suspendue_sans_acces(self):
        organisation = self.organisation(
            statut_habilitation=Organisation.StatutHabilitation.SUSPENDUE, motif_suspension="Fraude"
        )
        assert not organisation.acces_autorise

    def test_habilitee_sans_expiration_a_acces(self):
        org = self.organisation(statut_habilitation=Organisation.StatutHabilitation.HABILITEE)
        assert org.acces_autorise

    def test_habilitee_non_expiree_a_acces(self):
        org = self.organisation(
            statut_habilitation=Organisation.StatutHabilitation.HABILITEE,
            date_expiration=timezone.localdate(),
        )
        assert org.acces_autorise

    def test_habilitee_expiree_sans_acces(self):
        org = self.organisation(
            statut_habilitation=Organisation.StatutHabilitation.HABILITEE,
            date_expiration=timezone.localdate() - timedelta(days=1),
        )
        assert not org.acces_autorise



class TestEmail:
    @pytest.mark.parametrize("role", [Utilisateur.Role.AGENT, Utilisateur.Role.ADMIN_MAIRIE, Utilisateur.Role.ORGANISATION])
    def test_obligatoire_pour_la_mairie_et_les_organisations(self, role):
        with pytest.raises(ValueError, match="e-mail est obligatoire"):
            Utilisateur.objects.create_user(TELEPHONE, nom="A", prenoms="B", role=role)

    def test_obligatoire_en_base(self):
        citoyen = Utilisateur.objects.create_user(TELEPHONE, nom="A", prenoms="B")
        with pytest.raises(IntegrityError):
            Utilisateur.objects.filter(pk=citoyen.pk).update(role=Utilisateur.Role.ADMIN_MAIRIE)

    def test_unique_sans_tenir_compte_des_majuscules(self):
        Utilisateur.objects.create_user(TELEPHONE, nom="A", prenoms="B", email="afiavi@exemple.bj")
        with pytest.raises(IntegrityError):
            Utilisateur.objects.filter(pk=Utilisateur.objects.create_user(
                "+2290197000002", nom="C", prenoms="D").pk).update(email="AFIAVI@exemple.bj")

    def test_plusieurs_citoyens_sans_email(self):
        Utilisateur.objects.create_user(TELEPHONE, nom="A", prenoms="B")
        Utilisateur.objects.create_user("+2290197000002", nom="C", prenoms="D")
        assert Utilisateur.objects.filter(email__isnull=True).count() == 2

    def test_clean_exige_l_email_du_personnel(self):
        agent = Utilisateur(telephone=TELEPHONE, nom="A", prenoms="B", role=Utilisateur.Role.AGENT)
        with pytest.raises(ValidationError) as exc:
            agent.clean()
        assert "email" in exc.value.message_dict
