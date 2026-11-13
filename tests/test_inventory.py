import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import EquipmentStatus as S
from apps.inventory import services as inventory
from apps.inventory.models import (
    AssignmentKind,
    EquipmentAssignment,
    StockBalance,
    StockMovement,
    StockOperation,
)
from apps.inventory.models import (
    OperationType as T,
)
from apps.inventory.services import OperationData

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def urbanismo():
    return f.sector("Secretaria Municipal de Urbanismo", "SMU")


@pytest.fixture
def saude():
    return f.sector("Secretaria Municipal de Saúde", "SMS")


# --- Cadastro / entrada ----------------------------------------------------------------


def test_register_creates_entry_operation(tech_user):
    item = f.equipment(tech_user)
    assert item.status == S.AVAILABLE and item.location_label == "Estoque da TI"
    movement = item.movements.get()
    assert movement.operation.type == T.ENTRY
    assert movement.operation.number.startswith("OP-")
    assert movement.operation.performed_by == tech_user


def test_register_already_in_use_for_initial_inventory(tech_user, urbanismo):
    maria = f.recipient(urbanismo)
    item = inventory.register_equipment(
        actor=tech_user,
        data=f.equipment_data(serial_number="X1"),
        in_use=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    assert item.status == S.IN_USE and item.current_sector == urbanismo and item.current_recipient == maria
    assert item.assignments.get(ended_at__isnull=True).kind == AssignmentKind.USE


def test_operation_numbers_are_sequential(tech_user):
    numbers = [f.equipment(tech_user).movements.get().operation.number for _ in range(3)]
    sequence = [int(n.rsplit("-", 1)[1]) for n in numbers]
    assert sequence == [sequence[0], sequence[0] + 1, sequence[0] + 2]


def test_viewer_cannot_register(viewer_user):
    with pytest.raises(PermissionDenied):
        f.equipment(viewer_user)


# --- Movimentação de equipamentos ------------------------------------------------------


def test_exit_transfer_return_keep_full_history(tech_user, urbanismo, saude):
    item = f.equipment(tech_user)
    maria, joao = f.recipient(urbanismo, "Maria"), f.recipient(saude, "João")

    exit_op = inventory.move_equipment(
        actor=tech_user,
        op_type=T.EXIT,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    item.refresh_from_db()
    assert (item.status, item.current_sector, item.current_recipient) == (S.IN_USE, urbanismo, maria)

    transfer = inventory.move_equipment(
        actor=tech_user,
        op_type=T.TRANSFER,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=saude, recipient=joao),
    )
    assert transfer.origin_sector == urbanismo
    item.refresh_from_db()
    assert (item.current_sector, item.current_recipient) == (saude, joao)

    inventory.move_equipment(actor=tech_user, op_type=T.RETURN, equipment_ids=[item.pk], data=OperationData())
    item.refresh_from_db()
    assert item.status == S.AVAILABLE and item.current_sector is None

    history = list(item.assignments.order_by("started_at", "id").values_list("sector__acronym", "recipient__full_name"))
    assert history == [("SMU", "Maria"), ("SMS", "João")]
    assert not item.assignments.filter(ended_at__isnull=True).exists()
    assert exit_op.movements.get().status_before == S.AVAILABLE


def test_invalid_transitions_are_blocked(tech_user, urbanismo):
    item = f.equipment(tech_user)
    with pytest.raises(ValidationError, match="não pode receber"):
        inventory.move_equipment(
            actor=tech_user,
            op_type=T.TRANSFER,
            equipment_ids=[item.pk],
            data=OperationData(destination_sector=urbanismo, recipient=f.recipient(urbanismo)),
        )
    with pytest.raises(ValidationError, match="não pode receber"):
        inventory.move_equipment(actor=tech_user, op_type=T.LOAN_RETURN, equipment_ids=[item.pk], data=OperationData())
    assert StockOperation.objects.count() == 1  # só a entrada


def test_exit_requires_destination_and_recipient(tech_user):
    item = f.equipment(tech_user)
    with pytest.raises(ValidationError) as error:
        inventory.move_equipment(actor=tech_user, op_type=T.EXIT, equipment_ids=[item.pk], data=OperationData())
    assert "Informe o setor de destino." in error.value.messages
    assert "Informe o servidor que recebe." in error.value.messages


def test_one_operation_many_equipment_is_all_or_nothing(tech_user, urbanismo):
    maria = f.recipient(urbanismo)
    ok, busy = f.equipment(tech_user), f.equipment(tech_user)
    inventory.move_equipment(
        actor=tech_user,
        op_type=T.EXIT,
        equipment_ids=[busy.pk],
        data=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    with pytest.raises(ValidationError):
        inventory.move_equipment(
            actor=tech_user,
            op_type=T.EXIT,
            equipment_ids=[ok.pk, busy.pk],
            data=OperationData(destination_sector=urbanismo, recipient=maria),
        )
    ok.refresh_from_db()
    assert ok.status == S.AVAILABLE


def test_loan_and_maintenance_cycle(tech_user, urbanismo):
    item = f.equipment(tech_user)
    maria = f.recipient(urbanismo)
    inventory.move_equipment(
        actor=tech_user,
        op_type=T.LOAN,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=urbanismo, recipient=maria, due_date=inventory_date(7)),
    )
    item.refresh_from_db()
    assert item.status == S.ON_LOAN
    assert item.assignments.get(ended_at__isnull=True).due_date == inventory_date(7)
    inventory.move_equipment(actor=tech_user, op_type=T.LOAN_RETURN, equipment_ids=[item.pk], data=OperationData())
    with pytest.raises(ValidationError, match="assistência"):
        inventory.move_equipment(
            actor=tech_user, op_type=T.MAINTENANCE_OUT, equipment_ids=[item.pk], data=OperationData()
        )
    inventory.move_equipment(
        actor=tech_user,
        op_type=T.MAINTENANCE_OUT,
        equipment_ids=[item.pk],
        data=OperationData(third_party="Assistência Dell"),
    )
    item.refresh_from_db()
    assert item.status == S.MAINTENANCE


def test_write_off_is_admin_only_and_final(tech_user, admin_user):
    item = f.equipment(tech_user)
    with pytest.raises(PermissionDenied):
        inventory.move_equipment(
            actor=tech_user, op_type=T.WRITE_OFF, equipment_ids=[item.pk], data=OperationData(justification="queimou")
        )
    inventory.move_equipment(
        actor=admin_user,
        op_type=T.WRITE_OFF,
        equipment_ids=[item.pk],
        data=OperationData(justification="Placa-mãe queimada, laudo 12/2026"),
    )
    item.refresh_from_db()
    assert item.status == S.WRITTEN_OFF
    for op in [T.EXIT, T.WRITE_OFF, T.MAINTENANCE_OUT]:
        with pytest.raises(ValidationError):
            inventory.move_equipment(
                actor=admin_user,
                op_type=op,
                equipment_ids=[item.pk],
                data=OperationData(justification="x", third_party="x"),
            )


# --- Consumíveis -----------------------------------------------------------------------


def test_consumable_entry_and_exit_update_balance(tech_user, urbanismo):
    toner = f.consumable(tech_user, initial=20)
    maria = f.recipient(urbanismo)
    op = inventory.move_consumables(
        actor=tech_user,
        op_type=T.EXIT,
        lines=[(toner, 2)],
        data=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    assert StockBalance.objects.get(consumable=toner).quantity == 18
    movement = op.movements.get()
    assert (movement.quantity, movement.balance_after) == (-2, 18)
    assert (op.performed_by, op.destination_sector, op.recipient) == (tech_user, urbanismo, maria)


def test_negative_stock_is_impossible(tech_user, urbanismo):
    toner = f.consumable(tech_user, initial=1)
    maria = f.recipient(urbanismo)
    with pytest.raises(ValidationError, match="Estoque insuficiente"):
        inventory.move_consumables(
            actor=tech_user,
            op_type=T.EXIT,
            lines=[(toner, 2)],
            data=OperationData(destination_sector=urbanismo, recipient=maria),
        )
    assert StockBalance.objects.get(consumable=toner).quantity == 1


def test_database_rejects_negative_balance_even_bypassing_services(tech_user):
    toner = f.consumable(tech_user)
    with pytest.raises(IntegrityError), transaction.atomic():
        StockBalance.objects.filter(consumable=toner).update(quantity=-1)


def test_same_item_twice_in_one_exit_is_summed(tech_user, urbanismo):
    toner = f.consumable(tech_user, initial=3)
    with pytest.raises(ValidationError, match="Estoque insuficiente"):
        inventory.move_consumables(
            actor=tech_user,
            op_type=T.EXIT,
            lines=[(toner, 2), (toner, 2)],
            data=OperationData(destination_sector=urbanismo, recipient=f.recipient(urbanismo)),
        )


def test_adjustment_requires_admin_and_justification(tech_user, admin_user):
    toner = f.consumable(admin_user, initial=5)
    with pytest.raises(PermissionDenied):
        inventory.move_consumables(
            actor=tech_user, op_type=T.ADJUSTMENT, lines=[(toner, -1)], data=OperationData(justification="inventário")
        )
    with pytest.raises(ValidationError, match="justificativa"):
        inventory.move_consumables(actor=admin_user, op_type=T.ADJUSTMENT, lines=[(toner, -1)], data=OperationData())
    inventory.move_consumables(
        actor=admin_user,
        op_type=T.ADJUSTMENT,
        lines=[(toner, -2)],
        data=OperationData(justification="Inventário físico de 12/11/2026"),
    )
    assert StockBalance.objects.get(consumable=toner).quantity == 3


# --- Imutabilidade e estorno -----------------------------------------------------------


def test_history_cannot_be_edited_or_deleted(tech_user):
    item = f.equipment(tech_user)
    op = item.movements.get().operation
    for queryset in (StockOperation.objects.filter(pk=op.pk), StockMovement.objects.filter(operation=op)):
        with pytest.raises(IntegrityError), transaction.atomic():
            queryset.update(notes="x") if queryset.model is StockOperation else queryset.update(quantity=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            queryset.delete()


def test_reverse_consumable_exit_restores_balance(tech_user, admin_user, urbanismo):
    toner = f.consumable(tech_user, initial=10)
    op = inventory.move_consumables(
        actor=tech_user,
        op_type=T.EXIT,
        lines=[(toner, 4)],
        data=OperationData(destination_sector=urbanismo, recipient=f.recipient(urbanismo)),
    )
    with pytest.raises(PermissionDenied):
        inventory.reverse_operation(actor=tech_user, operation=op, justification="erro")
    reversal = inventory.reverse_operation(actor=admin_user, operation=op, justification="Quantidade digitada errada")
    assert StockBalance.objects.get(consumable=toner).quantity == 10
    assert reversal.reverses == op
    op.refresh_from_db()
    assert op.is_reversed
    with pytest.raises(ValidationError, match="já foi estornada"):
        inventory.reverse_operation(actor=admin_user, operation=op, justification="de novo")
    with pytest.raises(ValidationError, match="não pode ser estornado"):
        inventory.reverse_operation(actor=admin_user, operation=reversal, justification="x")


def test_reverse_transfer_restores_previous_holder(tech_user, admin_user, urbanismo, saude):
    item = f.equipment(tech_user)
    maria, joao = f.recipient(urbanismo, "Maria"), f.recipient(saude, "João")
    inventory.move_equipment(
        actor=tech_user,
        op_type=T.EXIT,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    transfer = inventory.move_equipment(
        actor=tech_user,
        op_type=T.TRANSFER,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=saude, recipient=joao),
    )
    inventory.reverse_operation(actor=admin_user, operation=transfer, justification="Transferido por engano")
    item.refresh_from_db()
    assert (item.status, item.current_sector, item.current_recipient) == (S.IN_USE, urbanismo, maria)
    open_assignment = EquipmentAssignment.objects.get(equipment=item, ended_at__isnull=True)
    assert open_assignment.recipient == maria


def test_only_latest_operation_of_equipment_can_be_reversed(tech_user, admin_user, urbanismo):
    item = f.equipment(tech_user)
    maria = f.recipient(urbanismo)
    exit_op = inventory.move_equipment(
        actor=tech_user,
        op_type=T.EXIT,
        equipment_ids=[item.pk],
        data=OperationData(destination_sector=urbanismo, recipient=maria),
    )
    inventory.move_equipment(actor=tech_user, op_type=T.RETURN, equipment_ids=[item.pk], data=OperationData())
    with pytest.raises(ValidationError, match="posteriores"):
        inventory.reverse_operation(actor=admin_user, operation=exit_op, justification="x")


def test_equipment_entry_cannot_be_reversed(tech_user, admin_user):
    op = f.equipment(tech_user).movements.get().operation
    with pytest.raises(ValidationError, match="não pode ser estornada"):
        inventory.reverse_operation(actor=admin_user, operation=op, justification="x")


def test_reversal_cannot_make_balance_negative(tech_user, admin_user, urbanismo):
    toner = f.consumable(tech_user)
    entry = inventory.move_consumables(actor=tech_user, op_type=T.ENTRY, lines=[(toner, 5)], data=OperationData())
    inventory.move_consumables(
        actor=tech_user,
        op_type=T.EXIT,
        lines=[(toner, 4)],
        data=OperationData(destination_sector=urbanismo, recipient=f.recipient(urbanismo)),
    )
    with pytest.raises(ValidationError, match="negativo"):
        inventory.reverse_operation(actor=admin_user, operation=entry, justification="nota fiscal errada")


def inventory_date(days: int):
    from datetime import timedelta

    from django.utils import timezone

    return timezone.localdate() + timedelta(days=days)
