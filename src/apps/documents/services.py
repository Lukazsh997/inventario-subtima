"""Emissão e ciclo de vida dos termos, e versionamento dos modelos."""

import hashlib
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.accounts.permissions import Capability, ensure_capability
from apps.audit import services as audit
from apps.audit.models import AuditAction
from apps.core.numbering import next_number
from apps.inventory.models import StockOperation

from . import rendering
from .models import STATUS_FLOW, DocumentStatus, DocumentStatusChange, DocumentTemplate, GeneratedDocument, ItemKind

logger = logging.getLogger("patrimonio.documents")
D = DocumentStatus


# --- Escolha do modelo -----------------------------------------------------------------


def operation_kind(operation: StockOperation) -> str | None:
    movement = operation.movements.order_by("id").first()
    if movement is None:
        return None
    return ItemKind.EQUIPMENT if movement.equipment_id else ItemKind.CONSUMABLE


def template_for(operation: StockOperation) -> DocumentTemplate | None:
    kind = operation_kind(operation)
    for template in DocumentTemplate.objects.filter(active=True, item_kind=kind).order_by("name"):
        if operation.type in template.operation_types:
            return template
    return None


# --- Emissão ---------------------------------------------------------------------------


@transaction.atomic
def issue(
    *,
    actor,
    operation: StockOperation,
    template: DocumentTemplate | None = None,
    replaces: GeneratedDocument | None = None,
) -> GeneratedDocument:
    """Gera o PDF da operação a partir do modelo ativo e o guarda no banco."""
    ensure_capability(actor, Capability.INVENTORY_OPERATE)
    # Consulta direta: o atributo is_reversed pode estar em cache numa instância antiga da operação.
    if StockOperation.objects.filter(reverses=operation).exists() and replaces is None:
        raise ValidationError("A operação foi estornada; não é possível emitir termo para ela.")
    template = template or template_for(operation)
    if template is None:
        raise ValidationError(
            f'Não há modelo de termo configurado para "{operation.get_type_display()}" '
            f"de {dict(ItemKind.choices).get(operation_kind(operation), 'itens')}."
        )
    number = next_number("TR")
    data = rendering.build_context(operation, number=number)
    pdf = rendering.render_pdf(template, data)
    document = GeneratedDocument.objects.create(
        number=number,
        operation=operation,
        template=template,
        pdf=pdf,
        sha256=hashlib.sha256(pdf).hexdigest(),
        size=len(pdf),
        data=data,
        issued_by=actor,
        replaces=replaces,
    )
    DocumentStatusChange.objects.create(
        document=document,
        from_status="",
        to_status=D.GENERATED,
        changed_by=actor,
        note=f"Substitui {replaces.number}" if replaces else "",
    )
    audit.record(
        AuditAction.CREATE, user=actor, instance=document, summary=f"{number} · {template.name} · {operation.number}"
    )
    logger.info("Termo emitido", extra={"termo": number, "operacao": operation.number, "bytes": len(pdf)})
    return document


def try_issue(*, actor, operation: StockOperation) -> tuple[GeneratedDocument | None, str]:
    """Emissão automática após registrar a operação: falhar aqui não desfaz a operação."""
    if template_for(operation) is None:
        return None, "Nenhum modelo de termo está configurado para este tipo de operação."
    try:
        return issue(actor=actor, operation=operation), ""
    except ValidationError as error:
        return None, " ".join(error.messages)
    except Exception:  # noqa: BLE001 - falha de PDF não pode desfazer a operação já registrada
        logger.exception("Falha ao gerar termo", extra={"operacao": operation.number})
        return None, 'Não foi possível gerar o PDF agora. Use "Gerar termo" na operação para tentar de novo.'


# --- Situação --------------------------------------------------------------------------


def allowed_next(document: GeneratedDocument) -> list[str]:
    if document.status == D.CANCELLED:
        return []
    position = STATUS_FLOW.index(document.status)
    return [*STATUS_FLOW[position + 1 :], D.CANCELLED]


