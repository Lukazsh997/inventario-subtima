"""Casos de uso de movimentação de estoque.

Regras centrais:
- Toda alteração de saldo ou de situação de equipamento acontece aqui, dentro de
  uma transação, com bloqueio das linhas envolvidas (SELECT ... FOR UPDATE) em
  ordem de id, para que operações simultâneas não deixem estoque inconsistente
  nem causem deadlock.
- Operações e movimentações nunca são alteradas: erros são corrigidos por estorno.
"""

from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.permissions import Capability, ensure_capability
from apps.audit import services as audit
from apps.audit.models import AuditAction
from apps.catalog.models import Consumable, Equipment, EquipmentStatus
from apps.catalog.services import apply_equipment_fields
from apps.core import events
from apps.core.numbering import next_number
from apps.organization.models import Location, Recipient, Sector

from .models import (
    AssignmentKind,
    EquipmentAssignment,
    OperationAccessory,
    OperationType,
    StockBalance,
    StockMovement,
    StockOperation,
)

S = EquipmentStatus
T = OperationType


@dataclass(frozen=True)
class EquipmentRule:
    allowed_from: frozenset[str]
    status_after: str
    assignment: str | None  # tipo da nova atribuição aberta (None = volta ao estoque ou baixa)
    needs_destination: bool = False
    needs_recipient: bool = False
    needs_third_party: bool = False
    needs_justification: bool = False
    capability: Capability = Capability.INVENTORY_OPERATE


EQUIPMENT_RULES: dict[str, EquipmentRule] = {
    T.EXIT: EquipmentRule(
        frozenset({S.AVAILABLE}), S.IN_USE, AssignmentKind.USE, needs_destination=True, needs_recipient=True
    ),
    T.TRANSFER: EquipmentRule(
        frozenset({S.IN_USE}), S.IN_USE, AssignmentKind.USE, needs_destination=True, needs_recipient=True
    ),
    T.RETURN: EquipmentRule(frozenset({S.IN_USE}), S.AVAILABLE, None),
    T.LOAN: EquipmentRule(
        frozenset({S.AVAILABLE}), S.ON_LOAN, AssignmentKind.LOAN, needs_destination=True, needs_recipient=True
    ),
    T.LOAN_RETURN: EquipmentRule(frozenset({S.ON_LOAN}), S.AVAILABLE, None),
    T.MAINTENANCE_OUT: EquipmentRule(
        frozenset({S.AVAILABLE, S.IN_USE}), S.MAINTENANCE, AssignmentKind.MAINTENANCE, needs_third_party=True
    ),
    T.MAINTENANCE_RETURN: EquipmentRule(frozenset({S.MAINTENANCE}), S.AVAILABLE, None),
    T.WRITE_OFF: EquipmentRule(
        frozenset({S.AVAILABLE, S.IN_USE, S.MAINTENANCE}),
        S.WRITTEN_OFF,
        None,
        needs_justification=True,
        capability=Capability.EQUIPMENT_WRITE_OFF,
    ),
}


@dataclass
class OperationData:
    """Dados comuns de uma operação, já validados pelo formulário."""

    destination_sector: Sector | None = None
    destination_location: Location | None = None
    recipient: Recipient | None = None
    origin_sector: Sector | None = None
    due_date: date | None = None
    third_party: str = ""
    justification: str = ""
    notes: str = ""
    accessories: list[tuple[str, int]] | None = None


def _create_operation(actor, op_type: str, data: OperationData, *, reverses: StockOperation | None = None):
    operation = StockOperation.objects.create(
        number=next_number("OP"),
        type=op_type,
        performed_by=actor,
        origin_sector=data.origin_sector,
        destination_sector=data.destination_sector,
        destination_location=data.destination_location,
        recipient=data.recipient,
        due_date=data.due_date,
        third_party=data.third_party.strip(),
        justification=data.justification.strip(),
        notes=data.notes.strip(),
        reverses=reverses,
    )
    for description, quantity in data.accessories or []:
        if description.strip():
            OperationAccessory.objects.create(
                operation=operation, description=description.strip(), quantity=max(1, quantity)
            )
    return operation


def _validate_common(rule: EquipmentRule, data: OperationData) -> None:
    errors = []
    if rule.needs_destination and data.destination_sector is None:
        errors.append("Informe o setor de destino.")
    if data.destination_sector is not None and not data.destination_sector.active:
        errors.append("O setor de destino está desativado.")
    if rule.needs_recipient and data.recipient is None:
        errors.append("Informe o servidor que recebe.")
    if data.recipient is not None and not data.recipient.active:
        errors.append("O servidor informado está desativado.")
    if data.destination_location is not None and data.destination_location.sector_id != getattr(
        data.destination_sector, "pk", None
    ):
        errors.append("O local escolhido não pertence ao setor de destino.")
    if rule.needs_third_party and not data.third_party.strip():
        errors.append("Informe a assistência técnica ou fornecedor.")
    if rule.needs_justification and not data.justification.strip():
        errors.append("Informe a justificativa.")
    if errors:
        raise ValidationError(errors)


