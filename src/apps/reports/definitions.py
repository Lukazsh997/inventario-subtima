"""Os relatórios do sistema. Para incluir um novo, crie a classe e registre em REPORTS."""

from collections import defaultdict

from django.db.models import Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.alerts.models import LowStockAlert
from apps.alerts.views import monthly_consumption
from apps.catalog.models import Consumable, Equipment, EquipmentStatus
from apps.catalog.services import find_equipment_by_code
from apps.dashboard.selectors import month_label, months_between
from apps.inventory.models import AssignmentKind, EquipmentAssignment, OperationType, StockMovement

from .base import EQUIPMENT_SITUATIONS, Column, Report, ReportResult, fmt_date

S = EquipmentStatus
T = OperationType


def identification(equipment: Equipment) -> str:
    parts = []
    if equipment.asset_tag:
        parts.append(f"Patr. {equipment.asset_tag}")
    if equipment.lessor_code:
        parts.append(equipment.lessor_code)
    if equipment.serial_number:
        parts.append(f"S/N {equipment.serial_number}")
    return " · ".join(parts)


def item_label(movement: StockMovement) -> tuple[str, str]:
    if movement.equipment_id:
        return movement.equipment.name, identification(movement.equipment)
    return movement.consumable.name, movement.consumable.reference or ""


def sector_label(sector) -> str:
    return (sector.acronym or sector.name) if sector else ""


class CurrentStock(Report):
    slug = "estoque-atual"
    title = "Estoque atual de materiais"
    description = "Saldo de cada material de consumo ativo, com estoque mínimo e situação."
    filters = ("categoria_mat", "situacao")
    situation_choices = [("critico", "No mínimo ou abaixo"), ("zerado", "Sem estoque"), ("normal", "Acima do mínimo")]
    landscape = False

    def run(self, params):
        queryset = Consumable.objects.filter(active=True).select_related("category", "balance").order_by("name")
        if params.get("categoria"):
            queryset = queryset.filter(category=params["categoria"])
        wanted = params.get("situacao")
        rows = []
        for c in queryset:
            balance = c.balance.quantity
            critical = bool(c.min_stock) and balance <= c.min_stock
            if (
                wanted == "critico"
                and not critical
                or wanted == "zerado"
                and balance != 0
                or wanted == "normal"
                and (critical or balance == 0)
            ):
                continue
            situation = "Sem estoque" if balance == 0 else "No mínimo ou abaixo" if critical else "Normal"
            rows.append(
                {
                    "material": c.name,
                    "codigo": c.reference or "",
                    "categoria": c.category.name,
                    "saldo": balance,
                    "unidade": c.get_unit_display(),
                    "minimo": c.min_stock,
                    "situacao": situation,
                }
            )
        return ReportResult(
            columns=[
                Column("material", "Material"),
                Column("codigo", "Código"),
                Column("categoria", "Categoria"),
                Column("saldo", "Saldo", "end"),
                Column("unidade", "Unidade"),
                Column("minimo", "Mínimo", "end"),
                Column("situacao", "Situação"),
            ],
            rows=rows,
            summary=[f"{len(rows)} materiais", f"{sum(r['saldo'] for r in rows)} unidades em estoque"],
        )


class _MovementHistory(Report):
    op_type = ""
    filters = ("periodo", "categoria", "setor")

    def movements(self, params):
        queryset = (
            StockMovement.objects.filter(operation__type=self.op_type)
            .select_related(
                "operation",
                "operation__performed_by",
                "operation__reversed_by",
                "operation__destination_sector",
                "operation__origin_sector",
                "operation__recipient",
                "equipment",
                "consumable",
            )
            .order_by("-operation__performed_at", "id")
        )
        queryset = self.period_filter(queryset, params, "operation__performed_at")
        if category := params.get("categoria"):
            queryset = queryset.filter(Q(equipment__category=category) | Q(consumable__category=category))
        if sector := params.get("setor"):
            queryset = queryset.filter(Q(operation__destination_sector=sector) | Q(operation__origin_sector=sector))
        return queryset


