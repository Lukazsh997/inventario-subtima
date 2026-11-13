"""Notificações de estoque mínimo (requisito 7)."""

import pytest
from django.urls import reverse

from apps.alerts.models import AlertLevel, LowStockAlert
from apps.catalog import services as catalog
from apps.inventory import services as inventory
from apps.inventory.models import OperationType as T
from apps.inventory.services import OperationData

from . import factories as f

pytestmark = pytest.mark.django_db


def _exit(actor, item, qty, sector, recipient):
    return inventory.move_consumables(
        actor=actor,
        op_type=T.EXIT,
        lines=[(item, qty)],
        data=OperationData(destination_sector=sector, recipient=recipient),
    )


@pytest.fixture
def setup(tech_user):
    sector = f.sector()
    toner = f.consumable(tech_user, name="Toner HP 105A", min_stock=5, initial=8)
    # Cadastrado com mínimo 5 e saldo 0, o material nasce crítico; a entrada inicial normaliza.
    created = LowStockAlert.objects.get()
    assert created.level == AlertLevel.EMPTY and created.closed_at is not None
    LowStockAlert.objects.all().delete()  # parte de um histórico limpo para os cenários abaixo
    return tech_user, sector, f.recipient(sector), toner


def test_alert_opens_when_reaching_minimum_and_records_when(setup):
    actor, sector, maria, toner = setup
    assert not LowStockAlert.objects.exists()
    _exit(actor, toner, 3, sector, maria)  # 8 -> 5 = mínimo: "atingir" já alerta
    alert = LowStockAlert.objects.get()
    assert (alert.balance_at_open, alert.min_stock_at_open, alert.level) == (5, 5, AlertLevel.LOW)
    assert alert.opened_at is not None and alert.is_open


def test_no_duplicate_alert_while_condition_lasts(setup):
    actor, sector, maria, toner = setup
    _exit(actor, toner, 3, sector, maria)
    _exit(actor, toner, 2, sector, maria)
    _exit(actor, toner, 3, sector, maria)
    alert = LowStockAlert.objects.get()  # um único alerta
    assert alert.current_balance == 0 and alert.level == AlertLevel.EMPTY
    assert alert.balance_at_open == 5  # registro do momento em que foi identificado é preservado


def test_alert_closes_when_stock_normalized_and_reopens_later(setup):
    actor, sector, maria, toner = setup
    _exit(actor, toner, 4, sector, maria)
    inventory.move_consumables(actor=actor, op_type=T.ENTRY, lines=[(toner, 10)], data=OperationData())
    closed = LowStockAlert.objects.get()
    assert closed.closed_at is not None and "normalizado" in closed.closed_reason
    _exit(actor, toner, 10, sector, maria)
    assert LowStockAlert.objects.count() == 2
    assert LowStockAlert.objects.filter(closed_at__isnull=True).count() == 1


def test_changing_minimum_or_deactivating_updates_alerts(setup, admin_user):
    actor, sector, maria, toner = setup
    data = {"category": toner.category, "name": toner.name, "reference": None, "unit": toner.unit, "compatibility": ""}
    catalog.save_consumable(actor=actor, consumable=toner, data={**data, "min_stock": 10})
    assert LowStockAlert.objects.filter(closed_at__isnull=True).count() == 1  # 8 <= 10
    catalog.save_consumable(actor=actor, consumable=toner, data={**data, "min_stock": 0})
    assert LowStockAlert.objects.get().closed_reason == "Estoque mínimo removido"
    catalog.save_consumable(actor=actor, consumable=toner, data={**data, "min_stock": 9})
    catalog.set_consumable_active(actor=actor, consumable=toner, active=False)
    assert not LowStockAlert.objects.filter(closed_at__isnull=True).exists()


def test_reversal_reevaluates_alert(setup, admin_user):
    actor, sector, maria, toner = setup
    op = _exit(actor, toner, 4, sector, maria)
    assert LowStockAlert.objects.filter(closed_at__isnull=True).exists()
    inventory.reverse_operation(actor=admin_user, operation=op, justification="digitado errado")
    assert not LowStockAlert.objects.filter(closed_at__isnull=True).exists()


def test_without_minimum_there_is_no_alert(tech_user):
    sector = f.sector()
    paper = f.consumable(tech_user, name="Papel A4", initial=1)
    _exit(tech_user, paper, 1, sector, f.recipient(sector))
    assert not LowStockAlert.objects.exists()


def test_critical_page_and_menu_badge(client_for, setup):
    actor, sector, maria, toner = setup
    _exit(actor, toner, 4, sector, maria)
    client = client_for(actor)
    page = client.get(reverse("alerts:critical_list")).content.decode()
    assert "Toner HP 105A" in page
    assert 'aria-label="1 alertas abertos"' in client.get(reverse("catalog:equipment_list")).content.decode()
    inventory.move_consumables(actor=actor, op_type=T.ENTRY, lines=[(toner, 10)], data=OperationData())
    assert "Toner HP 105A" not in client.get(reverse("alerts:critical_list")).content.decode()
    assert "Toner HP 105A" in client.get(reverse("alerts:critical_list") + "?historico=1").content.decode()


def test_purchase_suggestion_uses_recent_consumption(client_for, setup):
    actor, sector, maria, toner = setup
    _exit(actor, toner, 6, sector, maria)  # consumo de 6 em 90 dias = 2/mês; saldo 2, mínimo 5
    response = client_for(actor).get(reverse("alerts:critical_list"))
    row = response.context["rows"][0]
    assert round(row["avg"], 1) == 2.0
    assert row["suggested"] == 5 + 6 - 2  # volta ao mínimo + 3 meses de consumo
