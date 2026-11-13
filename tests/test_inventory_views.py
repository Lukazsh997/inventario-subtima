"""Fluxos completos pela interface (requisição HTTP → serviço → banco)."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.catalog.models import Consumable, Equipment, EquipmentStatus, Ownership
from apps.inventory.models import OperationType as T
from apps.inventory.models import StockBalance, StockOperation
from apps.organization.models import Recipient

from . import factories as f

pytestmark = pytest.mark.django_db


def _equipment_post(**overrides):
    data = {
        "category": f.equipment_category().pk,
        "name": "Estabilizador",
        "manufacturer": "SMS",
        "model": "",
        "ownership": Ownership.OWNED,
        "lessor": "",
        "asset_tag": "",
        "serial_number": "",
        "lessor_code": "",
        "condition": "bom",
        "acquisition_date": "",
        "notes": "",
    }
    data.update(overrides)
    return data


def test_entry_form_accepts_scanned_whatsapp_link(client_for, tech_user):
    client = client_for(tech_user)
    response = client.post(
        reverse("catalog:equipment_create"),
        _equipment_post(
            ownership=Ownership.LEASED,
            lessor="Locadora",
            serial_number="2419391010456",
            lessor_code="https://wa.me/552138991801?text= ACES0000151",
        ),
    )
    item = Equipment.objects.get()
    assert response["Location"] == reverse("catalog:equipment_detail", args=[item.pk])
    # O link lido do QR é salvo como o código impresso na etiqueta
    item.refresh_from_db()
    assert item.lessor_code == "ACES0000151"


def test_entry_form_requires_identifier_and_lessor(client_for, tech_user):
    client = client_for(tech_user)
    response = client.post(reverse("catalog:equipment_create"), _equipment_post())
    assert "pelo menos um identificador" in response.content.decode()
    response = client.post(reverse("catalog:equipment_create"), _equipment_post(serial_number="X", ownership="locado"))
    assert "Informe a locadora" in response.content.decode()
    assert not Equipment.objects.exists()


def test_entry_already_in_use_with_new_recipient(client_for, tech_user):
    sector = f.sector()
    client = client_for(tech_user)
    response = client.post(
        reverse("catalog:equipment_create"),
        {
            **_equipment_post(asset_tag="085.057"),
            "uso-in_use": "on",
            "uso-destination_sector": sector.pk,
            "uso-new_recipient_name": "Carlos Lima",
            "uso-new_recipient_registration": "4455",
        },
    )
    assert response.status_code == 302
    item = Equipment.objects.get()
    assert item.status == EquipmentStatus.IN_USE
    assert item.current_recipient == Recipient.objects.get(registration="4455")


def test_failed_entry_does_not_leave_orphan_recipient(client_for, tech_user):
    sector = f.sector()
    f.equipment(tech_user, asset_tag="085.057", serial_number="")
    client_for(tech_user).post(
        reverse("catalog:equipment_create"),
        {
            **_equipment_post(asset_tag="085057"),
            "uso-in_use": "on",
            "uso-destination_sector": sector.pk,
            "uso-new_recipient_name": "Fantasma",
        },
    )
    assert not Recipient.objects.filter(full_name="Fantasma").exists()


def test_lookup_and_scan_open_equipment(client_for, tech_user):
    item = f.equipment(tech_user, asset_tag="085.057", serial_number="")
    client = client_for(tech_user)
    data = client.get(reverse("catalog:equipment_lookup"), {"codigo": "085057"}).json()
    assert [r["id"] for r in data["results"]] == [item.pk]
    response = client.get(reverse("catalog:scan"), {"codigo": "085.057"})
    assert response["Location"] == reverse("catalog:equipment_detail", args=[item.pk])
    response = client.get(reverse("core:search"), {"q": "085.057"})
    assert response["Location"] == reverse("catalog:equipment_detail", args=[item.pk])
    assert "Nenhum equipamento" in client.get(reverse("catalog:scan"), {"codigo": "999"}).content.decode()


def test_equipment_exit_through_form_with_accessories(client_for, tech_user):
    sector = f.sector()
    maria = f.recipient(sector)
    notebook = f.equipment(tech_user, name="Notebook Dell")
    client = client_for(tech_user)
    assert (
        client.get(reverse("inventory:equipment_operation"), {"tipo": "saida", "equipamento": notebook.pk}).status_code
        == 200
    )
    response = client.post(
        reverse("inventory:equipment_operation"),
        {
            "type": T.EXIT,
            "equipment_ids": [notebook.pk],
            "destination_sector": sector.pk,
            "recipient": maria.pk,
            "accessory_description": ["Carregador", "Bolsa", ""],
            "accessory_quantity": ["1", "1", "1"],
            "justification": "",
            "notes": "",
        },
    )
    operation = StockOperation.objects.get(type=T.EXIT)
    assert response["Location"] == reverse("inventory:operation_detail", args=[operation.pk])
    assert list(operation.accessories.values_list("description", flat=True)) == ["Carregador", "Bolsa"]
    page = client.get(response["Location"]).content.decode()
    assert "Notebook Dell" in page and "Carregador" in page


def test_consumable_exit_form_shows_stock_error(client_for, tech_user):
    sector = f.sector()
    toner = f.consumable(tech_user, initial=1)
    client = client_for(tech_user)
    response = client.post(
        reverse("inventory:consumable_operation"),
        {
            "type": T.EXIT,
            "consumable_id": [toner.pk],
            "quantity": ["3"],
            "destination_sector": sector.pk,
            "new_recipient_name": "Ana",
            "justification": "",
            "notes": "",
        },
    )
    assert "Estoque insuficiente" in response.content.decode()
    assert StockBalance.objects.get(consumable=toner).quantity == 1
    assert not Recipient.objects.filter(full_name="Ana").exists()  # desfeito junto com a operação


def test_technician_cannot_adjust_or_reverse_via_http(client_for, tech_user):
    toner = f.consumable(tech_user, initial=5)
    client = client_for(tech_user)
    client.post(
        reverse("inventory:consumable_operation"),
        {"type": T.ADJUSTMENT, "consumable_id": [toner.pk], "quantity": ["-5"], "justification": "x"},
    )
    assert StockBalance.objects.get(consumable=toner).quantity == 5
    entry = StockOperation.objects.get()
    assert (
        client.post(reverse("inventory:operation_reverse", args=[entry.pk]), {"justification": "x"}).status_code == 403
    )


def test_admin_reverse_via_http(client_for, admin_user):
    toner = f.consumable(admin_user, initial=5)
    entry = StockOperation.objects.get()
    response = client_for(admin_user).post(
        reverse("inventory:operation_reverse", args=[entry.pk]), {"justification": "Nota lançada em duplicidade"}
    )
    reversal = StockOperation.objects.get(type=T.REVERSAL)
    assert response["Location"] == reverse("inventory:operation_detail", args=[reversal.pk])
    assert StockBalance.objects.get(consumable=toner).quantity == 0


def test_viewer_sees_but_cannot_operate(client_for, viewer_user, admin_user):
    item = f.equipment(admin_user)
    client = client_for(viewer_user)
    for name, args in [
        ("catalog:equipment_list", []),
        ("catalog:equipment_detail", [item.pk]),
        ("inventory:operation_list", []),
        ("catalog:consumable_list", []),
    ]:
        assert client.get(reverse(name, args=args)).status_code == 200
    for name in ["inventory:equipment_operation", "inventory:consumable_operation", "catalog:equipment_create"]:
        assert client.get(reverse(name)).status_code == 403


def test_pages_render(client_for, admin_user):
    item = f.equipment(admin_user)
    toner = f.consumable(admin_user, initial=2)
    client = client_for(admin_user)
    for name, args in [
        ("core:home", []),
        ("catalog:equipment_list", []),
        ("catalog:equipment_create", []),
        ("catalog:equipment_update", [item.pk]),
        ("catalog:consumable_detail", [toner.pk]),
        ("catalog:consumable_create", []),
        ("catalog:category_list", []),
        ("catalog:category_create", []),
        ("inventory:operation_list", []),
        ("inventory:consumable_operation", []),
        ("catalog:scan", []),
    ]:
        assert client.get(reverse(name, args=args)).status_code == 200, name


def test_load_reference_supplies_command(admin_user):
    call_command("carregar_suprimentos", usuario="admin", simular=True)
    assert not Consumable.objects.exists()
    call_command("carregar_suprimentos", usuario="admin")
    assert Consumable.objects.count() == 43
    assert Consumable.objects.get(reference="W1510A").compatibility == "HP LaserJet Pro MFP M4103fdw"
    call_command("carregar_suprimentos", usuario="admin")  # idempotente
    assert Consumable.objects.count() == 43