class EntryHistory(_MovementHistory):
    slug = "historico-entradas"
    title = "Histórico de entradas"
    description = "Equipamentos e materiais que entraram no estoque, com fornecedor/nota quando informado."
    op_type = T.ENTRY
    filters = ("periodo", "categoria")

    def run(self, params):
        rows = []
        for m in self.movements(params):
            name, ident = item_label(m)
            rows.append(
                {
                    "data": fmt_date(m.operation.performed_at),
                    "operacao": m.operation.number,
                    "item": name,
                    "identificacao": ident,
                    "quantidade": abs(m.quantity),
                    "fornecedor": m.operation.third_party,
                    "por": m.operation.performed_by.full_name,
                    "estornada": "sim" if m.operation.is_reversed else "",
                }
            )
        return ReportResult(
            columns=[
                Column("data", "Data"),
                Column("operacao", "Operação"),
                Column("item", "Item"),
                Column("identificacao", "Identificação"),
                Column("quantidade", "Qtd.", "end"),
                Column("fornecedor", "Fornecedor / nota"),
                Column("por", "Registrado por"),
                Column("estornada", "Estornada"),
            ],
            rows=rows,
            summary=[f"{len(rows)} linhas", f"{sum(r['quantidade'] for r in rows)} unidades"],
        )


class ExitHistory(_MovementHistory):
    slug = "historico-saidas"
    title = "Histórico de saídas"
    description = "Entregas de equipamentos e retiradas de materiais, com setor e servidor que recebeu."
    op_type = T.EXIT

    def run(self, params):
        rows = []
        for m in self.movements(params):
            name, ident = item_label(m)
            op = m.operation
            rows.append(
                {
                    "data": fmt_date(op.performed_at),
                    "operacao": op.number,
                    "item": name,
                    "identificacao": ident,
                    "quantidade": abs(m.quantity),
                    "setor": sector_label(op.destination_sector),
                    "recebedor": str(op.recipient or ""),
                    "por": op.performed_by.full_name,
                    "estornada": "sim" if op.is_reversed else "",
                }
            )
        return ReportResult(
            columns=[
                Column("data", "Data"),
                Column("operacao", "Operação"),
                Column("item", "Item"),
                Column("identificacao", "Identificação"),
                Column("quantidade", "Qtd.", "end"),
                Column("setor", "Setor"),
                Column("recebedor", "Recebido por"),
                Column("por", "Entregue por"),
                Column("estornada", "Estornada"),
            ],
            rows=rows,
            summary=[f"{len(rows)} linhas", f"{sum(r['quantidade'] for r in rows)} unidades"],
        )


class MonthlyConsumption(Report):
    slug = "consumo-mensal"
    title = "Consumo mensal de materiais"
    description = "Unidades retiradas (menos devolvidas) por material e por mês."
    filters = ("periodo", "categoria_mat", "setor")

    def run(self, params):
        today = timezone.localdate()
        start = params.get("de") or today.replace(month=1, day=1)
        end = params.get("ate") or today
        months = months_between(start, end)[-24:]
        queryset = StockMovement.objects.filter(
            consumable__isnull=False,
            operation__type__in=[T.EXIT, T.RETURN],
            operation__performed_at__date__gte=months[0],
            operation__performed_at__date__lte=end,
        )
        if params.get("categoria"):
            queryset = queryset.filter(consumable__category=params["categoria"])
        if sector := params.get("setor"):
            queryset = queryset.filter(Q(operation__destination_sector=sector) | Q(operation__origin_sector=sector))
        totals: dict[str, dict] = defaultdict(lambda: defaultdict(int))
        for row in queryset.annotate(month=TruncMonth("operation__performed_at")).values(
            "consumable__name", "month", "quantity"
        ):
            totals[row["consumable__name"]][row["month"].date().replace(day=1)] -= row["quantity"]
        keys = [f"m{i}" for i in range(len(months))]
        rows = []
        for name in sorted(totals):
            values = [max(0, totals[name].get(m, 0)) for m in months]
            if not any(values):
                continue
            rows.append({"material": name, **dict(zip(keys, values, strict=True)), "total": sum(values)})
        rows.sort(key=lambda r: -r["total"])
        columns = [
            Column("material", "Material"),
            *[Column(k, month_label(m), "end") for k, m in zip(keys, months, strict=True)],
            Column("total", "Total", "end"),
        ]
        return ReportResult(
            columns=columns,
            rows=rows,
            summary=[f"{len(rows)} materiais", f"{sum(r['total'] for r in rows)} unidades no período"],
        )


