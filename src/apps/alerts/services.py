"""Avaliação dos alertas de estoque mínimo.

Chamada automaticamente (evento CONSUMABLES_CHANGED) após cada movimentação de
consumível, estorno ou mudança de estoque mínimo, na mesma transação.

Regras:
- Só há alerta para materiais ativos com estoque mínimo configurado (> 0).
- Saldo <= mínimo abre um alerta (nível "baixo"; "zerado" se o saldo for 0).
- Enquanto a condição dura, o mesmo alerta é atualizado: nunca há duplicata.
- Saldo acima do mínimo, mínimo zerado ou material desativado fecham o alerta.
"""

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Consumable

from .models import AlertLevel, LowStockAlert


def _level(balance: int) -> str:
    return AlertLevel.EMPTY if balance <= 0 else AlertLevel.LOW


@transaction.atomic
def evaluate_consumables(consumable_ids: list[int] | None = None) -> None:
    consumables = Consumable.objects.select_related("balance").order_by("pk")
    if consumable_ids is not None:
        consumables = consumables.filter(pk__in=consumable_ids)
    open_alerts = {
        a.consumable_id: a
        for a in LowStockAlert.objects.select_for_update().filter(closed_at__isnull=True, consumable__in=consumables)
    }
    now = timezone.now()
    for consumable in consumables:
        balance = consumable.balance.quantity if hasattr(consumable, "balance") else 0
        alert = open_alerts.get(consumable.pk)
        critical = consumable.active and consumable.min_stock > 0 and balance <= consumable.min_stock
        if critical and alert is None:
            LowStockAlert.objects.create(
                consumable=consumable,
                balance_at_open=balance,
                min_stock_at_open=consumable.min_stock,
                level=_level(balance),
                current_balance=balance,
            )
        elif critical and (alert.current_balance != balance or alert.level != _level(balance)):
            alert.current_balance = balance
            alert.level = _level(balance)
            alert.save(update_fields=["current_balance", "level", "updated_at"])
        elif not critical and alert is not None:
            if not consumable.active:
                reason = "Material desativado"
            elif consumable.min_stock == 0:
                reason = "Estoque mínimo removido"
            else:
                reason = f"Saldo normalizado ({balance})"
            alert.current_balance = balance
            alert.closed_at = now
            alert.closed_reason = reason
            alert.save(update_fields=["current_balance", "closed_at", "closed_reason", "updated_at"])


def open_alert_count() -> int:
    return LowStockAlert.objects.filter(closed_at__isnull=True).count()
