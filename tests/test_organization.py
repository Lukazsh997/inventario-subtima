import pytest
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog
from apps.organization import services
from apps.organization.models import Recipient, Sector

pytestmark = pytest.mark.django_db


def test_sector_hierarchy_and_path(admin_user):
    gov = services.save_sector(actor=admin_user, sector=None, name="Secretaria Municipal de Governo", acronym="smg")
    subtima = services.save_sector(
        actor=admin_user,
        sector=None,
        name="Subsecretaria de Tecnologia da Informação e Modernização Administrativa",
        acronym="SUBTIMA",
        parent=gov,
    )
    assert gov.acronym == "SMG"
    assert subtima.path == "SMG › SUBTIMA"


def test_sector_name_unique_case_insensitive(admin_user):
    services.save_sector(actor=admin_user, sector=None, name="DESANS")
    with pytest.raises(ValidationError):
        services.save_sector(actor=admin_user, sector=None, name="desans")


def test_sector_cycle_prevented(admin_user):
    a = services.save_sector(actor=admin_user, sector=None, name="A")
    b = services.save_sector(actor=admin_user, sector=None, name="B", parent=a)
    with pytest.raises(ValidationError):
        services.save_sector(actor=admin_user, sector=a, name="A", parent=b)


def test_sector_with_active_children_cannot_be_deactivated(admin_user):
    a = services.save_sector(actor=admin_user, sector=None, name="A")
    services.save_sector(actor=admin_user, sector=None, name="B", parent=a)
    with pytest.raises(ValidationError):
        services.set_sector_active(actor=admin_user, sector=a, active=False)


def test_sector_with_history_cannot_be_deleted(admin_user):
    sector = services.save_sector(actor=admin_user, sector=None, name="Urbanismo")
    services.save_recipient(actor=admin_user, recipient=None, full_name="Fulano", sector=sector)
    with pytest.raises(ProtectedError):
        sector.delete()


def test_recipient_registration_unique_but_optional(tech_user):
    sector = Sector.objects.create(name="Saúde")
    services.save_recipient(actor=tech_user, recipient=None, full_name="Sem Matrícula 1", sector=sector)
    services.save_recipient(actor=tech_user, recipient=None, full_name="Sem Matrícula 2", sector=sector)
    services.save_recipient(actor=tech_user, recipient=None, full_name="Maria", sector=sector, registration="12345")
    with pytest.raises(ValidationError):
        services.save_recipient(actor=tech_user, recipient=None, full_name="Outra", sector=sector, registration="12345")
    assert Recipient.objects.count() == 3


def test_recipient_update_records_only_changed_fields(tech_user):
    sector = Sector.objects.create(name="Saúde")
    r = services.save_recipient(actor=tech_user, recipient=None, full_name="José", sector=sector)
    services.save_recipient(actor=tech_user, recipient=r, full_name="José da Silva", sector=sector)
    entry = AuditLog.objects.get(action=AuditAction.UPDATE, entity_id=str(r.pk))
    assert entry.changes == {"full_name": {"de": "José", "para": "José da Silva"}}


def test_location_unique_within_sector(admin_user):
    sector = Sector.objects.create(name="Governo")
    services.save_location(actor=admin_user, location=None, sector=sector, name="Sala 204")
    with pytest.raises(ValidationError):
        services.save_location(actor=admin_user, location=None, sector=sector, name="sala 204")


def test_sector_views_flow(client_for, admin_user):
    client = client_for(admin_user)
    response = client.post(reverse("organization:sector_create"), {"name": "Secretaria de Urbanismo", "acronym": "SMU"})
    sector = Sector.objects.get(acronym="SMU")
    assert response["Location"] == reverse("organization:sector_detail", args=[sector.pk])
    client.post(reverse("organization:sector_detail", args=[sector.pk]), {"name": "Prédio anexo"})
    assert sector.locations.filter(name="Prédio anexo").exists()
    page = client.get(reverse("organization:sector_list") + "?q=urban").content.decode()
    assert "Secretaria de Urbanismo" in page


def test_recipient_search_by_registration(client_for, tech_user):
    sector = Sector.objects.create(name="Saúde")
    Recipient.objects.create(full_name="Carla Dias", registration="98765", sector=sector)
    Recipient.objects.create(full_name="Outro Nome", registration="11111", sector=sector)
    page = client_for(tech_user).get(reverse("organization:recipient_list") + "?q=98765").content.decode()
    assert "Carla Dias" in page and "Outro Nome" not in page