class BelowMinimum(Report):
    slug = "abaixo-do-minimo"
    title = "Materiais abaixo do estoque mínimo"
    description = "Alertas abertos, com consumo médio dos últimos 90 dias e sugestão de compra."
    filters = ("categoria_mat",)
    landscape = False

    def run(self, params):
        alerts = (
            LowStockAlert.objects.filter(closed_at__isnull=True)
            .select_related("consumable", "consumable__category", "consumable__balance")
            .order_by("level", "consumable__name")
        )
        if params.get("categoria"):
            alerts = alerts.filter(consumable__category=params["categoria"])
        alerts = list(alerts)
        usage = monthly_consumption([a.consumable_id for a in alerts])
        rows = []
        for a in alerts:
            c, avg = a.consumable, usage.get(a.consumable_id, 0.0)
            rows.append(
                {
                    "material": c.name,
                    "categoria": c.category.name,
                    "saldo": c.balance.quantity,
                    "minimo": c.min_stock,
                    "nivel": a.get_level_display(),
                    "desde": fmt_date(a.opened_at),
                    "consumo": f"{avg:.1f}".replace(".", ","),
                    "sugestao": max(0, round(c.min_stock + 3 * avg - c.balance.quantity)),
                }
            )
        return ReportResult(
            columns=[
                Column("material", "Material"),
                Column("categoria", "Categoria"),
                Column("saldo", "Saldo", "end"),
                Column("minimo", "Mínimo", "end"),
                Column("nivel", "Nível"),
                Column("desde", "Desde"),
                Column("consumo", "Consumo/mês", "end"),
                Column("sugestao", "Sugestão de compra", "end"),
            ],
            rows=rows,
            summary=[f"{len(rows)} materiais críticos"],
        )


def _equipment_queryset(params, statuses=None):
    queryset = Equipment.objects.select_related(
        "category", "current_sector", "current_location", "current_recipient"
    ).exclude(status=S.WRITTEN_OFF)
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    if params.get("situacao"):
        queryset = queryset.filter(status=params["situacao"])
    if params.get("categoria"):
        queryset = queryset.filter(category=params["categoria"])
    if params.get("setor"):
        queryset = queryset.filter(current_sector=params["setor"])
    return queryset


class EquipmentBySector(Report):
    slug = "equipamentos-por-setor"
    title = "Equipamentos por setor"
    description = "Onde está cada equipamento hoje, agrupado por setor (estoque da TI incluído)."
    filters = ("setor", "categoria_eq", "situacao")
    situation_choices = [c for c in EQUIPMENT_SITUATIONS if c[0] != S.WRITTEN_OFF]

    def run(self, params):
        queryset = _equipment_queryset(params).order_by("current_sector__name", "category__name", "name")
        rows = [
            {
                "setor": str(e.current_sector) if e.current_sector else "Estoque da TI",
                "equipamento": e.name,
                "identificacao": identification(e),
                "categoria": e.category.name,
                "situacao": e.get_status_display(),
                "responsavel": str(e.current_recipient or ""),
                "local": e.current_location.name if e.current_location else "",
                "propriedade": "Locado" if e.is_leased else "Próprio",
            }
            for e in queryset
        ]
        sectors = {r["setor"] for r in rows}
        return ReportResult(
            columns=[
                Column("setor", "Setor"),
                Column("equipamento", "Equipamento"),
                Column("identificacao", "Identificação"),
                Column("categoria", "Categoria"),
                Column("situacao", "Situação"),
                Column("responsavel", "Responsável"),
                Column("local", "Local"),
                Column("propriedade", "Propriedade"),
            ],
            rows=rows,
            summary=[f"{len(rows)} equipamentos", f"{len(sectors)} setores"],
        )


