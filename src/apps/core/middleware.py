from django.conf import settings

from .request_context import reset_client_ip, set_client_ip


def client_ip_from_request(request) -> str | None:
    # Atrás de um proxy reverso confiável (USE_HTTPS), usa o primeiro IP do X-Forwarded-For.
    if getattr(settings, "USE_HTTPS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_client_ip(client_ip_from_request(request))
        try:
            return self.get_response(request)
        finally:
            reset_client_ip(token)