def _open_assignment(
    equipment: Equipment,
    kind: str,
    operation: StockOperation,
    *,
    sector=None,
    location=None,
    recipient=None,
    third_party="",
    due_date=None,
) -> None:
    EquipmentAssignment.objects.create(
        equipment=equipment,
        kind=kind,
        sector=sector,
        location=location,
        recipient=recipient,
        third_party=third_party,
        due_date=due_date,
        started_at=operation.performed_at,
        opened_by=operation,
    )


def _close_open_assignment(equipment: Equipment, operation: StockOperation) -> None:
    EquipmentAssignment.objects.filter(equipment=equipment, ended_at__isnull=True).update(
        ended_at=operation.performed_at, closed_by=operation
    )


def _audit_operation(actor, operation: StockOperation, action=AuditAction.OPERATION) -> None:
    lines = operation.movements.select_related("equipment", "consumable")
    items = [f"{m.item} ({m.quantity:+d})" if m.consumable_id else str(m.item) for m in lines]
    audit.record(
        action, user=actor, instance=operation, changes={"itens": {"de": None, "para": "; ".join(items)[:1000]}}
    )


# --- Equipamentos ----------------------------------------------------------------------


@transaction.atomic
def register_equipment(*, actor, data: dict, in_use: OperationData | None = None) -> Equipment:
    """Entrada de equipamento no inventário: cria o cadastro e a operação de Entrada.

    in_use: para o inventário inicial de equipamentos que já estão em uso em um
    setor; nesse caso o equipamento entra com situação "Em uso" e atribuição aberta.
    """
    ensure_capability(actor, Capability.CATALOG_MANAGE)
    ensure_capability(actor, Capability.INVENTORY_OPERATE)
    equipment = Equipment(created_by=actor)
    apply_equipment_fields(equipment, data)
    op_data = in_use or OperationData()
    if in_use is not None:
        _validate_common(EQUIPMENT_RULES[T.EXIT], in_use)
    equipment.status = S.IN_USE if in_use else S.AVAILABLE
    equipment.current_sector = op_data.destination_sector
    equipment.current_location = op_data.destination_location
    equipment.current_recipient = op_data.recipient
    try:
        with transaction.atomic():
            equipment.save()
    except IntegrityError as exc:
        raise ValidationError("Identificador já cadastrado em outro equipamento.") from exc

    operation = _create_operation(actor, T.ENTRY, op_data)
    StockMovement.objects.create(
        operation=operation, equipment=equipment, quantity=1, status_before="", status_after=equipment.status
    )
    if in_use:
        _open_assignment(
            equipment,
            AssignmentKind.USE,
            operation,
            sector=op_data.destination_sector,
            location=op_data.destination_location,
            recipient=op_data.recipient,
        )
    audit.record(
        AuditAction.CREATE,
        user=actor,
        instance=equipment,
        changes=audit.diff(
            {}, audit.snapshot(equipment, ["name", "serial_number", "asset_tag", "lessor_code", "status"])
        ),
    )
    _audit_operation(actor, operation)
    return equipment


