from django.conf import settings

from apps.accounts.permissions import Capability, capabilities_for


def app_context(request):
    user = getattr(request, "user", None)
    caps = capabilities_for(user)
    open_alerts = 0
    if Capability.INVENTORY_VIEW in caps:
        from apps.alerts.services import open_alert_count

        open_alerts = open_alert_count()
    return {
        "open_alerts": open_alerts,
        "ORG_NAME": settings.ORG_NAME,
        "ORG_UNIT_NAME": settings.ORG_UNIT_NAME,
        "APP_VERSION": settings.APP_VERSION,
        "caps": caps,
    }
