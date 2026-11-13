from django.db import models
from django.db.models import Q


class AlertLevel(models.TextChoices):
    LOW = "baixo", "No mínimo ou abaixo"
    EMPTY = "zerado", "Sem estoque"


class LowStockAlert(models.Model):
    """Período em que um material ficou no estoque mínimo ou abaixo.

    Há no máximo um alerta aberto por material (índice único parcial): a condição
    é registrada quando surge, atualizada enquanto dura e fechada quando o saldo
    volta acima do mínimo. Alertas fechados formam o histórico.
    """

    consumable = models.ForeignKey(
        "catalog.Consumable", verbose_name="material", on_delete=models.PROTECT, related_name="alerts"
    )
    opened_at = models.DateTimeField("identificado em", auto_now_add=True, db_index=True)
    balance_at_open = models.IntegerField("saldo ao identificar")
    min_stock_at_open = models.PositiveIntegerField("mínimo ao identificar")
    level = models.CharField("nível", max_length=8, choices=AlertLevel.choices)
    current_balance = models.IntegerField("saldo atual")
    updated_at = models.DateTimeField("atualizado em", auto_now=True)
    closed_at = models.DateTimeField("normalizado em", null=True, blank=True, db_index=True)
    closed_reason = models.CharField("motivo do encerramento", max_length=120, blank=True)

    class Meta:
        ordering = ["-opened_at", "-id"]
        verbose_name = "alerta de estoque baixo"
        verbose_name_plural = "alertas de estoque baixo"
        constraints = [
            models.UniqueConstraint(
                "consumable", name="alert_one_open_per_consumable", condition=Q(closed_at__isnull=True)
            ),
        ]

    def __str__(self) -> str:
        return f"{self.consumable}: {self.get_level_display()} desde {self.opened_at:%d/%m/%Y}"

    @property
    def is_open(self) -> bool:
        return self.closed_at is None
