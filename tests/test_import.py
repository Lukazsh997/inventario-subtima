"""Importação de equipamentos por planilha (CSV/XLSX): validação, prévia e gravação tudo-ou-nada."""

import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.catalog import importer
from apps.catalog.models import Equipment, EquipmentStatus
from apps.inventory.models import EquipmentAssignment, StockOperation

from . import factories as f

HEADER = (
    "categoria;nome;fabricante;modelo;propriedade;locadora;patrimonio;serie;codigo_locadora;estado;"
    "data_aquisicao;observacoes;setor_atual;servidor_atual"
)


def csv_file(*lines, name="planilha.csv", encoding="utf-8-sig"):
    return SimpleUploadedFile(name, ("\r\n".join([HEADER, *lines]) + "\r\n").encode(encoding), "text/csv")


@pytest.fixture
def base(db):
    f.equipment_category()
    sector = f.sector("Secretaria Municipal de Urbanismo", acronym="SMU")
    person = f.recipient(sector, "Maria Souza", registration="12345")
    return sector, person


def test_template_has_all_columns_and_reads_back(base):
    content = importer.template_csv()
    records = importer.read_table(SimpleUploadedFile("modelo.csv", content))
    assert list(records[0].keys()) == importer.COLUMNS
    rows = importer.validate(records)
    assert rows[0].errors == []  # o exemplo do modelo é válido com a categoria/setor/servidor de teste


def test_valid_rows_import_with_entry_and_assignment(base, tech_user):
    sector, person = base
    records = importer.read_table(
        csv_file(
            "Computadores desktop;Desktop A;Dell;7010;proprio;;085.057;;;bom;10/03/2024;;;",
            "Computadores desktop;Desktop B;Dell;7010;locado;Locadora X;;SNB;ACES0001;regular;;;SMU;12345",
        )
    )
    rows = importer.validate(records)
    assert [r.errors for r in rows] == [[], []]
    created = importer.import_rows(actor=tech_user, rows=rows)
    assert len(created) == 2
    a = Equipment.objects.get(name="Desktop A")
    assert a.status == EquipmentStatus.AVAILABLE and a.acquisition_date.isoformat() == "2024-03-10"
    b = Equipment.objects.get(name="Desktop B")
    assert b.status == EquipmentStatus.IN_USE and b.current_sector == sector and b.current_recipient == person
    assert EquipmentAssignment.objects.filter(equipment=b, ended_at__isnull=True).exists()
    assert StockOperation.objects.count() == 2


def test_validation_errors_are_reported_per_line(base, tech_user):
    f.equipment(tech_user, serial_number="JA-EXISTE")
    records = importer.read_table(
        csv_file(
            "Categoria inexistente;X;;;;;;S1;;;;;;",
            "Computadores desktop;;;;;;;S2;;;;;;",
            "Computadores desktop;Sem id;;;;;;;;;;;;",
            "Computadores desktop;Locado;;;locado;;;S3;;;;;;",
            "Computadores desktop;Dup;;;;;;JA-EXISTE;;;;;;",
            "Computadores desktop;Rep1;;;;;;S9;;;;;;",
            "Computadores desktop;Rep2;;;;;;S9;;;;;;",
            "Computadores desktop;Data;;;;;;S4;;;31/02/2024;;;",
            "Computadores desktop;Setor;;;;;;S5;;;;;XYZ;",
            "Computadores desktop;Sem servidor;;;;;;S6;;;;;SMU;",
            "Computadores desktop;Estado;;;;;;S7;;quebradissimo;;;;",
        )
    )
    rows = importer.validate(records)
    messages = {r.line: " ".join(r.errors) for r in rows}
    assert "Categoria não encontrada" in messages[2]
    assert "Informe o nome" in messages[3]
    assert "patrimônio, série ou código" in messages[4]
    assert "informe a locadora" in messages[5]
    assert "Já cadastrado" in messages[6]
    assert messages[7] == "" and "repetido na planilha (linha 7)" in messages[8]
    assert "Data de aquisição inválida" in messages[9]
    assert "Setor não encontrado" in messages[10]
    assert "servidor responsável" in messages[11]
    assert "Estado inválido" in messages[12]
    with pytest.raises(ValidationError):
        importer.import_rows(actor=tech_user, rows=rows)
    assert Equipment.objects.count() == 1  # nada importado


def test_xlsx_and_cp1252_are_read(base):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(importer.COLUMNS)
    ws.append(["Computadores desktop", "Notebook", "", "", "", "", 85057, "", "", "", None, "", "", ""])
    buffer = io.BytesIO()
    wb.save(buffer)
    records = importer.read_table(SimpleUploadedFile("p.xlsx", buffer.getvalue()))
    assert records[0]["patrimonio"] == "85057"
    records = importer.read_table(csv_file("Computadores desktop;Impressão;;;;;;S1;;;;;;", encoding="cp1252"))
    assert records[0]["nome"] == "Impressão"


def test_bad_files_are_rejected(base):
    with pytest.raises(ValidationError, match="csv ou .xlsx"):
        importer.read_table(SimpleUploadedFile("p.txt", b"a"))
    with pytest.raises(ValidationError, match="ausentes"):
        importer.read_table(SimpleUploadedFile("p.csv", b"nome;serie\r\nX;1\r\n"))
    with pytest.raises(ValidationError, match="não reconhecidas"):
        importer.read_table(SimpleUploadedFile("p.csv", b"categoria;nome;cor\r\nA;B;C\r\n"))
    with pytest.raises(ValidationError, match="abrir"):
        importer.read_table(SimpleUploadedFile("p.xlsx", b"nao e xlsx"))


def test_view_preview_then_confirm(base, tech_user, client_for):
    client = client_for(tech_user)
    url = reverse("catalog:equipment_import")
    assert client.get(url).status_code == 200
    response = client.post(url, {"arquivo": csv_file("Computadores desktop;Desktop A;;;;;;SNA;;;;;;")})
    assert response.status_code == 200 and "prontos para importar" in response.content.decode()
    assert Equipment.objects.count() == 0  # a prévia não grava
    response = client.post(url, {"confirmar": "1"})
    assert response.status_code == 302
    assert Equipment.objects.filter(serial_number="SNA").exists()
    response = client.post(url, {"confirmar": "1"})  # não reimporta a mesma prévia
    assert "expirou" in response.content.decode()
    assert Equipment.objects.count() == 1


def test_view_with_errors_does_not_offer_confirmation(base, tech_user, client_for):
    client = client_for(tech_user)
    url = reverse("catalog:equipment_import")
    response = client.post(url, {"arquivo": csv_file("Inexistente;Desktop A;;;;;;SNA;;;;;;")})
    html = response.content.decode()
    assert "linhas com erro" in html and "Confirmar importação" not in html
    client.post(url, {"confirmar": "1"})
    assert Equipment.objects.count() == 0


def test_viewer_cannot_import(base, viewer_user, client_for):
    client = client_for(viewer_user)
    assert client.get(reverse("catalog:equipment_import")).status_code == 403
    assert client.get(reverse("catalog:equipment_import_template")).status_code == 403
