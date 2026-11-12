"""Módulo de documentos e termos (requisito 8)."""

import hashlib
import subprocess
import tempfile

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.documents import rendering, services
from apps.documents.models import DocumentStatus as D
from apps.documents.models import DocumentTemplate, GeneratedDocument
from apps.inventory import services as inventory
from apps.inventory.models import OperationType as T
from apps.inventory.services import OperationData
from apps.organization import services as org

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def org_tree(admin_user):
    gov = org.save_sector(actor=admin_user, sector=None, name="Secretaria Municipal de Governo", acronym="SMG")
    support = org.save_sector(
        actor=admin_user, sector=None, name="Suporte de Informática", acronym="SUBTIMA", parent=gov
    )
    desans = org.save_sector(actor=admin_user, sector=None, name="Departamento de Saneamento", acronym="DESANS")
    urb = org.save_sector(actor=admin_user, sector=None, name="Secretaria Municipal de Urbanismo", acronym="SMU")
    return {"support": support, "desans": desans, "urb": urb}


@pytest.fixture
def transfer_op(admin_user, org_tree):
    tech = f.recipient(org_tree["support"], "Técnico Suporte")
    agent = f.recipient(org_tree["desans"], "Agente DESANS", registration="5566")
    ids = []
    for serial in ["2419391010456", "2550191010999"]:
        item = inventory.register_equipment(
            actor=admin_user,
            data=f.equipment_data(
                name="Estabilizador", manufacturer="TSSHARA", model="-POWEREST", serial_number=serial
            ),
            in_use=OperationData(destination_sector=org_tree["support"], recipient=tech),
        )
        ids.append(item.pk)
    return inventory.move_equipment(
        actor=admin_user,
        op_type=T.TRANSFER,
        equipment_ids=ids,
        data=OperationData(destination_sector=org_tree["desans"], recipient=agent),
    )


@pytest.fixture
def paper_exit(admin_user, org_tree):
    paper = f.consumable(admin_user, name="Papel Plotter", initial=8000)
    joana = f.recipient(org_tree["urb"], "Joana Pereira", registration="12345")
    return inventory.move_consumables(
        actor=admin_user,
        op_type=T.EXIT,
        lines=[(paper, 7650)],
        data=OperationData(destination_sector=org_tree["urb"], recipient=joana),
    )


def pdf_text(pdf: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
        fh.write(pdf)
        fh.flush()
        return subprocess.run(["pdftotext", "-layout", fh.name, "-"], capture_output=True, text=True, check=True).stdout


def test_institutional_templates_installed():
    names = set(DocumentTemplate.objects.filter(active=True).values_list("name", flat=True))
    assert names == {"Termo de Transferência", "Termo de Recebimento de Resmas"}


def test_transfer_term_reproduces_original_text(admin_user, transfer_op):
    document = services.issue(actor=admin_user, operation=transfer_op)
    text = " ".join(pdf_text(bytes(document.pdf)).split())
    for expected in [
        "PREFEITURA MUNICIPAL DE DUQUE DE CAXIAS",
        "SECRETARIA MUNICIPAL DE GOVERNO",
        "TERMO DE TRANSFERÊNCIA",
        "Comunico a esta Subsecretaria a TRANSFERÊNCIA do(s) bem(s) permanente(s), abaixo relacionado:",
        "Descrição – Estado de Conservação",
        "Marca/Modelo",
        "Patrimônio / Série",
        "ESTABILIZADOR - BOM",
        "TSSHARA -POWEREST",
        "2419391010456",
        "2550191010999",
        "Transferido da Secretaria Municipal de Governo",
        "Setor: Suporte de Informática / SUBTIMA",
        "Para: DESANS",
        "Responsável pela transferência (nome legível e matrícula)",
        "Agente recebedor (nome legível e matrícula)",
        document.number,
        transfer_op.number,
    ]:
        assert expected in text, expected


def test_receipt_term_fills_receiver_and_items(admin_user, paper_exit):
    document = services.issue(actor=admin_user, operation=paper_exit)
    text = " ".join(pdf_text(bytes(document.pdf)).split())
    for expected in [
        "TERMO DE RECEBIMENTO DE RESMAS",
        "Joana Pereira (mat. 12345)",
        "da Secretaria Municipal de Urbanismo declaro ter recebido",
        "7650 unidades (Papel Plotter)",
        "Recebedor (Assinatura e Matrícula)",
        "Alameda Esmeralda, 206 - Jardim Primavera",
        "CNPJ 29.138.328/0001-50",
    ]:
        assert expected in text, expected


def test_pdf_stored_in_database_with_hash_and_snapshot(admin_user, paper_exit):
    document = services.issue(actor=admin_user, operation=paper_exit)
    document.refresh_from_db()
    pdf = bytes(document.pdf)
    assert pdf.startswith(b"%PDF") and document.size == len(pdf)
    assert document.sha256 == hashlib.sha256(pdf).hexdigest()
    assert document.number.startswith("TR-") and document.issued_by == admin_user
    assert document.data["recebedor"]["nome"] == "Joana Pereira"
    assert document.status == D.GENERATED
    assert document.status_changes.get().to_status == D.GENERATED


def test_no_template_means_clear_message_not_invented_text(admin_user, org_tree):
    item = f.equipment(admin_user)
    op = inventory.move_equipment(
        actor=admin_user,
        op_type=T.EXIT,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=org_tree["urb"], recipient=f.recipient(org_tree["urb"])),
    )
    assert services.template_for(op) is None  # Termo de Responsabilidade ainda não fornecido
    with pytest.raises(ValidationError, match="Não há modelo de termo configurado"):
        services.issue(actor=admin_user, operation=op)
    document, problem = services.try_issue(actor=admin_user, operation=op)
    assert document is None and "Nenhum modelo" in problem


