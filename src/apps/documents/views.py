from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import Capability, has_capability, require_capability
from apps.core.listing import paginate
from apps.inventory.models import StockOperation

from . import rendering, services
from .forms import AssetForm, StatusForm, TemplateForm
from .models import DocumentAsset, DocumentStatus, DocumentTemplate, GeneratedDocument


def _errors(request, error: ValidationError) -> None:
    messages.error(request, " ".join(error.messages))


# --- Termos emitidos -------------------------------------------------------------------


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def document_list(request):
    queryset = GeneratedDocument.objects.select_related(
        "template", "operation", "operation__recipient", "operation__destination_sector", "issued_by"
    ).defer("pdf")
    if term := request.GET.get("q", "").strip():
        queryset = queryset.filter(
            Q(number__icontains=term)
            | Q(operation__number__icontains=term)
            | Q(operation__recipient__full_name__icontains=term)
        )
    status = request.GET.get("situacao", "")
    if status == "pendentes":
        queryset = queryset.filter(
            status__in=[DocumentStatus.GENERATED, DocumentStatus.PRINTED, DocumentStatus.AWAITING]
        )
    elif status in DocumentStatus.values:
        queryset = queryset.filter(status=status)
    if (template := request.GET.get("modelo", "")).isdigit():
        queryset = queryset.filter(template__code=DocumentTemplate.objects.filter(pk=template).values("code")[:1])
    page, querystring = paginate(request, queryset)
    return render(
        request,
        "documents/document_list.html",
        {
            "page": page,
            "querystring": querystring,
            "statuses": DocumentStatus.choices,
            "templates": DocumentTemplate.objects.filter(active=True),
        },
    )


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def document_detail(request, pk: int):
    document = get_object_or_404(
        GeneratedDocument.objects.defer("pdf").select_related("template", "operation", "issued_by", "replaces"), pk=pk
    )
    return render(
        request,
        "documents/document_detail.html",
        {
            "document": document,
            "history": document.status_changes.select_related("changed_by"),
            "next_statuses": [(s, DocumentStatus(s).label) for s in services.allowed_next(document)],
            "replaced_by": GeneratedDocument.objects.filter(replaces=document).defer("pdf").first(),
        },
    )


@xframe_options_sameorigin
@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def document_pdf(request, pk: int):
    """Entrega o PDF guardado (sempre o mesmo arquivo da emissão). ?imprimir=1 conta como impressão."""
    document = get_object_or_404(GeneratedDocument, pk=pk)
    if request.GET.get("imprimir") == "1" and has_capability(request.user, Capability.INVENTORY_OPERATE):
        services.register_print(actor=request.user, document=document)
    disposition = "inline" if request.GET.get("baixar") != "1" else "attachment"
    response = HttpResponse(bytes(document.pdf), content_type="application/pdf")
    response["Content-Disposition"] = f'{disposition}; filename="{document.filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@require_POST
@require_capability(Capability.INVENTORY_OPERATE)
def document_status(request, pk: int):
    document = get_object_or_404(GeneratedDocument.objects.defer("pdf"), pk=pk)
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            services.change_status(
                actor=request.user,
                document=document,
                status=form.cleaned_data["status"],
                note=form.cleaned_data["note"],
            )
        except ValidationError as error:
            _errors(request, error)
        else:
            messages.success(request, "Situação do termo atualizada.")
    return redirect("documents:detail", pk=pk)


@require_POST
@require_capability(Capability.INVENTORY_OPERATE)
def document_reissue(request, pk: int):
    document = get_object_or_404(GeneratedDocument.objects.defer("pdf"), pk=pk)
    try:
        new = services.reissue(actor=request.user, document=document, reason=request.POST.get("reason", ""))
    except ValidationError as error:
        _errors(request, error)
        return redirect("documents:detail", pk=pk)
    messages.success(request, f"Termo reemitido como {new.number}; {document.number} foi cancelado.")
    return redirect("documents:detail", pk=new.pk)


@require_POST
@require_capability(Capability.INVENTORY_OPERATE)
def issue_for_operation(request, pk: int):
    operation = get_object_or_404(StockOperation, pk=pk)
    try:
        document = services.issue(actor=request.user, operation=operation)
    except ValidationError as error:
        _errors(request, error)
        return redirect("inventory:operation_detail", pk=pk)
    messages.success(request, f"Termo {document.number} gerado.")
    return redirect("inventory:operation_detail", pk=pk)


# --- Modelos ---------------------------------------------------------------------------


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def template_list(request):
    templates = DocumentTemplate.objects.select_related("created_by").order_by("name", "-version")
    return render(
        request, "documents/template_list.html", {"templates": templates, "assets": DocumentAsset.objects.all()}
    )


