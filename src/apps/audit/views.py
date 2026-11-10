from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.accounts.permissions import Capability, require_capability
from apps.core.listing import apply_search, paginate

from .models import AuditAction, AuditLog


@require_GET
@require_capability(Capability.AUDIT_VIEW)
def audit_list(request):
    queryset = AuditLog.objects.select_related("user")
    queryset = apply_search(queryset, request.GET.get("q"), ["username", "summary", "entity"])
    action = request.GET.get("acao")
    if action in AuditAction.values:
        queryset = queryset.filter(action=action)
    page, querystring = paginate(request, queryset)
    return render(
        request,
        "audit/list.html",
        {"page": page, "querystring": querystring, "actions": AuditAction.choices},
    )
