from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import Capability, has_capability, require_capability
from apps.core.listing import apply_search, paginate

from . import services
from .forms import LocationForm, RecipientForm, SectorForm
from .models import Location, Recipient, Sector


def _form_errors(form, error: ValidationError) -> None:
    for message in error.messages:
        form.add_error(None, message)


def _status_filter(request, queryset):
    status = request.GET.get("status", "ativos")
    if status == "ativos":
        queryset = queryset.filter(active=True)
    elif status == "inativos":
        queryset = queryset.filter(active=False)
    return queryset, status


# --- Setores ---------------------------------------------------------------------------


@require_GET
@require_capability(Capability.ORG_VIEW)
def sector_list(request):
    queryset = (
        Sector.objects.select_related("parent")
        .annotate(recipient_count=Count("recipients", filter=Q(recipients__active=True)))
        .order_by("name")
    )
    queryset = apply_search(queryset, request.GET.get("q"), ["name", "acronym", "parent__name"])
    queryset, status = _status_filter(request, queryset)
    page, querystring = paginate(request, queryset)
    return render(
        request, "organization/sector_list.html", {"page": page, "querystring": querystring, "status": status}
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.ORG_VIEW)
def sector_detail(request, pk: int):
    sector = get_object_or_404(Sector.objects.select_related("parent"), pk=pk)
    can_manage = has_capability(request.user, Capability.SECTORS_MANAGE)
    location_form = LocationForm(request.POST or None) if can_manage else None
    if request.method == "POST":
        if not can_manage:
            return redirect("organization:sector_detail", pk=pk)
        if location_form.is_valid():
            try:
                services.save_location(
                    actor=request.user, location=None, sector=sector, name=location_form.cleaned_data["name"]
                )
            except ValidationError as error:
                _form_errors(location_form, error)
            else:
                messages.success(request, "Local adicionado.")
                return redirect("organization:sector_detail", pk=pk)
    return render(
        request,
        "organization/sector_detail.html",
        {
            "sector": sector,
            "children": sector.children.order_by("-active", "name"),
            "locations": sector.locations.order_by("-active", "name"),
            "recipients": sector.recipients.filter(active=True).order_by("full_name")[:50],
            "location_form": location_form,
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.SECTORS_MANAGE)
def sector_form(request, pk: int | None = None):
    sector = get_object_or_404(Sector, pk=pk) if pk else None
    initial = {"name": sector.name, "acronym": sector.acronym, "parent": sector.parent} if sector else {}
    form = SectorForm(request.POST or None, initial=initial, editing=sector)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            saved = services.save_sector(
                actor=request.user, sector=sector, name=data["name"], acronym=data["acronym"], parent=data["parent"]
            )
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Setor salvo.")
            return redirect("organization:sector_detail", pk=saved.pk)
    title = f"Editar {sector}" if sector else "Novo setor"
    return render(
        request,
        "organization/simple_form.html",
        {
            "form": form,
            "title": title,
            "cancel_url": "organization:sector_list",
        },
    )


@require_POST
@require_capability(Capability.SECTORS_MANAGE)
def sector_toggle_active(request, pk: int):
    sector = get_object_or_404(Sector, pk=pk)
    try:
        services.set_sector_active(actor=request.user, sector=sector, active=not sector.active)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Setor reativado." if sector.active else "Setor desativado.")
    return redirect("organization:sector_detail", pk=pk)


@require_POST
@require_capability(Capability.SECTORS_MANAGE)
def location_toggle_active(request, pk: int):
    location = get_object_or_404(Location, pk=pk)
    services.set_location_active(actor=request.user, location=location, active=not location.active)
    messages.success(request, "Local reativado." if location.active else "Local desativado.")
    return redirect("organization:sector_detail", pk=location.sector_id)


# --- Servidores recebedores ------------------------------------------------------------


@require_GET
@require_capability(Capability.ORG_VIEW)
def recipient_list(request):
    queryset = Recipient.objects.select_related("sector")
    queryset = apply_search(
        queryset, request.GET.get("q"), ["full_name", "registration", "job_title", "sector__name", "sector__acronym"]
    )
    sector_id = request.GET.get("setor")
    if sector_id and sector_id.isdigit():
        queryset = queryset.filter(sector_id=int(sector_id))
    queryset, status = _status_filter(request, queryset)
    page, querystring = paginate(request, queryset)
    return render(
        request,
        "organization/recipient_list.html",
        {
            "page": page,
            "querystring": querystring,
            "status": status,
            "sectors": Sector.objects.filter(active=True),
            "selected_sector": sector_id or "",
        },
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.RECIPIENTS_MANAGE)
def recipient_form(request, pk: int | None = None):
    recipient = get_object_or_404(Recipient, pk=pk) if pk else None
    initial = {}
    if recipient:
        initial = {
            "full_name": recipient.full_name,
            "registration": recipient.registration or "",
            "job_title": recipient.job_title,
            "sector": recipient.sector,
            "phone": recipient.phone,
        }
    elif request.GET.get("setor", "").isdigit():
        initial = {"sector": request.GET["setor"]}
    form = RecipientForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            services.save_recipient(
                actor=request.user,
                recipient=recipient,
                full_name=data["full_name"],
                sector=data["sector"],
                registration=data["registration"],
                job_title=data["job_title"],
                phone=data["phone"],
            )
        except ValidationError as error:
            _form_errors(form, error)
        else:
            messages.success(request, "Servidor salvo.")
            return redirect("organization:recipient_list")
    title = f"Editar {recipient.full_name}" if recipient else "Novo servidor"
    return render(
        request,
        "organization/simple_form.html",
        {
            "form": form,
            "title": title,
            "cancel_url": "organization:recipient_list",
            "help": (
                "Servidores são as pessoas que recebem materiais e assinam os termos. "
                "Não precisam ter login no sistema."
            ),
        },
    )


@require_POST
@require_capability(Capability.RECIPIENTS_MANAGE)
def recipient_toggle_active(request, pk: int):
    recipient = get_object_or_404(Recipient, pk=pk)
    services.set_recipient_active(actor=request.user, recipient=recipient, active=not recipient.active)
    messages.success(request, "Servidor reativado." if recipient.active else "Servidor desativado.")
    return redirect("organization:recipient_list")
