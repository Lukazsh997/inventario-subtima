import logging

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, require_capability
from apps.core.listing import paginate

from . import exporters
from .base import ReportFilterForm
from .definitions import REPORTS

logger = logging.getLogger("patrimonio.reports")


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def index(request):
    return render(request, "reports/index.html", {"reports": REPORTS.values()})


@require_GET
@require_capability(Capability.INVENTORY_VIEW)
def show(request, slug: str):
    report = REPORTS.get(slug)
    if report is None:
        raise Http404
    form = ReportFilterForm(request.GET or None, report=report)
    params = form.cleaned_data if form.is_bound and form.is_valid() else {}
    ready = not report.requires or params.get(report.requires)
    result = report.run(params) if ready and (not form.is_bound or form.is_valid()) else None

    export = request.GET.get("formato")
    if result is not None and export in ("csv", "pdf"):
        filename = f"{report.slug}-{timezone.localdate():%Y%m%d}.{export}"
        if export == "csv":
            response = HttpResponse(exporters.to_csv(result), content_type="text/csv; charset=utf-8")
        else:
            pdf = exporters.to_pdf(report, result, filters=form.describe() if form.is_bound else [], user=request.user)
            response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        logger.info(
            "Relatório exportado", extra={"relatorio": report.slug, "formato": export, "usuario": request.user.username}
        )
        return response

    page = querystring = None
    if result is not None:
        page, querystring = paginate(request, result.rows, per_page=50)
        params_qs = request.GET.copy()
        params_qs.pop("page", None)
        params_qs.pop("formato", None)
        querystring = params_qs.urlencode()
    return render(
        request,
        "reports/show.html",
        {
            "report": report,
            "form": form,
            "result": result,
            "page": page,
            "querystring": querystring,
        },
    )
