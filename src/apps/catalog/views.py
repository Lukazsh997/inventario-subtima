from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import Capability, require_capability
from apps.core.listing import apply_search, paginate
from apps.inventory import services as inventory
from apps.inventory.models import EquipmentAssignment, OperationType, StockMovement
from apps.organization.models import Sector

from . import services
from .forms import CategoryForm, ConsumableForm, EquipmentForm
from .identification import normalize_scan
from .models import Category, Consumable, Equipment, EquipmentStatus, ItemKind, Ownership


def _form_errors(form, error: ValidationError) -> None:
    for message in error.messages:
        form.add_error(None, message)


# --- Equipamentos ----------------------------------------------------------------------

EQUIPMENT_SEARCH = [
    "name",
    "manufacturer",
    "model",
    "serial_number",
    "asset_tag",
    "lessor_code",
    "current_recipient__full_name",
    "current_sector__name",
    "current_sector__acronym",
]


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def equipment_list(request):
    queryset = Equipment.objects.select_related("category", "current_sector", "current_recipient")
    term = request.GET.get("q", "")
    if term:
        by_code = services.find_equipment_by_code(term).values("pk")
        queryset = queryset.filter(
            Q(pk__in=by_code) | Q(pk__in=apply_search(Equipment.objects, term, EQUIPMENT_SEARCH).values("pk"))
        )
    filters = {
        "categoria": ("category_id", None),
        "situacao": ("status", EquipmentStatus.values),
        "setor": ("current_sector_id", None),
        "propriedade": ("ownership", Ownership.values),
    }
    for param, (field, allowed) in filters.items():
        value = request.GET.get(param, "")
        if value and (allowed is None and value.isdigit() or allowed is not None and value in allowed):
            queryset = queryset.filter(**{field: value})
    if request.GET.get("situacao") != EquipmentStatus.WRITTEN_OFF and not request.GET.get("baixados"):
        queryset = queryset.exclude(status=EquipmentStatus.WRITTEN_OFF)
    page, querystring = paginate(request, queryset)
    return render(
        request,
        "catalog/equipment_list.html",
        {
            "page": page,
            "querystring": querystring,
            "categories": Category.objects.filter(kind=ItemKind.EQUIPMENT),
            "statuses": EquipmentStatus.choices,
            "ownerships": Ownership.choices,
            "sectors": Sector.objects.filter(active=True),
        },
    )


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def equipment_detail(request, pk: int):
    equipment = get_object_or_404(
        Equipment.objects.select_related(
            "category", "current_sector", "current_location", "current_recipient", "created_by"
        ),
        pk=pk,
    )
    movements = (
        StockMovement.objects.filter(equipment=equipment)
        .select_related(
            "operation",
            "operation__performed_by",
            "operation__destination_sector",
            "operation__recipient",
            "operation__reverses",
        )
        .order_by("-operation__performed_at", "-id")
    )
    assignments = EquipmentAssignment.objects.filter(equipment=equipment).select_related(
        "sector", "location", "recipient"
    )
    actions = [
        (op, label)
        for op, label in OperationType.choices
        if op in inventory.EQUIPMENT_RULES and equipment.status in inventory.EQUIPMENT_RULES[op].allowed_from
    ]
    return render(
        request,
        "catalog/equipment_detail.html",
        {
            "equipment": equipment,
            "movements": movements,
            "assignments": assignments,
            "actions": actions,
        },
    )


def _equipment_initial(equipment: Equipment) -> dict:
    return {
        field: getattr(equipment, field) or ""
        for field in [
            "name",
            "manufacturer",
            "model",
            "ownership",
            "lessor",
            "serial_number",
            "asset_tag",
            "lessor_code",
            "condition",
            "notes",
        ]
    } | {"category": equipment.category, "acquisition_date": equipment.acquisition_date}


