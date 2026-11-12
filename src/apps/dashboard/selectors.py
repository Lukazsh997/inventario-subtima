"""Consultas do dashboard. Cada função devolve dados prontos para a tela (sem lógica no template)."""

from dataclasses import dataclass
from datetime import date

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.alerts.models import LowStockAlert
from apps.catalog.models import Category, Consumable, Equipment, EquipmentStatus, ItemKind
from apps.inventory.models import (
    AssignmentKind,
    EquipmentAssignment,
    OperationType,
    StockBalance,
    StockMovement,
    StockOperation,
)
from apps.organization.models import Sector

S = EquipmentStatus
T = OperationType
MONTH_NAMES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


@dataclass
class DashboardFilters:
    start: date
    end: date
    category: Category | None = None
    sector: Sector | None = None

    @property
    def equipment_category(self):
        return self.category if self.category and self.category.kind == ItemKind.EQUIPMENT else None

    @property
    def consumable_category(self):
        return self.category if self.category and self.category.kind == ItemKind.CONSUMABLE else None


def default_period(today: date | None = None) -> tuple[date, date]:
    """Últimos 12 meses, do primeiro dia do mês inicial até hoje."""
    today = today or timezone.localdate()
    month = today.month - 11
    year = today.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, 1), today


def months_between(start: date, end: date) -> list[date]:
    months, current = [], date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return months


def month_label(value: date) -> str:
    return f"{MONTH_NAMES[value.month - 1]}/{value.year % 100:02d}"


def _equipment(f: DashboardFilters):
    queryset = Equipment.objects.exclude(status=S.WRITTEN_OFF)
    if f.equipment_category:
        queryset = queryset.filter(category=f.equipment_category)
    if f.sector:
        queryset = queryset.filter(current_sector=f.sector)
    return queryset


def _consumables(f: DashboardFilters):
    queryset = Consumable.objects.filter(active=True)
    if f.consumable_category:
        queryset = queryset.filter(category=f.consumable_category)
    return queryset


def _movements_in_period(f: DashboardFilters):
    queryset = StockMovement.objects.filter(
        operation__performed_at__date__gte=f.start, operation__performed_at__date__lte=f.end
    )
    if f.category:
        field = "equipment__category" if f.category.kind == ItemKind.EQUIPMENT else "consumable__category"
        queryset = queryset.filter(**{field: f.category})
    if f.sector:
        queryset = queryset.filter(Q(operation__destination_sector=f.sector) | Q(operation__origin_sector=f.sector))
    return queryset


def indicators(f: DashboardFilters) -> dict:
    by_status = dict(_equipment(f).values_list("status").annotate(n=Count("id")).order_by())
    consumables = _consumables(f)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    operations_month = StockOperation.objects.filter(performed_at__date__gte=month_start)
    if f.sector:
        operations_month = operations_month.filter(Q(destination_sector=f.sector) | Q(origin_sector=f.sector))
    overdue = EquipmentAssignment.objects.filter(kind=AssignmentKind.LOAN, ended_at__isnull=True, due_date__lt=today)
    return {
        "equipment_total": sum(by_status.values()),
        "available": by_status.get(S.AVAILABLE, 0),
        "in_use": by_status.get(S.IN_USE, 0),
        "on_loan": by_status.get(S.ON_LOAN, 0),
        "maintenance": by_status.get(S.MAINTENANCE, 0),
        "overdue_loans": overdue.count(),
        "stock_units": StockBalance.objects.filter(consumable__in=consumables).aggregate(t=Sum("quantity"))["t"] or 0,
        "stock_items": consumables.filter(balance__quantity__gt=0).count(),
        "operations_month": operations_month.count(),
        "low_stock": LowStockAlert.objects.filter(closed_at__isnull=True, consumable__in=consumables).count(),
        "empty_stock": consumables.filter(balance__quantity=0).count(),
    }


