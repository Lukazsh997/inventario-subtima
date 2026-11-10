from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

PUBLIC_PREFIXES = ("/health/", "/static/")


class LoginRequiredMiddleware:
    """Toda página exige login, exceto login, health check e arquivos estáticos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        if (
            not request.user.is_authenticated
            and not path.startswith(PUBLIC_PREFIXES)
            and path != reverse(settings.LOGIN_URL)
        ):
            return redirect_to_login(request.get_full_path())
        return self.get_response(request)
