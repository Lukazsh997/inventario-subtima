from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import Capability, has_capability, require_capability
from apps.catalog.models import Consumable, Equipment
from apps.core.listing import apply_search, paginate
from apps.organization.models import Location, Recipient, Sector

from . import services
from .forms import CONSUMABLE_TYPE_LABELS, EQUIPMENT_TYPE_LABELS, ConsumableOperationForm, EquipmentOperationForm
from .models import OperationType, StockOperation

T = OperationType


def _form_errors(form, error: ValidationError) -> None:
    for message in error.messages:
        form.add_error(None, message)


def _type_capability_ok(user, op_type: str) -> bool:
    if op_type == T.ADJUSTMENT:
        return has_capability(user, Capability.STOCK_ADJUST)
    if op_type == T.WRITE_OFF:
        return has_capability(user, Capability.EQUIPMENT_WRITE_OFF)
    return True


def _rules_for_js() -> dict:
    """Regras de cada tipo para a tela mostrar só os campos necessários (a validação real é no servidor)."""
    rules = {
        op: {
            "allowed": sorted(rule.allowed_from),
            "destination": rule.needs_destination,
            "recipient": rule.needs_recipient,
            "thirdParty": rule.needs_third_party,
            "justification": rule.needs_justification,
            "dueDate": op == T.LOAN,
            "accessories": op in (T.EXIT, T.LOAN, T.TRANSFER),
        }
        for op, rule in services.EQUIPMENT_RULES.items()
    }
    return rules


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def operation_list(request):
    queryset = StockOperation.objects.select_related(
        "performed_by", "destination_sector", "origin_sector", "recipient", "reverses"
    ).prefetch_related("reversed_by")
    queryset = apply_search(
        queryset,
        request.GET.get("q"),
        [
            "number",
            "recipient__full_name",
            "destination_sector__name",
            "destination_sector__acronym",
            "performed_by__full_name",
            "justification",
            "movements__equipment__serial_number",
            "movements__equipment__asset_tag",
            "movements__equipment__lessor_code",
            "movements__consumable__name",
        ],
    ).distinct()
    op_type = request.GET.get("tipo", "")
    if op_type in T.values:
        queryset = queryset.filter(type=op_type)
    for param, lookup in (("de", "performed_at__date__gte"), ("ate", "performed_at__date__lte")):
        if value := request.GET.get(param):
            try:
                queryset = queryset.filter(**{lookup: value})
            except ValidationError:
                messages.warning(request, "Data inválida no filtro.")
    page, querystring = paginate(request, queryset)
    return render(
        request, "inventory/operation_list.html", {"page": page, "querystring": querystring, "types": T.choices}
    )


@require_http_methods(["GET"])
@require_capability(Capability.INVENTORY_VIEW)
def operation_detail(request, pk: int):
    operation = get_object_or_404(
        StockOperation.objects.select_related(
            "performed_by", "origin_sector", "destination_sector", "destination_location", "recipient", "reverses"
        ),
        pk=pk,
    )
    reversal = StockOperation.objects.filter(reverses=operation).first()
    movements = operation.movements.select_related(
        "equipment", "equipment__category", "consumable", "sector_before", "recipient_before"
    )
    return render(
        request,
        "inventory/operation_detail.html",
        {
            "operation": operation,
            "movements": movements,
            "accessories": operation.accessories.all(),
            "reversal": reversal,
        },
    )


