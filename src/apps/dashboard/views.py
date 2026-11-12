from datetime import date

from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, has_capability
from apps.audit.models import AuditLog
from apps.catalog.models import Category
from apps.organization.models import Recipient, Sector

from . import selectors


def _parse_date(value: str | None, fallback: date) -> date:
    try:
        return date.fromisoformat(value) if value else fallback
    except ValueError:
        return fallback


def build_filters(request) -> tuple[selectors.DashboardFilters, list[str]]:
    default_start, default_end = selectors.default_period()
    start = _parse_date(request.GET.get("de"), default_start)
    end = _parse_date(request.GET.get("ate"), default_end)
    warnings = []
    if start > end:
        start, end = end, start
        warnings.append("As datas do período estavam invertidas e foram trocadas.")
    if len(selectors.months_between(start, end)) > 36:
        start = date(end.year - 3, end.month, 1)
        warnings.append("O período foi limitado a 36 meses.")
    category_id = request.GET.get("categoria", "")
    sector_id = request.GET.get("setor", "")
    category = Category.objects.filter(pk=category_id).first() if category_id.isdigit() else None
    sector = Sector.objects.filter(pk=sector_id).first() if sector_id.isdigit() else None
    return selectors.DashboardFilters(start=start, end=end, category=category, sector=sector), warnings


def table_rows(chart: dict) -> list[tuple]:
    """Linhas da tabela alternativa ao gráfico (acessibilidade e conferência dos números)."""
    if "entries" in chart:
        return list(zip(chart["labels"], chart["entries"], chart["exits"], strict=True))
    return list(zip(chart["labels"], chart["values"], strict=True))


@require_GET
def home(request):
    context = {
        "sector_count": Sector.objects.filter(active=True).count(),
        "recipient_count": Recipient.objects.filter(active=True).count(),
    }
    if has_capability(request.user, Capability.INVENTORY_VIEW):
        filters, warnings = build_filters(request)
        months = selectors.months_between(filters.start, filters.end)
        context.update(
            {
                "filters": filters,
                "filter_warnings": warnings,
                "categories": Category.objects.filter(active=True).order_by("kind", "name"),
                "sectors": Sector.objects.filter(active=True),
                "kpi": selectors.indicators(filters),
                "charts": {
                    "entries_exits": selectors.entries_and_exits(filters, months),
                    "consumption": selectors.monthly_consumption(filters, months),
                    "top_withdrawn": selectors.top_withdrawn(filters),
                    "by_sector": selectors.equipment_by_sector(filters),
                    "stock_evolution": selectors.stock_evolution(filters, months),
                    "by_category": selectors.equipment_by_category(filters),
                },
                "recent": selectors.recent_activity(filters),
            }
        )
        context["tables"] = {name: table_rows(chart) for name, chart in context["charts"].items()}
    if has_capability(request.user, Capability.AUDIT_VIEW):
        context["recent_audit"] = AuditLog.objects.select_related("user")[:6]
    return render(request, "dashboard/home.html", context)