def test_status_flow_and_print_counter(admin_user, tech_user, viewer_user, paper_exit):
    document = services.issue(actor=admin_user, operation=paper_exit)
    services.register_print(actor=tech_user, document=document)
    services.register_print(actor=tech_user, document=document)
    document.refresh_from_db()
    assert (document.status, document.print_count) == (D.PRINTED, 2)
    services.change_status(actor=tech_user, document=document, status=D.SIGNED, note="via na pasta 11/2026")
    with pytest.raises(ValidationError):
        services.change_status(actor=tech_user, document=document, status=D.AWAITING)  # não volta
    with pytest.raises(ValidationError, match="motivo"):
        services.change_status(actor=tech_user, document=document, status=D.CANCELLED)
    with pytest.raises(PermissionDenied):
        services.change_status(actor=viewer_user, document=document, status=D.ARCHIVED)
    services.change_status(actor=tech_user, document=document, status=D.ARCHIVED)
    assert list(document.status_changes.values_list("to_status", flat=True)) == [
        D.GENERATED,
        D.PRINTED,
        D.SIGNED,
        D.ARCHIVED,
    ]


def test_reversal_cancels_term(admin_user, paper_exit):
    document = services.issue(actor=admin_user, operation=paper_exit)
    inventory.reverse_operation(actor=admin_user, operation=paper_exit, justification="quantidade errada")
    document.refresh_from_db()
    assert document.status == D.CANCELLED
    assert "estornada" in document.status_changes.last().note
    with pytest.raises(ValidationError, match="estornada"):
        services.issue(actor=admin_user, operation=paper_exit)


def test_reissue_cancels_old_and_links_new(admin_user, paper_exit):
    old = services.issue(actor=admin_user, operation=paper_exit)
    new = services.reissue(actor=admin_user, document=old, reason="papel rasgado antes de assinar")
    old.refresh_from_db()
    assert old.status == D.CANCELLED and new.replaces == old and new.number != old.number


def test_template_versioning_keeps_issued_documents(admin_user, tech_user, paper_exit):
    v1 = DocumentTemplate.objects.get(code="termo-recebimento-resmas")
    first = services.issue(actor=admin_user, operation=paper_exit)
    with pytest.raises(PermissionDenied):
        services.save_template_version(
            actor=tech_user,
            base=v1,
            code="",
            name=v1.name,
            item_kind=v1.item_kind,
            operation_types=v1.operation_types,
            css=v1.css,
            body=v1.body,
            source="x",
        )
    v2 = services.save_template_version(
        actor=admin_user,
        base=v1,
        code="",
        name="Termo de Recebimento de Material",
        item_kind=v1.item_kind,
        operation_types=v1.operation_types,
        css=v1.css,
        body=v1.body.replace("TERMO DE RECEBIMENTO DE RESMAS", "TERMO DE RECEBIMENTO DE MATERIAL"),
        source="Título alterado com autorização da SUBTIMA",
    )
    v1.refresh_from_db()
    assert (v1.active, v2.active, v2.version, v2.code) == (False, True, 2, v1.code)
    first.refresh_from_db()
    assert first.template == v1  # termo antigo continua ligado à versão usada
    second = services.reissue(actor=admin_user, document=first, reason="novo título")
    assert "TERMO DE RECEBIMENTO DE MATERIAL" in pdf_text(bytes(second.pdf))