@transaction.atomic
def move_equipment(*, actor, op_type: str, equipment_ids: list[int], data: OperationData) -> StockOperation:
    """Saída, transferência, devolução, empréstimo, manutenção ou baixa de um ou mais equipamentos."""
    rule = EQUIPMENT_RULES.get(op_type)
    if rule is None:
        raise ValidationError("Tipo de operação inválido para equipamentos.")
    ensure_capability(actor, Capability.INVENTORY_OPERATE)
    ensure_capability(actor, rule.capability)
    ids = sorted(set(equipment_ids))
    if not ids:
        raise ValidationError("Selecione pelo menos um equipamento.")
    _validate_common(rule, data)

    equipment_list = list(Equipment.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(equipment_list) != len(ids):
        raise ValidationError("Algum equipamento selecionado não existe mais.")

    errors = [
        f'{e}: está "{e.get_status_display()}" e não pode receber "{T(op_type).label}".'
        for e in equipment_list
        if e.status not in rule.allowed_from
    ]
    if errors:
        raise ValidationError(errors)

    if op_type == T.TRANSFER:
        origins = {e.current_sector_id for e in equipment_list}
        if len(origins) != 1:
            raise ValidationError("Na transferência, todos os equipamentos devem estar no mesmo setor de origem.")
        if data.destination_sector.pk in origins and data.recipient.pk == equipment_list[0].current_recipient_id:
            raise ValidationError("O destino e o responsável são os mesmos da situação atual.")
        data.origin_sector = equipment_list[0].current_sector
    elif data.origin_sector is None:
        origins = {e.current_sector_id for e in equipment_list}
        if len(origins) == 1:
            data.origin_sector = equipment_list[0].current_sector

    operation = _create_operation(actor, op_type, data)
    for equipment in equipment_list:
        StockMovement.objects.create(
            operation=operation,
            equipment=equipment,
            quantity=1,
            status_before=equipment.status,
            status_after=rule.status_after,
            sector_before=equipment.current_sector,
            location_before=equipment.current_location,
            recipient_before=equipment.current_recipient,
        )
        _close_open_assignment(equipment, operation)
        if rule.assignment is not None:
            keep_sector = rule.assignment == AssignmentKind.MAINTENANCE
            _open_assignment(
                equipment,
                rule.assignment,
                operation,
                sector=equipment.current_sector if keep_sector else data.destination_sector,
                location=equipment.current_location if keep_sector else data.destination_location,
                recipient=equipment.current_recipient if keep_sector else data.recipient,
                third_party=data.third_party,
                due_date=data.due_date,
            )
        equipment.status = rule.status_after
        if rule.assignment in (AssignmentKind.USE, AssignmentKind.LOAN):
            equipment.current_sector = data.destination_sector
            equipment.current_location = data.destination_location
            equipment.current_recipient = data.recipient
        elif rule.assignment is None:
            equipment.current_sector = None
            equipment.current_location = None
            equipment.current_recipient = None
        # Em manutenção o equipamento mantém o setor/responsável de origem para referência.
        equipment.save(
            update_fields=["status", "current_sector", "current_location", "current_recipient", "updated_at"]
        )
    _audit_operation(actor, operation)
    return operation


# --- Materiais de consumo --------------------------------------------------------------

CONSUMABLE_SIGN = {T.ENTRY: 1, T.EXIT: -1, T.RETURN: 1}


@transaction.atomic
def move_consumables(
    *, actor, op_type: str, lines: list[tuple[Consumable, int]], data: OperationData
) -> StockOperation:
    """Entrada, saída, devolução ou ajuste de materiais de consumo.

    lines: (material, quantidade). Para ajuste, a quantidade tem sinal (+ acrescenta, − retira).
    """
    if op_type == T.ADJUSTMENT:
        ensure_capability(actor, Capability.STOCK_ADJUST)
        if not data.justification.strip():
            raise ValidationError("O ajuste de estoque exige justificativa.")
    elif op_type in CONSUMABLE_SIGN:
        ensure_capability(actor, Capability.INVENTORY_OPERATE)
    else:
        raise ValidationError("Tipo de operação inválido para materiais de consumo.")

    merged: dict[int, int] = {}
    for consumable, quantity in lines:
        if quantity == 0 or (op_type != T.ADJUSTMENT and quantity < 0):
            raise ValidationError(f"Quantidade inválida para {consumable}.")
        merged[consumable.pk] = merged.get(consumable.pk, 0) + quantity
    if not merged:
        raise ValidationError("Informe pelo menos um material.")
    if any(quantity == 0 for quantity in merged.values()):
        raise ValidationError("As linhas de um mesmo material se anulam; revise as quantidades.")
    if op_type == T.EXIT:
        _validate_common(EquipmentRule(frozenset(), "", None, needs_destination=True, needs_recipient=True), data)
    if op_type == T.RETURN and data.origin_sector is None:
        raise ValidationError("Informe o setor que está devolvendo o material.")

    balances = {
        b.consumable_id: b
        for b in StockBalance.objects.select_for_update()
        .filter(consumable_id__in=merged)
        .select_related("consumable")
        .order_by("consumable_id")
    }
    if len(balances) != len(merged):
        raise ValidationError("Algum material selecionado não existe mais.")

    sign = CONSUMABLE_SIGN.get(op_type, 1)
    errors = []
    for consumable_id, quantity in merged.items():
        balance = balances[consumable_id]
        if not balance.consumable.active and op_type == T.EXIT:
            errors.append(f"{balance.consumable} está desativado.")
        if balance.quantity + sign * quantity < 0:
            errors.append(
                f"Estoque insuficiente de {balance.consumable}: disponível {balance.quantity}, "
                f"solicitado {abs(quantity)}."
            )
    if errors:
        raise ValidationError(errors)

    operation = _create_operation(actor, op_type, data)
    for consumable_id in sorted(merged):
        balance = balances[consumable_id]
        delta = sign * merged[consumable_id]
        balance.quantity += delta
        balance.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            operation=operation, consumable_id=consumable_id, quantity=delta, balance_after=balance.quantity
        )
    _audit_operation(actor, operation)
    events.publish(events.CONSUMABLES_CHANGED, consumable_ids=sorted(merged))
    return operation


