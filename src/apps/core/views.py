from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, has_capability
from apps.audit.models import AuditLog
from apps.organization.models import Recipient, Sector

from .health import run_checks


@require_GET
def home(request):
    context = {
        "sector_count": Sector.objects.filter(active=True).count(),
        "recipient_count": Recipient.objects.filter(active=True).count(),
    }
    if has_capability(request.user, Capability.AUDIT_VIEW):
        context["recent_audit"] = AuditLog.objects.select_related("user")[:8]
    return render(request, "core/home.html", context)


@never_cache
@require_GET
def health(request):
    result = run_checks()
    return JsonResponse(result, status=200 if result["status"] == "ok" else 503)


def permission_denied(request, exception=None):
    return render(request, "core/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "core/404.html", status=404)
