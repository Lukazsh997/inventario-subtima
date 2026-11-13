"""Abre os alertas para materiais que já estão no mínimo quando esta versão é instalada."""

from django.db import migrations


def backfill(apps, schema_editor):
    Consumable = apps.get_model("catalog", "Consumable")
    StockBalance = apps.get_model("inventory", "StockBalance")
    LowStockAlert = apps.get_model("alerts", "LowStockAlert")
    balances = dict(StockBalance.objects.values_list("consumable_id", "quantity"))
    for consumable in Consumable.objects.filter(active=True, min_stock__gt=0):
        balance = balances.get(consumable.pk, 0)
        if balance <= consumable.min_stock and not LowStockAlert.objects.filter(
            consumable=consumable, closed_at__isnull=True
        ).exists():
            LowStockAlert.objects.create(
                consumable=consumable, balance_at_open=balance, min_stock_at_open=consumable.min_stock,
                level="zerado" if balance <= 0 else "baixo", current_balance=balance,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0001_initial"),
        ("inventory", "0002_immutable_history"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