@transaction.atomic
def change_status(*, actor, document: GeneratedDocument, status: str, note: str = "") -> GeneratedDocument:
    ensure_capability(actor, Capability.INVENTORY_OPERATE)
    document = GeneratedDocument.objects.select_for_update().get(pk=document.pk)
    if status not in allowed_next(document):
        raise ValidationError(
            f'Não é possível passar de "{document.get_status_display()}" para '
            f'"{D(status).label if status in D.values else status}".'
        )
    if status == D.CANCELLED and not note.strip():
        raise ValidationError("Informe o motivo do cancelamento.")
    previous = document.status
    document.status = status
    document.save(update_fields=["status"])
    DocumentStatusChange.objects.create(
        document=document, from_status=previous, to_status=status, changed_by=actor, note=note.strip()[:255]
    )
    audit.record(
        AuditAction.UPDATE,
        user=actor,
        instance=document,
        changes={"situacao": {"de": D(previous).label, "para": D(status).label}},
    )
    return document


@transaction.atomic
def register_print(*, actor, document: GeneratedDocument) -> GeneratedDocument:
    """Cada abertura para impressão é contada; a primeira marca o termo como Impresso."""
    document = GeneratedDocument.objects.select_for_update().get(pk=document.pk)
    document.print_count += 1
    document.save(update_fields=["print_count"])
    if document.status == D.GENERATED:
        DocumentStatusChange.objects.create(
            document=document,
            from_status=D.GENERATED,
            to_status=D.PRINTED,
            changed_by=actor,
            note="Aberto para impressão",
        )
        document.status = D.PRINTED
        document.save(update_fields=["status"])
    return document


@transaction.atomic
def reissue(*, actor, document: GeneratedDocument, reason: str) -> GeneratedDocument:
    """Cancela o termo e emite outro (novo número) com o modelo ativo atual."""
    if not reason.strip():
        raise ValidationError("Informe o motivo da reemissão.")
    change_status(actor=actor, document=document, status=D.CANCELLED, note=f"Reemitido: {reason}")
    return issue(actor=actor, operation=document.operation, replaces=document)


def cancel_for_reversed_operation(*, operation, reversal, actor) -> None:
    """Assinante do evento OPERATION_REVERSED: o termo da operação estornada é cancelado."""
    for document in GeneratedDocument.objects.filter(operation=operation).exclude(status=D.CANCELLED):
        change_status(
            actor=actor, document=document, status=D.CANCELLED, note=f"Operação estornada por {reversal.number}"
        )


# --- Modelos ---------------------------------------------------------------------------


@transaction.atomic
def save_template_version(
    *,
    actor,
    base: DocumentTemplate | None,
    code: str,
    name: str,
    item_kind: str,
    operation_types: list[str],
    css: str,
    body: str,
    source: str,
) -> DocumentTemplate:
    """Cria a próxima versão de um modelo (ou o primeiro). A versão anterior é desativada, nunca alterada."""
    ensure_capability(actor, Capability.TEMPLATES_MANAGE)
    try:
        rendering.check_template(css, body)
    except rendering.TemplateSyntaxError as error:
        raise ValidationError(f"Erro de sintaxe no modelo: {error}") from error
    if not operation_types:
        raise ValidationError("Escolha pelo menos um tipo de operação.")
    code = base.code if base else code
    conflicts = [
        t
        for t in DocumentTemplate.objects.filter(active=True, item_kind=item_kind).exclude(code=code)
        if set(t.operation_types) & set(operation_types)
    ]
    if conflicts:
        raise ValidationError(
            f"Já existe modelo ativo para algum desses tipos: {conflicts[0].name}. "
            "Desative-o ou retire o tipo dele antes."
        )
    last = DocumentTemplate.objects.filter(code=code).aggregate(v=Max("version"))["v"] or 0
    DocumentTemplate.objects.filter(code=code, active=True).update(active=False)
    template = DocumentTemplate.objects.create(
        code=code,
        version=last + 1,
        name=name.strip(),
        item_kind=item_kind,
        operation_types=list(operation_types),
        css=css,
        body=body,
        source=source.strip(),
        created_by=actor,
    )
    audit.record(AuditAction.CREATE, user=actor, instance=template, summary=f"{template.name} v{template.version}")
    return template


@transaction.atomic
def set_template_active(*, actor, template: DocumentTemplate, active: bool) -> DocumentTemplate:
    ensure_capability(actor, Capability.TEMPLATES_MANAGE)
    if active:
        newest = DocumentTemplate.objects.filter(code=template.code).order_by("-version").first()
        if newest.pk != template.pk:
            raise ValidationError("Só a versão mais recente pode ser reativada.")
    template.active = active
    template.save(update_fields=["active"])
    audit.record(AuditAction.REACTIVATE if active else AuditAction.DEACTIVATE, user=actor, instance=template)
    return template
