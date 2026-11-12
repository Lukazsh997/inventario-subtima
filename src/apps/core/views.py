from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, has_capability
from apps.audit.models import AuditLog
from apps.catalog.models import Consumable, Equipment, EquipmentStatus
from apps.catalog.services import find_equipment_by_code
from apps.core.listing import apply_search
from apps.inventory.models import StockOperation
from apps.organization.models import Recipient, Sector

from .health import run_checks


@require_GET
def home(request):
    context = {
        "sector_count": Sector.objects.filter(active=True).count(),
        "recipient_count": Recipient.objects.filter(active=True).count(),
    }
    if has_capability(request.user, Capability.INVENTORY_VIEW):
        by_status = dict(Equipment.objects.values_list("status").annotate(n=Count("id")).order_by())
        context["equipment_stats"] = [
            (value, label, by_status.get(value, 0))
            for value, label in EquipmentStatus.choices
            if value != EquipmentStatus.WRITTEN_OFF
        ]
        consumables = Consumable.objects.filter(active=True)
        context["critical_count"] = consumables.filter(min_stock__gt=0, balance__quantity__lte=F("min_stock")).count()
        context["empty_count"] = consumables.filter(balance__quantity=0).count()
        context["recent_operations"] = StockOperation.objects.select_related(
            "performed_by", "destination_sector", "recipient"
        )[:8]
    if has_capability(request.user, Capability.AUDIT_VIEW):
        context["recent_audit"] = AuditLog.objects.select_related("user")[:8]
    return render(request, "core/home.html", context)


@require_GET
def search(request):
    """Busca global. Um código que identifica um único equipamento abre direto a ficha."""
    term = request.GET.get("q", "").strip()
    context = {"search_term": term, "equipment": [], "consumables": [], "recipients": [], "operations": []}
    if term:
        if has_capability(request.user, Capability.INVENTORY_VIEW):
            by_code = list(find_equipment_by_code(term)[:2])
            if len(by_code) == 1:
                return redirect("catalog:equipment_detail", pk=by_code[0].pk)
            equipment = Equipment.objects.filter(
                Q(pk__in=[e.pk for e in by_code])
                | Q(
                    pk__in=apply_search(
                        Equipment.objects,
                        term,
                        ["name", "manufacturer", "model", "serial_number", "asset_tag", "lessor_code"],
                    ).values("pk")
                )
            )
            context["equipment"] = equipment.select_related("current_sector")[:20]
            context["consumables"] = apply_search(
                Consumable.objects, term, ["name", "reference", "compatibility"]
            ).select_related("balance")[:20]
            operations = StockOperation.objects.filter(number__iexact=term)
            if operations.count() == 1:
                return redirect("inventory:operation_detail", pk=operations.first().pk)
        if has_capability(request.user, Capability.ORG_VIEW):
            context["recipients"] = apply_search(
                Recipient.objects.filter(active=True), term, ["full_name", "registration"]
            ).select_related("sector")[:20]
    return render(request, "core/search.html", context)


@never_cache
@require_GET
def health(request):
    result = run_checks()
    return JsonResponse(result, status=200 if result["status"] == "ok" else 503)


def permission_denied(request, exception=None):
    return render(request, "core/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "core/404.html", status=404)