# --- Estorno ---------------------------------------------------------------------------


@transaction.atomic
def reverse_operation(*, actor, operation: StockOperation, justification: str) -> StockOperation:
    """Desfaz uma operação criando outra, inversa, vinculada à original. Nada é apagado."""
    ensure_capability(actor, Capability.OPERATION_REVERSE)
    if not justification.strip():
        raise ValidationError("Informe a justificativa do estorno.")
    operation = StockOperation.objects.select_for_update().get(pk=operation.pk)
    if operation.type == T.REVERSAL:
        raise ValidationError("Um estorno não pode ser estornado. Registre uma nova operação.")
    if StockOperation.objects.filter(reverses=operation).exists():
        raise ValidationError("Esta operação já foi estornada.")

    movements = list(operation.movements.select_related("equipment", "consumable").order_by("id"))
    equipment_movements = [m for m in movements if m.equipment_id]
    consumable_movements = [m for m in movements if m.consumable_id]

    if operation.type == T.ENTRY and equipment_movements:
        raise ValidationError(
            "A entrada de um equipamento não pode ser estornada. Corrija os dados no cadastro ou registre a baixa."
        )

    locked_equipment = {
        e.pk: e
        for e in Equipment.objects.select_for_update()
        .filter(pk__in=[m.equipment_id for m in equipment_movements])
        .order_by("pk")
    }
    for movement in equipment_movements:
        latest = StockMovement.objects.filter(equipment_id=movement.equipment_id).order_by("-id").first()
        if latest.pk != movement.pk:
            raise ValidationError(
                f"{movement.equipment} teve movimentações posteriores. Estorne primeiro as operações mais recentes."
            )

    balances = {
        b.consumable_id: b
        for b in StockBalance.objects.select_for_update()
        .filter(consumable_id__in=[m.consumable_id for m in consumable_movements])
        .order_by("consumable_id")
    }
    for movement in consumable_movements:
        balance = balances[movement.consumable_id]
        if balance.quantity - movement.quantity < 0:
            raise ValidationError(
                f"Estorno deixaria o estoque de {movement.consumable} negativo (saldo atual {balance.quantity})."
            )

    reversal = _create_operation(
        actor,
        T.REVERSAL,
        OperationData(
            origin_sector=operation.destination_sector,
            destination_sector=operation.origin_sector,
            justification=justification,
            notes=f"Estorno de {operation.number}",
        ),
        reverses=operation,
    )
    for movement in consumable_movements:
        balance = balances[movement.consumable_id]
        balance.quantity -= movement.quantity
        balance.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            operation=reversal,
            consumable_id=movement.consumable_id,
            quantity=-movement.quantity,
            balance_after=balance.quantity,
        )

    for movement in equipment_movements:
        equipment = locked_equipment[movement.equipment_id]
        StockMovement.objects.create(
            operation=reversal,
            equipment=equipment,
            quantity=1,
            status_before=equipment.status,
            status_after=movement.status_before,
            sector_before=equipment.current_sector,
            location_before=equipment.current_location,
            recipient_before=equipment.current_recipient,
        )
        _close_open_assignment(equipment, reversal)
        previous = EquipmentAssignment.objects.filter(equipment=equipment, closed_by=operation).first()
        if previous is not None:
            _open_assignment(
                equipment,
                previous.kind,
                reversal,
                sector=previous.sector,
                location=previous.location,
                recipient=previous.recipient,
                third_party=previous.third_party,
                due_date=previous.due_date,
            )
        equipment.status = movement.status_before
        equipment.current_sector = movement.sector_before
        equipment.current_location = movement.location_before
        equipment.current_recipient = movement.recipient_before
        equipment.save(
            update_fields=["status", "current_sector", "current_location", "current_recipient", "updated_at"]
        )

    _audit_operation(actor, reversal, action=AuditAction.REVERSAL)
    if consumable_movements:
        events.publish(
            events.CONSUMABLES_CHANGED, consumable_ids=sorted({m.consumable_id for m in consumable_movements})
        )
    events.publish(events.OPERATION_REVERSED, operation=operation, reversal=reversal, actor=actor)
    return reversal
