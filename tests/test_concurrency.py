"""Duas retiradas simultâneas não podem deixar o estoque negativo nem entregar o mesmo equipamento duas vezes.

Usa conexões reais e paralelas ao PostgreSQL (transaction=True), não simulação.
"""

import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import connection

from apps.catalog.models import EquipmentStatus
from apps.inventory import services as inventory
from apps.inventory.models import OperationType as T
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import OperationData

from . import factories as f

pytestmark = pytest.mark.django_db(transaction=True)


def _run_in_parallel(target, count: int) -> list:
    barrier = threading.Barrier(count)
    results: list = []

    def worker():
        try:
            barrier.wait()
            results.append(target())
        except ValidationError as exc:
            results.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_parallel_withdrawals_never_go_negative(tech_user):
    sector = f.sector()
    maria = f.recipient(sector)
    toner = f.consumable(tech_user, initial=5)

    def withdraw():
        return inventory.move_consumables(
            actor=tech_user,
            op_type=T.EXIT,
            lines=[(toner, 1)],
            data=OperationData(destination_sector=sector, recipient=maria),
        )

    results = _run_in_parallel(withdraw, 8)
    successes = [r for r in results if not isinstance(r, ValidationError)]
    failures = [r for r in results if isinstance(r, ValidationError)]
    assert len(successes) == 5 and len(failures) == 3
    assert StockBalance.objects.get(consumable=toner).quantity == 0
    assert sorted(
        StockMovement.objects.filter(consumable=toner, quantity__lt=0).values_list("balance_after", flat=True)
    ) == [0, 1, 2, 3, 4]


def test_same_equipment_cannot_be_delivered_twice(tech_user):
    sector = f.sector()
    maria = f.recipient(sector)
    item = f.equipment(tech_user)

    def deliver():
        return inventory.move_equipment(
            actor=tech_user,
            op_type=T.EXIT,
            equipment_ids=[item.pk],
            data=OperationData(destination_sector=sector, recipient=maria),
        )

    results = _run_in_parallel(deliver, 4)
    assert sum(not isinstance(r, ValidationError) for r in results) == 1
    item.refresh_from_db()
    assert item.status == EquipmentStatus.IN_USE
    assert item.assignments.filter(ended_at__isnull=True).count() == 1