@require_POST
@require_capability(Capability.OPERATION_REVERSE)
def operation_reverse(request, pk: int):
    operation = get_object_or_404(StockOperation, pk=pk)
    try:
        reversal = services.reverse_operation(
            actor=request.user, operation=operation, justification=request.POST.get("justification", "")
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("inventory:operation_detail", pk=pk)
    messages.success(request, f"Operação {operation.number} estornada por {reversal.number}.")
    return redirect("inventory:operation_detail", pk=reversal.pk)


@require_http_methods(["GET", "POST"])
@require_capability(Capability.INVENTORY_OPERATE)
def equipment_operation(request):
    op_type = request.POST.get("type") or request.GET.get("tipo") or T.EXIT
    form = EquipmentOperationForm(request.POST or None, op_type=op_type)
    if request.method == "POST" and form.is_valid():
        if not _type_capability_ok(request.user, op_type):
            form.add_error(None, "Seu perfil não pode registrar este tipo de operação.")
        else:
            try:
                with transaction.atomic():
                    operation = services.move_equipment(
                        actor=request.user,
                        op_type=op_type,
                        equipment_ids=form.equipment_ids,
                        data=form.operation_data(request.user, accessories=form.accessories),
                    )
            except ValidationError as error:
                _form_errors(form, error)
            else:
                messages.success(request, f"{operation.get_type_display()} registrada: {operation.number}.")
                return redirect("inventory:operation_detail", pk=operation.pk)

    if request.method == "POST":
        preselected = form.selected_equipment()
    else:
        ids = [int(v) for v in request.GET.getlist("equipamento") if v.isdigit()]
        preselected = list(Equipment.objects.filter(pk__in=ids).select_related("current_sector", "current_recipient"))
    items = [
        {
            "id": e.pk,
            "name": e.name,
            "identifier": e.main_identifier,
            "status": e.status,
            "status_label": e.get_status_display(),
            "location": e.location_label,
            "recipient": str(e.current_recipient or ""),
            "leased": e.is_leased,
        }
        for e in preselected
    ]
    types = [(v, label) for v, label in EQUIPMENT_TYPE_LABELS if _type_capability_ok(request.user, v)]
    return render(
        request,
        "inventory/equipment_operation.html",
        {
            "form": form,
            "op_type": op_type,
            "types": types,
            "items": items,
            "rules": _rules_for_js(),
            "accessories": [
                {"description": d, "quantity": q}
                for d, q in zip(
                    request.POST.getlist("accessory_description"),
                    request.POST.getlist("accessory_quantity"),
                    strict=False,
                )
            ],
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.INVENTORY_OPERATE)
def consumable_operation(request):
    op_type = request.POST.get("type") or request.GET.get("tipo") or T.EXIT
    form = ConsumableOperationForm(request.POST or None, op_type=op_type)
    if request.method == "POST" and form.is_valid():
        if not _type_capability_ok(request.user, op_type):
            form.add_error(None, "Seu perfil não pode registrar este tipo de operação.")
        else:
            try:
                with transaction.atomic():
                    operation = services.move_consumables(
                        actor=request.user, op_type=op_type, lines=form.lines, data=form.operation_data(request.user)
                    )
            except ValidationError as error:
                _form_errors(form, error)
            else:
                messages.success(request, f"{operation.get_type_display()} registrada: {operation.number}.")
                return redirect("inventory:operation_detail", pk=operation.pk)

    consumables = [
        {
            "id": c.pk,
            "name": c.name,
            "unit": c.get_unit_display(),
            "balance": c.balance.quantity if hasattr(c, "balance") else 0,
        }
        for c in Consumable.objects.filter(active=True).select_related("balance").order_by("name")
    ]
    lines = form.raw_lines() if request.method == "POST" else []
    if not lines and (preset := request.GET.get("material", "")).isdigit():
        lines = [{"consumable_id": preset, "quantity": ""}]
    types = [(v, label) for v, label in CONSUMABLE_TYPE_LABELS if _type_capability_ok(request.user, v)]
    return render(
        request,
        "inventory/consumable_operation.html",
        {
            "form": form,
            "op_type": op_type,
            "types": types,
            "consumables": consumables,
            "lines": lines or [{"consumable_id": "", "quantity": ""}],
        },
    )


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def sector_options(request):
    """JSON: servidores e locais ativos de um setor, para os campos dependentes das operações."""
    sector_id = request.GET.get("setor", "")
    if not sector_id.isdigit():
        return JsonResponse({"recipients": [], "locations": []})
    sector = get_object_or_404(Sector, pk=sector_id)
    recipients = Recipient.objects.filter(sector=sector, active=True).order_by("full_name")
    locations = Location.objects.filter(sector=sector, active=True).order_by("name")
    return JsonResponse(
        {
            "recipients": [{"id": r.pk, "label": str(r)} for r in recipients],
            "locations": [{"id": loc.pk, "label": loc.name} for loc in locations],
        }
    )