class EquipmentByRecipient(Report):
    slug = "equipamentos-por-responsavel"
    title = "Equipamentos por responsável"
    description = "Equipamentos sob responsabilidade de cada servidor (útil em mudança de setor ou desligamento)."
    filters = ("servidor", "setor", "categoria_eq")

    def run(self, params):
        queryset = _equipment_queryset(params, [S.IN_USE, S.ON_LOAN]).filter(current_recipient__isnull=False)
        if term := (params.get("servidor") or "").strip():
            queryset = queryset.filter(
                Q(current_recipient__full_name__icontains=term) | Q(current_recipient__registration=term)
            )
        queryset = queryset.order_by("current_recipient__full_name", "name")
        since = dict(
            EquipmentAssignment.objects.filter(equipment__in=queryset, ended_at__isnull=True).values_list(
                "equipment_id", "started_at"
            )
        )
        rows = [
            {
                "responsavel": e.current_recipient.full_name,
                "matricula": e.current_recipient.registration or "",
                "setor": sector_label(e.current_sector),
                "equipamento": e.name,
                "identificacao": identification(e),
                "situacao": e.get_status_display(),
                "desde": fmt_date(since.get(e.pk)),
            }
            for e in queryset
        ]
        people = {(r["responsavel"], r["matricula"]) for r in rows}
        return ReportResult(
            columns=[
                Column("responsavel", "Responsável"),
                Column("matricula", "Matrícula"),
                Column("setor", "Setor"),
                Column("equipamento", "Equipamento"),
                Column("identificacao", "Identificação"),
                Column("situacao", "Situação"),
                Column("desde", "Desde"),
            ],
            rows=rows,
            summary=[f"{len(rows)} equipamentos", f"{len(people)} servidores"],
        )


class LoanedEquipment(Report):
    slug = "equipamentos-emprestados"
    title = "Equipamentos emprestados"
    description = "Empréstimos em aberto, com data prevista de devolução e atraso."
    filters = ("setor", "atrasados")

    def run(self, params):
        today = timezone.localdate()
        loans = (
            EquipmentAssignment.objects.filter(kind=AssignmentKind.LOAN, ended_at__isnull=True)
            .select_related("equipment", "sector", "recipient")
            .order_by("due_date", "started_at")
        )
        if params.get("setor"):
            loans = loans.filter(sector=params["setor"])
        if params.get("atrasados"):
            loans = loans.filter(due_date__lt=today)
        rows = [
            {
                "equipamento": a.equipment.name,
                "identificacao": identification(a.equipment),
                "setor": sector_label(a.sector),
                "servidor": str(a.recipient or ""),
                "desde": fmt_date(a.started_at),
                "previsto": fmt_date(a.due_date),
                "atraso": (today - a.due_date).days if a.due_date and a.due_date < today else "",
            }
            for a in loans
        ]
        late = sum(1 for r in rows if r["atraso"] != "")
        return ReportResult(
            columns=[
                Column("equipamento", "Equipamento"),
                Column("identificacao", "Identificação"),
                Column("setor", "Setor"),
                Column("servidor", "Servidor"),
                Column("desde", "Emprestado em"),
                Column("previsto", "Devolução prevista"),
                Column("atraso", "Dias de atraso", "end"),
            ],
            rows=rows,
            summary=[f"{len(rows)} empréstimos em aberto", f"{late} atrasados"],
        )


