import csv
import io
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.inventory import services as inventory
from apps.inventory.models import OperationType as T
from apps.inventory.services import OperationData
from apps.reports.definitions import REPORTS

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(admin_user):
    smu = f.sector("Secretaria Municipal de Urbanismo", "SMU")
    maria = f.recipient(smu, "Maria Souza", registration="123")
    pc = f.equipment(admin_user, name="Desktop Dell", asset_tag="085.057", serial_number="")
    notebook = f.equipment(admin_user, name="Notebook Lenovo")
    printer = f.equipment(admin_user, name="Impressora HP")
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.EXIT,
        equipment_ids=[pc.pk],
        data=OperationData(destination_sector=smu, recipient=maria),
    )
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.LOAN,
        equipment_ids=[notebook.pk],
        data=OperationData(destination_sector=smu, recipient=maria, due_date=timezone.localdate() - timedelta(days=3)),
    )
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.MAINTENANCE_OUT,
        equipment_ids=[printer.pk],
        data=OperationData(third_party="Assistência HP"),
    )
    toner = f.consumable(admin_user, name="Toner HP 151A", reference="W1510A", min_stock=5, initial=10)
    inventory.move_consumables(
        actor=admin_user,
        op_type=T.EXIT,
        lines=[(toner, 6)],
        data=OperationData(destination_sector=smu, recipient=maria),
    )
    return {"smu": smu, "pc": pc, "toner": toner}


def _run(slug, **params):
    return REPORTS[slug].run(params)


def test_all_reports_listed(client_for, viewer_user):
    page = client_for(viewer_user).get(reverse("reports:index")).content.decode()
    assert all(r.title in page for r in REPORTS.values())
    assert len(REPORTS) == 10


def test_current_stock_and_below_minimum(data):
    stock = _run("estoque-atual")
    assert stock.rows[0]["saldo"] == 4 and stock.rows[0]["situacao"] == "No mínimo ou abaixo"
    assert _run("estoque-atual", situacao="normal").rows == []
    below = _run("abaixo-do-minimo")
    assert [r["material"] for r in below.rows] == ["Toner HP 151A"]
    assert below.rows[0]["sugestao"] == 5 + 6 - 4


def test_movement_histories(data):
    exits = _run("historico-saidas")
    assert {r["item"] for r in exits.rows} == {"Desktop Dell", "Toner HP 151A"}
    toner_row = next(r for r in exits.rows if r["item"] == "Toner HP 151A")
    assert (toner_row["quantidade"], toner_row["setor"], toner_row["recebedor"]) == (6, "SMU", "Maria Souza (mat. 123)")
    entries = _run("historico-entradas")
    assert len(entries.rows) == 4  # 3 equipamentos + entrada do toner
    future = timezone.localdate() + timedelta(days=1)
    assert _run("historico-saidas", de=future).rows == []


def test_monthly_consumption_pivot(data):
    result = _run("consumo-mensal")
    row = result.rows[0]
    assert row["material"] == "Toner HP 151A" and row["total"] == 6
    assert result.columns[-1].label == "Total"


def test_equipment_reports(data):
    by_sector = _run("equipamentos-por-setor", setor=data["smu"])
    assert {r["equipamento"] for r in by_sector.rows} == {"Desktop Dell", "Notebook Lenovo"}
    by_person = _run("equipamentos-por-responsavel", servidor="123")
    assert len(by_person.rows) == 2 and by_person.rows[0]["responsavel"] == "Maria Souza"
    loans = _run("equipamentos-emprestados", atrasados=True)
    assert loans.rows[0]["atraso"] == 3
    maintenance = _run("equipamentos-em-manutencao")
    assert maintenance.rows[0]["assistencia"] == "Assistência HP"


def test_equipment_history_by_scanned_code(data):
    result = _run("historico-equipamento", equipamento="085057")
    assert [r["tipo"] for r in result.rows] == ["Entrada", "Saída (entrega)"]
    assert ("Identificação", "Patr. 085.057") in result.header
    assert _run("historico-equipamento", equipamento="nao-existe").summary == ["Nenhum equipamento encontrado."]


def test_csv_export_opens_in_excel(client_for, viewer_user, data):
    response = client_for(viewer_user).get(reverse("reports:show", args=["historico-saidas"]), {"formato": "csv"})
    assert response["Content-Type"].startswith("text/csv")
    assert "historico-saidas-" in response["Content-Disposition"]
    content = response.content.decode("utf-8")
    assert content.startswith("﻿")
    rows = list(csv.reader(io.StringIO(content.lstrip("﻿")), delimiter=";"))
    assert rows[0][:3] == ["Data", "Operação", "Item"]
    assert len(rows) == 3


def test_csv_neutralizes_formulas():
    from apps.reports.base import Column, ReportResult
    from apps.reports.exporters import to_csv

    content = to_csv(ReportResult(columns=[Column("a", "A")], rows=[{"a": '=HYPERLINK("x")'}])).decode()
    assert "'=HYPERLINK" in content


def test_pdf_export(client_for, admin_user, data):
    response = client_for(admin_user).get(
        reverse("reports:show", args=["equipamentos-por-setor"]), {"setor": data["smu"].pk, "formato": "pdf"}
    )
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 3000


def test_report_pages_render_with_filters(client_for, admin_user, data):
    client = client_for(admin_user)
    for slug in REPORTS:
        assert client.get(reverse("reports:show", args=[slug])).status_code == 200, slug
    page = client.get(reverse("reports:show", args=["historico-equipamento"]), {"equipamento": "085.057"})
    assert "Desktop Dell" in page.content.decode()
    assert client.get(reverse("reports:show", args=["nao-existe"])).status_code == 404