@require_http_methods(["GET", "POST"])
@require_capability(Capability.TEMPLATES_MANAGE)
def template_edit(request, pk: int | None = None):
    base = get_object_or_404(DocumentTemplate, pk=pk) if pk else None
    copy_from = None
    if base is None and (source_id := request.GET.get("copiar", "")).isdigit():
        copy_from = DocumentTemplate.objects.filter(pk=source_id).first()
    origin = base or copy_from
    initial = {}
    if origin:
        initial = {
            "name": origin.name if base else "",
            "item_kind": origin.item_kind,
            "operation_types": origin.operation_types if base else [],
            "css": origin.css,
            "body": origin.body,
            "source": origin.source if base else "",
        }
    form = TemplateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        code = base.code if base else _slug(data["name"])
        try:
            template = services.save_template_version(
                actor=request.user,
                base=base,
                code=code,
                name=data["name"],
                item_kind=data["item_kind"],
                operation_types=data["operation_types"],
                css=data["css"],
                body=data["body"],
                source=data["source"],
            )
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(request, f"{template.name} salvo como versão {template.version}.")
            return redirect("documents:template_list")
    return render(request, "documents/template_form.html", {"form": form, "base": base, "variables": VARIABLES})


def _slug(name: str) -> str:
    from django.utils.text import slugify

    base = slugify(name)[:50] or "modelo"
    code, counter = base, 2
    while DocumentTemplate.objects.filter(code=code).exists():
        code = f"{base}-{counter}"
        counter += 1
    return code


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def template_preview(request, pk: int):
    """PDF do modelo preenchido com a operação real mais recente desse tipo (nada é gravado)."""
    template = get_object_or_404(DocumentTemplate, pk=pk)
    operation = (
        StockOperation.objects.filter(type__in=template.operation_types)
        .filter(
            Q(movements__equipment__isnull=False)
            if template.item_kind == "equipamento"
            else Q(movements__consumable__isnull=False)
        )
        .order_by("-performed_at")
        .first()
    )
    if operation is None:
        messages.info(request, "Ainda não há operação desse tipo para pré-visualizar o modelo.")
        return redirect("documents:template_list")
    data = rendering.build_context(operation, number="PRÉ-VISUALIZAÇÃO")
    pdf = rendering.render_pdf(template, data)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="previa-{template.code}-v{template.version}.pdf"'
    return response


@require_POST
@require_capability(Capability.TEMPLATES_MANAGE)
def template_toggle(request, pk: int):
    template = get_object_or_404(DocumentTemplate, pk=pk)
    try:
        services.set_template_active(actor=request.user, template=template, active=not template.active)
    except ValidationError as error:
        _errors(request, error)
    else:
        messages.success(request, "Modelo ativado." if template.active else "Modelo desativado.")
    return redirect("documents:template_list")


@require_http_methods(["GET", "POST"])
@require_capability(Capability.TEMPLATES_MANAGE)
def asset_upload(request, key: str):
    asset = get_object_or_404(DocumentAsset, key=key)
    form = AssetForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        image = form.cleaned_data["image"]
        with transaction.atomic():
            asset.content = image.read()
            asset.content_type = image.content_type
            asset.save()
            from apps.audit import services as audit
            from apps.audit.models import AuditAction

            audit.record(AuditAction.UPDATE, user=request.user, instance=asset, summary=f"Imagem: {asset.name}")
        messages.success(request, f"{asset.name} substituído. Os próximos termos já usam a nova imagem.")
        return redirect("documents:template_list")
    return render(request, "documents/asset_form.html", {"form": form, "asset": asset})


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def asset_image(request, key: str):
    asset = get_object_or_404(DocumentAsset, key=key)
    response = HttpResponse(bytes(asset.content), content_type=asset.content_type)
    response["Cache-Control"] = "private, max-age=60"
    return response


VARIABLES = [
    ("termo.numero", "Número do termo (TR-2026-000001)"),
    ("termo.cidade / termo.data_extenso", "Duque de Caxias / 04 de maio de 2025"),
    ("termo.dia, termo.mes, termo.ano", 'Partes da data (use |capfirst para "Novembro")'),
    ("operacao.numero, operacao.tipo, operacao.data", "Dados da operação"),
    ("operacao.justificativa, operacao.observacoes, operacao.devolucao_prevista, operacao.assistencia", ""),
    ("origem.secretaria, origem.nome, origem.sigla, origem.rotulo", 'Setor de origem (rotulo = "Nome / SIGLA")'),
    (
        "destino.secretaria, destino.nome, destino.sigla, destino.rotulo",
        "Setor de destino; secretaria = nível mais alto",
    ),
    ("local", "Local de destino (sala, prédio)"),
    ("recebedor.nome, recebedor.matricula, recebedor.cargo, recebedor.setor", "Servidor que recebe"),
    ("responsavel.nome", "Técnico que registrou a operação"),
    (
        "{% for item in itens %} … {% endfor %}",
        "Itens: descricao, categoria, estado, fabricante, modelo, marca_modelo, "
        "patrimonio, serie, codigo_locadora, patrimonio_serie, quantidade, unidade, material, codigo",
    ),
    ("{% for a in acessorios %} … {% endfor %}", "Acessórios: descricao, quantidade"),
    ("imagens.brasao, imagens.logo_dc", 'Use em <img src="{{ imagens.brasao }}">'),
]