def test_template_syntax_and_conflicts_validated(admin_user):
    with pytest.raises(ValidationError, match="sintaxe"):
        services.save_template_version(
            actor=admin_user,
            base=None,
            code="x",
            name="X",
            item_kind="equipamento",
            operation_types=["saida"],
            css="",
            body="{% for x in %}",
            source="teste",
        )
    with pytest.raises(ValidationError, match="Já existe modelo ativo"):
        services.save_template_version(
            actor=admin_user,
            base=None,
            code="y",
            name="Y",
            item_kind="equipamento",
            operation_types=["transferencia"],
            css="",
            body="<p>x</p>",
            source="teste",
        )


def test_templates_cannot_reach_database_objects(admin_user, paper_exit):
    """O modelo só recebe dados simples: não há como chegar a senha, sessão ou outras tabelas."""
    data = rendering.build_context(paper_exit, number="TR-TESTE")

    def only_plain(value):
        if isinstance(value, dict):
            return all(isinstance(k, str) and only_plain(v) for k, v in value.items())
        if isinstance(value, list):
            return all(only_plain(v) for v in value)
        return isinstance(value, str | int | float | bool) or value is None

    assert only_plain(data)
    template = DocumentTemplate(css="", body="{% load static %}")
    with pytest.raises(rendering.TemplateSyntaxError):
        rendering.render_html(template, data)
    malicious = DocumentTemplate(css="", body="{{ responsavel.nome.__class__ }}{% include 'base.html' %}")
    with pytest.raises(Exception):  # noqa: B017 - include não tem carregador: falha sem expor nada
        rendering.render_html(malicious, data)


def test_operation_form_generates_term_automatically(client_for, tech_user, org_tree):
    paper = f.consumable(tech_user, name="Papel A4", initial=10)
    joana = f.recipient(org_tree["urb"], "Joana")
    response = client_for(tech_user).post(
        reverse("inventory:consumable_operation"),
        {
            "type": T.EXIT,
            "consumable_id": [paper.pk],
            "quantity": ["2"],
            "destination_sector": org_tree["urb"].pk,
            "recipient": joana.pk,
            "generate_document": "on",
        },
        follow=True,
    )
    document = GeneratedDocument.objects.get()
    page = response.content.decode()
    assert document.number in page and "pronto para impressão" in page


def test_pdf_download_print_and_permissions(client_for, admin_user, viewer_user, tech_user, paper_exit):
    document = services.issue(actor=admin_user, operation=paper_exit)
    viewer = client_for(viewer_user)
    response = viewer.get(reverse("documents:pdf", args=[document.pk]), {"imprimir": "1"})
    assert response["Content-Type"] == "application/pdf" and response.content == bytes(document.pdf)
    document.refresh_from_db()
    assert document.print_count == 0  # perfil Consulta vê, mas não registra impressão
    assert viewer.post(reverse("documents:status", args=[document.pk]), {"status": D.SIGNED}).status_code == 403
    tech = client_for(tech_user)
    tech.get(reverse("documents:pdf", args=[document.pk]), {"imprimir": "1"})
    document.refresh_from_db()
    assert (document.status, document.print_count) == (D.PRINTED, 1)
    for name, args in [("documents:list", []), ("documents:detail", [document.pk]), ("documents:template_list", [])]:
        assert tech.get(reverse(name, args=args)).status_code == 200
    assert tech.get(reverse("documents:template_create")).status_code == 403


def test_template_pages_for_admin(client_for, admin_user, paper_exit):
    client = client_for(admin_user)
    template = DocumentTemplate.objects.get(code="termo-recebimento-resmas")
    assert client.get(reverse("documents:template_edit", args=[template.pk])).status_code == 200
    preview = client.get(reverse("documents:template_preview", args=[template.pk]))
    assert preview["Content-Type"] == "application/pdf"
    assert not GeneratedDocument.objects.exists()  # prévia não grava termo
    assert client.get(reverse("documents:asset_image", args=["brasao"]))["Content-Type"] == "image/png"


def test_issued_documents_report(admin_user, paper_exit):
    from apps.reports.definitions import REPORTS

    services.issue(actor=admin_user, operation=paper_exit)
    result = REPORTS["termos-emitidos"].run({"situacao": "pendentes"})
    assert len(result.rows) == 1 and result.rows[0]["recebedor"] == "Joana Pereira (mat. 12345)"