class MaintenanceEquipment(Report):
    slug = "equipamentos-em-manutencao"
    title = "Equipamentos em manutenção"
    description = "Equipamentos enviados para assistência e ainda não retornados."
    filters = ("setor", "categoria_eq")

    def run(self, params):
        now = timezone.now()
        items = (
            EquipmentAssignment.objects.filter(kind=AssignmentKind.MAINTENANCE, ended_at__isnull=True)
            .select_related("equipment", "equipment__category", "sector", "recipient")
            .order_by("started_at")
        )
        if params.get("setor"):
            items = items.filter(sector=params["setor"])
        if params.get("categoria"):
            items = items.filter(equipment__category=params["categoria"])
        rows = [
            {
                "equipamento": a.equipment.name,
                "identificacao": identification(a.equipment),
                "assistencia": a.third_party,
                "enviado": fmt_date(a.started_at),
                "dias": (now - a.started_at).days,
                "origem": sector_label(a.sector) or "Estoque da TI",
                "responsavel": str(a.recipient or ""),
            }
            for a in items
        ]
        return ReportResult(
            columns=[
                Column("equipamento", "Equipamento"),
                Column("identificacao", "Identificação"),
                Column("assistencia", "Assistência"),
                Column("enviado", "Enviado em"),
                Column("dias", "Dias", "end"),
                Column("origem", "Setor de origem"),
                Column("responsavel", "Responsável anterior"),
            ],
            rows=rows,
            summary=[f"{len(rows)} equipamentos em manutenção"],
        )


class EquipmentHistory(Report):
    slug = "historico-equipamento"
    title = "Histórico individual de equipamento"
    description = "Todas as movimentações de um equipamento: por onde passou, com quem e quem registrou."
    filters = ("equipamento",)
    requires = "equipamento"

    def run(self, params):
        matches = list(find_equipment_by_code(params.get("equipamento", ""))[:2])
        if len(matches) != 1:
            message = "Nenhum equipamento encontrado." if not matches else "Mais de um equipamento corresponde."
            return ReportResult(columns=[], rows=[], summary=[message])
        e = matches[0]
        movements = (
            StockMovement.objects.filter(equipment=e)
            .select_related(
                "operation",
                "operation__performed_by",
                "operation__destination_sector",
                "operation__recipient",
                "operation__reverses",
                "sector_before",
            )
            .order_by("operation__performed_at", "id")
        )
        rows = [
            {
                "data": fmt_date(m.operation.performed_at),
                "operacao": m.operation.number,
                "tipo": m.operation.get_type_display(),
                "situacao": (f"{m.get_status_before_display()} → " if m.status_before else "")
                + m.get_status_after_display(),
                "destino": sector_label(m.operation.destination_sector),
                "responsavel": str(m.operation.recipient or ""),
                "por": m.operation.performed_by.full_name,
                "obs": m.operation.justification or m.operation.third_party,
            }
            for m in movements
        ]
        header = [
            ("Equipamento", e.name),
            ("Identificação", identification(e)),
            ("Fabricante / modelo", f"{e.manufacturer} {e.model}".strip()),
            ("Propriedade", e.get_ownership_display()),
            ("Situação atual", e.get_status_display()),
            ("Onde está", e.location_label),
            ("Responsável", str(e.current_recipient or "—")),
        ]
        return ReportResult(
            columns=[
                Column("data", "Data"),
                Column("operacao", "Operação"),
                Column("tipo", "Tipo"),
                Column("situacao", "Situação"),
                Column("destino", "Destino"),
                Column("responsavel", "Responsável"),
                Column("por", "Registrado por"),
                Column("obs", "Justificativa / assistência"),
            ],
            rows=rows,
            header=header,
            summary=[f"{len(rows)} movimentações"],
        )


REPORTS: dict[str, Report] = {
    r.slug: r
    for r in [
        CurrentStock(),
        EntryHistory(),
        ExitHistory(),
        MonthlyConsumption(),
        BelowMinimum(),
        EquipmentBySector(),
        EquipmentByRecipient(),
        LoanedEquipment(),
        MaintenanceEquipment(),
        EquipmentHistory(),
    ]
}