def entries_and_exits(f: DashboardFilters, months: list[date]) -> dict:
    """Quantidade de operações de entrada e de saída por mês (equipamentos e materiais)."""
    rows = (
        _movements_in_period(f)
        .filter(operation__type__in=[T.ENTRY, T.EXIT])
        .annotate(month=TruncMonth("operation__performed_at"))
        .values("month", "operation__type")
        .annotate(n=Count("operation", distinct=True))
    )
    data = {(r["month"].date().replace(day=1), r["operation__type"]): r["n"] for r in rows}
    return {
        "labels": [month_label(m) for m in months],
        "entries": [data.get((m, T.ENTRY), 0) for m in months],
        "exits": [data.get((m, T.EXIT), 0) for m in months],
    }


def monthly_consumption(f: DashboardFilters, months: list[date]) -> dict:
    """Unidades de material consumidas por mês (saídas menos devoluções)."""
    rows = (
        _movements_in_period(f)
        .filter(consumable__isnull=False, operation__type__in=[T.EXIT, T.RETURN])
        .annotate(month=TruncMonth("operation__performed_at"))
        .values("month")
        .annotate(total=Sum("quantity"))
    )
    data = {r["month"].date().replace(day=1): max(0, -r["total"]) for r in rows}
    return {"labels": [month_label(m) for m in months], "values": [data.get(m, 0) for m in months]}


def top_withdrawn(f: DashboardFilters, limit: int = 10) -> dict:
    rows = (
        _movements_in_period(f)
        .filter(consumable__isnull=False, operation__type=T.EXIT)
        .values("consumable__name")
        .annotate(total=Sum(-F("quantity")))
        .order_by("-total")[:limit]
    )
    return {"labels": [r["consumable__name"] for r in rows], "values": [r["total"] for r in rows]}


def equipment_by_sector(f: DashboardFilters, limit: int = 12) -> dict:
    rows = list(
        _equipment(f)
        .filter(status__in=[S.IN_USE, S.ON_LOAN], current_sector__isnull=False)
        .values("current_sector__name", "current_sector__acronym")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    labels = [r["current_sector__acronym"] or r["current_sector__name"] for r in rows[:limit]]
    values = [r["n"] for r in rows[:limit]]
    if len(rows) > limit:
        labels.append("Outros")
        values.append(sum(r["n"] for r in rows[limit:]))
    return {"labels": labels, "values": values}


def equipment_by_category(f: DashboardFilters) -> dict:
    rows = _equipment(f).values("category__name").annotate(n=Count("id")).order_by("-n")
    return {"labels": [r["category__name"] for r in rows], "values": [r["n"] for r in rows]}


def stock_evolution(f: DashboardFilters, months: list[date]) -> dict:
    """Total de unidades de material em estoque ao fim de cada mês, reconstruído a partir das movimentações."""
    consumables = _consumables(f)
    current = StockBalance.objects.filter(consumable__in=consumables).aggregate(t=Sum("quantity"))["t"] or 0
    deltas = dict(
        StockMovement.objects.filter(consumable__in=consumables)
        .annotate(month=TruncMonth("operation__performed_at"))
        .values("month")
        .annotate(total=Sum("quantity"))
        .values_list("month", "total")
    )
    deltas = {k.date().replace(day=1): v for k, v in deltas.items()}
    values = []
    for month in months:
        # saldo ao fim do mês = saldo atual − tudo o que entrou/saiu depois daquele mês
        after = sum(v for k, v in deltas.items() if k > month)
        values.append(current - after)
    return {"labels": [month_label(m) for m in months], "values": values}


def recent_activity(f: DashboardFilters, limit: int = 10):
    queryset = StockMovement.objects.select_related(
        "operation",
        "operation__performed_by",
        "operation__destination_sector",
        "operation__origin_sector",
        "operation__recipient",
        "equipment",
        "consumable",
    ).order_by("-operation__performed_at", "-id")
    if f.sector:
        queryset = queryset.filter(Q(operation__destination_sector=f.sector) | Q(operation__origin_sector=f.sector))
    if f.category:
        field = "equipment__category" if f.category.kind == ItemKind.EQUIPMENT else "consumable__category"
        queryset = queryset.filter(**{field: f.category})
    return queryset[:limit]
