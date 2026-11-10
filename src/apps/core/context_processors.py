from django.conf import settings

from apps.accounts.permissions import capabilities_for


def app_context(request):
    user = getattr(request, "user", None)
    return {
        "ORG_NAME": settings.ORG_NAME,
        "ORG_UNIT_NAME": settings.ORG_UNIT_NAME,
        "APP_VERSION": settings.APP_VERSION,
        "caps": capabilities_for(user),
    }
