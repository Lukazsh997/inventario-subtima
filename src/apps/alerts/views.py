from datetime import timedelta

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, require_capability
from apps.core.listing import paginate
from apps.inventory.models import OperationType, StockMovement

from .models import LowStockAlert

CONSUMPTION_WINDOW_DAYS = 90


def monthly_consumption(consumable_ids) -> dict[int, float]:
    """Consumo médio mensal (saídas menos devoluções) dos últimos 90 dias, por material."""
    since = timezone.now() - timedelta(days=CONSUMPTION_WINDOW_DAYS)
    rows = (
        StockMovement.objects.filter(
            consumable_id__in=consumable_ids,
            operation__performed_at__gte=since,
            operation__type__in=[OperationType.EXIT, OperationType.RETURN],
        )
        .values("consumable_id")
        .annotate(total=Sum("quantity"))
    )
    months = CONSUMPTION_WINDOW_DAYS / 30
    return {r["consumable_id"]: max(0.0, -r["total"] / months) for r in rows}


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def critical_list(request):
    history = request.GET.get("historico") == "1"
    queryset = LowStockAlert.objects.select_related("consumable", "consumable__category", "consumable__balance")
    queryset = queryset.filter(closed_at__isnull=not history)
    queryset = queryset.order_by("-closed_at") if history else queryset.order_by("level", "opened_at")
    page, querystring = paginate(request, queryset)
    rows = []
    usage = monthly_consumption([a.consumable_id for a in page]) if not history else {}
    for alert in page:
        avg = usage.get(alert.consumable_id, 0.0)
        balance = alert.consumable.balance.quantity
        rows.append(
            {
                "alert": alert,
                "avg": avg,
                "days_left": int(balance / (avg / 30)) if avg > 0 else None,
                # Sugestão: cobrir 3 meses de consumo acima do mínimo
                "suggested": max(0, round(alert.consumable.min_stock + 3 * avg - balance)) if not history else None,
            }
        )
    return render(
        request,
        "alerts/critical_list.html",
        {
            "page": page,
            "rows": rows,
            "querystring": querystring,
            "history": history,
            "window": CONSUMPTION_WINDOW_DAYS,
        },
    )
