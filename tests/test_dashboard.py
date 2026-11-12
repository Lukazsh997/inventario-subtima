"""Os números do dashboard conferidos contra consultas diretas ao banco."""

from datetime import date

import pytest
from django.urls import reverse

from apps.catalog.models import Equipment, EquipmentStatus
from apps.dashboard import selectors
from apps.inventory import services as inventory
from apps.inventory.models import OperationType as T
from apps.inventory.models import StockBalance
from apps.inventory.services import OperationData

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario(admin_user):
    smu, sms = f.sector("Urbanismo", "SMU"), f.sector("Saúde", "SMS")
    maria, joao = f.recipient(smu, "Maria"), f.recipient(sms, "João")
    pcs = [f.equipment(admin_user) for _ in range(4)]
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.EXIT,
        equipment_ids=[pcs[0].pk, pcs[1].pk],
        data=OperationData(destination_sector=smu, recipient=maria),
    )
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.LOAN,
        equipment_ids=[pcs[2].pk],
        data=OperationData(destination_sector=sms, recipient=joao),
    )
    toner = f.consumable(admin_user, name="Toner A", min_stock=3, initial=10)
    paper = f.consumable(admin_user, name="Papel A4", initial=4)
    inventory.move_consumables(
        actor=admin_user,
        op_type=T.EXIT,
        lines=[(toner, 8), (paper, 4)],
        data=OperationData(destination_sector=smu, recipient=maria),
    )
    return {"smu": smu, "sms": sms, "toner": toner, "paper": paper}


def _filters(**kwargs):
    start, end = selectors.default_period()
    return selectors.DashboardFilters(start=start, end=end, **kwargs)


def test_indicators_match_database(scenario):
    kpi = selectors.indicators(_filters())
    live = Equipment.objects.exclude(status=EquipmentStatus.WRITTEN_OFF)
    assert kpi["equipment_total"] == live.count() == 4
    assert kpi["available"] == live.filter(status=EquipmentStatus.AVAILABLE).count() == 1
    assert kpi["in_use"] == 2 and kpi["on_loan"] == 1 and kpi["maintenance"] == 0
    assert kpi["stock_units"] == sum(StockBalance.objects.values_list("quantity", flat=True)) == 2
    assert kpi["low_stock"] == 1  # toner: 2 <= 3
    assert kpi["empty_stock"] == 1  # papel
    assert kpi["operations_month"] == 4 + 2 + 2 + 1  # 4 entradas de equip., saída, empréstimo, 2 entradas, 1 saída


def test_sector_filter(scenario):
    kpi = selectors.indicators(_filters(sector=scenario["smu"]))
    assert kpi["equipment_total"] == 2 and kpi["in_use"] == 2
    by_sector = selectors.equipment_by_sector(_filters())
    assert dict(zip(by_sector["labels"], by_sector["values"], strict=True)) == {"SMU": 2, "SMS": 1}


def test_monthly_series(scenario):
    filters = _filters()
    months = selectors.months_between(filters.start, filters.end)
    assert len(months) == 12
    flows = selectors.entries_and_exits(filters, months)
    assert flows["entries"][-1] == 6 and flows["exits"][-1] == 2  # operações, não itens
    assert selectors.monthly_consumption(filters, months)["values"][-1] == 12
    top = selectors.top_withdrawn(filters)
    assert top["labels"] == ["Toner A", "Papel A4"] and top["values"] == [8, 4]
    evolution = selectors.stock_evolution(filters, months)["values"]
    assert evolution[-1] == 2 and evolution[0] == 0


def test_category_filter_splits_by_kind(scenario):
    toner_category = scenario["toner"].category
    kpi = selectors.indicators(_filters(category=toner_category))
    assert kpi["equipment_total"] == 4  # filtro de categoria de material não afeta equipamentos
    assert kpi["stock_units"] == 2


def test_months_and_period_helpers():
    assert selectors.default_period(date(2026, 11, 12)) == (date(2025, 12, 1), date(2026, 11, 12))
    assert selectors.months_between(date(2025, 11, 20), date(2026, 2, 1)) == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert selectors.month_label(date(2026, 3, 1)) == "mar/26"


def test_dashboard_page(client_for, admin_user, viewer_user, scenario):
    page = client_for(admin_user).get(reverse("core:home"), {"setor": scenario["smu"].pk}).content.decode()
    for text in [
        "Entradas e saídas",
        "Consumo mensal de materiais",
        "Materiais mais retirados",
        "Equipamentos distribuídos por setor",
        "Evolução do estoque",
        "Equipamentos por categoria",
        "Atividades recentes",
        "chart.umd",
    ]:
        assert text in page, text
    assert client_for(viewer_user).get(reverse("core:home")).status_code == 200


def test_dashboard_tolerates_bad_filters(client_for, admin_user):
    response = client_for(admin_user).get(
        reverse("core:home"), {"de": "2026-13-40", "ate": "2020-01-01", "setor": "abc"}
    )
    assert response.status_code == 200