@require_http_methods(["GET", "POST"])
@require_capability(Capability.CATALOG_MANAGE)
def equipment_create(request):
    from apps.inventory.forms import InitialPlacementForm

    initial = {}
    if "ultimo" in request.GET and (last := Equipment.objects.filter(pk=request.GET["ultimo"]).first()):
        # "Salvar e cadastrar outro igual": repete categoria, fabricante, modelo e propriedade.
        initial = {
            k: v
            for k, v in _equipment_initial(last).items()
            if k in ("category", "name", "manufacturer", "model", "ownership", "lessor", "condition")
        }
    form = EquipmentForm(request.POST or None, initial=initial)
    placement = InitialPlacementForm(request.POST or None, prefix="uso")
    if request.method == "POST" and form.is_valid() and placement.is_valid():
        try:
            with transaction.atomic():
                equipment = inventory.register_equipment(
                    actor=request.user, data=form.cleaned_data, in_use=placement.operation_data(request.user)
                )
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, f"{equipment} cadastrado.")
            if "outro" in request.POST:
                return redirect(f"{request.path}?ultimo={equipment.pk}")
            return redirect("catalog:equipment_detail", pk=equipment.pk)
    return render(
        request,
        "catalog/equipment_form.html",
        {"form": form, "placement": placement, "title": "Entrada de equipamento"},
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.CATALOG_MANAGE)
def equipment_update(request, pk: int):
    equipment = get_object_or_404(Equipment, pk=pk)
    if equipment.status == EquipmentStatus.WRITTEN_OFF:
        messages.error(request, "Equipamento baixado não pode ser alterado.")
        return redirect("catalog:equipment_detail", pk=pk)
    form = EquipmentForm(request.POST or None, initial=_equipment_initial(equipment))
    if request.method == "POST" and form.is_valid():
        try:
            services.update_equipment(actor=request.user, equipment=equipment, data=form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Dados cadastrais atualizados.")
            return redirect("catalog:equipment_detail", pk=pk)
    return render(
        request,
        "catalog/equipment_form.html",
        {"form": form, "title": f"Editar {equipment.name}", "equipment": equipment},
    )


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def equipment_lookup(request):
    """JSON usado pelas telas de operação: equipamentos que correspondem ao código lido."""
    results = [
        {
            "id": e.pk,
            "name": e.name,
            "identifier": e.main_identifier,
            "status": e.status,
            "status_label": e.get_status_display(),
            "location": e.location_label,
            "recipient": str(e.current_recipient or ""),
            "leased": e.is_leased,
            "url": reverse("catalog:equipment_detail", args=[e.pk]),
        }
        for e in services.find_equipment_by_code(request.GET.get("codigo", ""))[:10]
    ]
    return JsonResponse({"code": normalize_scan(request.GET.get("codigo", "")), "results": results})


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def scan(request):
    """Tela "Ler código": abre direto a ficha quando o código corresponde a um único equipamento."""
    code = request.GET.get("codigo", "")
    matches = list(services.find_equipment_by_code(code)) if code else []
    if len(matches) == 1:
        return redirect("catalog:equipment_detail", pk=matches[0].pk)
    return render(request, "catalog/scan.html", {"code": normalize_scan(code), "raw": code, "matches": matches})


# --- Consumíveis -----------------------------------------------------------------------


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def consumable_list(request):
    queryset = Consumable.objects.select_related("category", "balance")
    queryset = apply_search(queryset, request.GET.get("q"), ["name", "reference", "compatibility"])
    category = request.GET.get("categoria", "")
    if category.isdigit():
        queryset = queryset.filter(category_id=category)
    situation = request.GET.get("situacao", "")
    if situation == "critico":
        queryset = queryset.filter(balance__quantity__lte=F("min_stock"), min_stock__gt=0)
    elif situation == "zerado":
        queryset = queryset.filter(balance__quantity=0)
    status = request.GET.get("status", "ativos")
    if status == "ativos":
        queryset = queryset.filter(active=True)
    elif status == "inativos":
        queryset = queryset.filter(active=False)
    page, querystring = paginate(request, queryset.order_by("name"))
    return render(
        request,
        "catalog/consumable_list.html",
        {
            "page": page,
            "querystring": querystring,
            "status": status,
            "categories": Category.objects.filter(kind=ItemKind.CONSUMABLE),
        },
    )


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def consumable_detail(request, pk: int):
    consumable = get_object_or_404(Consumable.objects.select_related("category", "balance"), pk=pk)
    movements = (
        StockMovement.objects.filter(consumable=consumable)
        .select_related(
            "operation",
            "operation__performed_by",
            "operation__destination_sector",
            "operation__origin_sector",
            "operation__recipient",
        )
        .order_by("-operation__performed_at", "-id")
    )
    page, querystring = paginate(request, movements)
    return render(
        request, "catalog/consumable_detail.html", {"consumable": consumable, "page": page, "querystring": querystring}
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.CATALOG_MANAGE)
def consumable_form(request, pk: int | None = None):
    consumable = get_object_or_404(Consumable, pk=pk) if pk else None
    initial = {}
    if consumable:
        initial = {
            "category": consumable.category,
            "name": consumable.name,
            "reference": consumable.reference or "",
            "unit": consumable.unit,
            "min_stock": consumable.min_stock,
            "compatibility": consumable.compatibility,
        }
    form = ConsumableForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            saved = services.save_consumable(actor=request.user, consumable=consumable, data=form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(
                request,
                "Material salvo."
                if consumable
                else "Material cadastrado com saldo 0. Registre a entrada para incluir a quantidade.",
            )
            return redirect("catalog:consumable_detail", pk=saved.pk)
    title = f"Editar {consumable}" if consumable else "Novo material de consumo"
    return render(
        request,
        "organization/simple_form.html",
        {"form": form, "title": title, "cancel_url": "catalog:consumable_list"},
    )


@require_POST
@require_capability(Capability.CATALOG_MANAGE)
def consumable_toggle_active(request, pk: int):
    consumable = get_object_or_404(Consumable, pk=pk)
    services.set_consumable_active(actor=request.user, consumable=consumable, active=not consumable.active)
    messages.success(request, "Material reativado." if consumable.active else "Material desativado.")
    return redirect("catalog:consumable_detail", pk=pk)


# --- Categorias ------------------------------------------------------------------------


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def category_list(request):
    categories = Category.objects.order_by("kind", "name")
    return render(request, "catalog/category_list.html", {"categories": categories})


@require_http_methods(["GET", "POST"])
@require_capability(Capability.CATEGORIES_MANAGE)
def category_form(request, pk: int | None = None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    initial = {"name": category.name, "kind": category.kind} if category else {}
    form = CategoryForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_category(actor=request.user, category=category, **form.cleaned_data)
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Categoria salva.")
            return redirect("catalog:category_list")
    title = f"Editar {category}" if category else "Nova categoria"
    return render(
        request, "organization/simple_form.html", {"form": form, "title": title, "cancel_url": "catalog:category_list"}
    )


@require_POST
@require_capability(Capability.CATEGORIES_MANAGE)
def category_toggle_active(request, pk: int):
    category = get_object_or_404(Category, pk=pk)
    services.set_category_active(actor=request.user, category=category, active=not category.active)
    messages.success(request, "Categoria reativada." if category.active else "Categoria desativada.")
    return redirect("catalog:category_list")
