"""Operações, movimentações, saldos e atribuições.

StockOperation, StockMovement e OperationAccessory são imutáveis: o banco
rejeita UPDATE e DELETE (migração 0002). Correções são feitas por estorno,
uma nova operação que aponta para a original.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import EquipmentStatus


class OperationType(models.TextChoices):
    ENTRY = "entrada", "Entrada"
    EXIT = "saida", "Saída (entrega)"
    TRANSFER = "transferencia", "Transferência entre setores"
    RETURN = "devolucao", "Devolução"
    LOAN = "emprestimo", "Empréstimo temporário"
    LOAN_RETURN = "retorno_emprestimo", "Retorno de empréstimo"
    MAINTENANCE_OUT = "envio_manutencao", "Envio para manutenção"
    MAINTENANCE_RETURN = "retorno_manutencao", "Retorno de manutenção"
    ADJUSTMENT = "ajuste", "Ajuste de estoque"
    WRITE_OFF = "baixa", "Baixa de equipamento"
    REVERSAL = "estorno", "Estorno"


EQUIPMENT_OPERATIONS = [
    OperationType.EXIT,
    OperationType.TRANSFER,
    OperationType.RETURN,
    OperationType.LOAN,
    OperationType.LOAN_RETURN,
    OperationType.MAINTENANCE_OUT,
    OperationType.MAINTENANCE_RETURN,
    OperationType.WRITE_OFF,
]
CONSUMABLE_OPERATIONS = [OperationType.ENTRY, OperationType.EXIT, OperationType.RETURN, OperationType.ADJUSTMENT]


class StockOperation(models.Model):
    """Um ato do técnico: um destinatário, uma justificativa, um termo (Fase 5), uma ou várias linhas."""

    number = models.CharField("número", max_length=20, unique=True)
    type = models.CharField("tipo", max_length=20, choices=OperationType.choices, db_index=True)
    performed_at = models.DateTimeField("data/hora", auto_now_add=True, db_index=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsável pela operação",
        on_delete=models.PROTECT,
        related_name="operations",
    )
    origin_sector = models.ForeignKey(
        "organization.Sector",
        verbose_name="setor de origem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    destination_sector = models.ForeignKey(
        "organization.Sector",
        verbose_name="setor de destino",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    destination_location = models.ForeignKey(
        "organization.Location",
        verbose_name="local de destino",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    recipient = models.ForeignKey(
        "organization.Recipient",
        verbose_name="servidor recebedor",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operations",
    )
    due_date = models.DateField("devolução prevista", null=True, blank=True)
    third_party = models.CharField("assistência/fornecedor", max_length=150, blank=True)
    justification = models.TextField("justificativa", blank=True)
    notes = models.TextField("observações", blank=True)
    reverses = models.OneToOneField(
        "self", verbose_name="estorno de", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )

    class Meta:
        ordering = ["-performed_at", "-id"]
        verbose_name = "operação"
        verbose_name_plural = "operações"

    def __str__(self) -> str:
        return f"{self.number} · {self.get_type_display()}"

    @property
    def is_reversed(self) -> bool:
        return hasattr(self, "reversed_by")


class StockMovement(models.Model):
    """Uma linha da operação: um equipamento (sempre quantidade 1) ou um consumível (quantidade com sinal)."""

    operation = models.ForeignKey(StockOperation, on_delete=models.PROTECT, related_name="movements")
    equipment = models.ForeignKey(
        "catalog.Equipment", on_delete=models.PROTECT, null=True, blank=True, related_name="movements"
    )
    consumable = models.ForeignKey(
        "catalog.Consumable", on_delete=models.PROTECT, null=True, blank=True, related_name="movements"
    )
    quantity = models.IntegerField("quantidade", help_text="Positiva entra no estoque, negativa sai")
    balance_after = models.IntegerField("saldo após", null=True, blank=True)
    # Situação do equipamento antes e depois (permite estorno e histórico completo)
    status_before = models.CharField(max_length=12, choices=EquipmentStatus.choices, blank=True)
    status_after = models.CharField(max_length=12, choices=EquipmentStatus.choices, blank=True)
    sector_before = models.ForeignKey(
        "organization.Sector", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    location_before = models.ForeignKey(
        "organization.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    recipient_before = models.ForeignKey(
        "organization.Recipient", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(equipment__isnull=False, consumable__isnull=True)
                    | Q(equipment__isnull=True, consumable__isnull=False)
                ),
                name="movement_exactly_one_item",
            ),
            models.CheckConstraint(condition=~Q(quantity=0), name="movement_nonzero_quantity"),
            models.CheckConstraint(
                condition=Q(equipment__isnull=True) | Q(quantity=1),
                name="movement_equipment_unit_quantity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.operation.number}: {self.item} ({self.quantity:+d})"

    @property
    def item(self):
        return self.equipment or self.consumable


class OperationAccessory(models.Model):
    """Acessórios não patrimoniados entregues junto (carregador, bolsa, mouse simples)."""

    operation = models.ForeignKey(StockOperation, on_delete=models.PROTECT, related_name="accessories")
    description = models.CharField("descrição", max_length=150)
    quantity = models.PositiveIntegerField("quantidade", default=1)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.description}"


class StockBalance(models.Model):
    """Saldo atual de um consumível. Alterado apenas pelos serviços, sob bloqueio de linha."""

    consumable = models.OneToOneField("catalog.Consumable", on_delete=models.PROTECT, related_name="balance")
    quantity = models.IntegerField("quantidade", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0), name="stock_balance_non_negative")]

    def __str__(self) -> str:
        return f"{self.consumable}: {self.quantity}"


class AssignmentKind(models.TextChoices):
    USE = "uso", "Em uso"
    LOAN = "emprestimo", "Empréstimo"
    MAINTENANCE = "manutencao", "Manutenção"


class EquipmentAssignment(models.Model):
    """Período em que um equipamento esteve com um setor/servidor (histórico de localização e responsabilidade)."""

    equipment = models.ForeignKey("catalog.Equipment", on_delete=models.PROTECT, related_name="assignments")
    kind = models.CharField("tipo", max_length=12, choices=AssignmentKind.choices)
    sector = models.ForeignKey("organization.Sector", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    location = models.ForeignKey(
        "organization.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    recipient = models.ForeignKey(
        "organization.Recipient", on_delete=models.PROTECT, null=True, blank=True, related_name="assignments"
    )
    third_party = models.CharField(max_length=150, blank=True)
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    opened_by = models.ForeignKey(StockOperation, on_delete=models.PROTECT, related_name="opened_assignments")
    closed_by = models.ForeignKey(
        StockOperation, on_delete=models.PROTECT, null=True, blank=True, related_name="closed_assignments"
    )

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                "equipment", name="assignment_one_open_per_equipment", condition=Q(ended_at__isnull=True)
            ),
        ]

    def __str__(self) -> str:
        return f"{self.equipment} · {self.get_kind_display()} desde {self.started_at:%d/%m/%Y}"
