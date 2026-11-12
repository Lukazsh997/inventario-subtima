"""Cabeçalhos de segurança adicionais.

Content-Security-Policy: tudo vem do próprio servidor (bibliotecas empacotadas, sem CDN).
'unsafe-inline'/'unsafe-eval' são necessários para os componentes Alpine.js e os
pequenos scripts das telas; a política ainda impede carregar código ou enviar dados
para qualquer outro endereço (connect-src/form-action 'self').
"""

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
        "frame-src 'self'",
        "worker-src 'self' blob:",
    ]
)

# A câmera é usada só pela própria aplicação (leitura de etiquetas).
PERMISSIONS = "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS)
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
