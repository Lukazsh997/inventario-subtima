"""Revisão de segurança (Fase 6): regras verificadas automaticamente para não regredirem."""

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.inventory.models import OperationType as T

from . import factories as f

pytestmark = pytest.mark.django_db

PAYLOAD = "x');alert(document.cookie);//"


def _inline_js_attributes(html: str) -> list[str]:
    return re.findall(r'x-data="([^"]*)"', html, flags=re.S)


@pytest.mark.parametrize("url_name", ["inventory:equipment_operation", "inventory:consumable_operation"])
def test_operation_type_from_url_cannot_inject_script(client_for, tech_user, url_name):
    """Valor de ?tipo= vai para dentro de JavaScript num atributo; o escape HTML não basta ali."""
    html = client_for(tech_user).get(reverse(url_name), {"tipo": PAYLOAD}).content.decode()
    for attribute in _inline_js_attributes(html):
        decoded = attribute.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")
        assert "alert(" not in decoded


def test_posted_values_cannot_break_out_of_inline_js(client_for, tech_user):
    sector = f.sector()
    html = (
        client_for(tech_user)
        .post(
            reverse("inventory:equipment_operation"),
            {
                "type": T.EXIT,
                "equipment_ids": [],
                "destination_sector": PAYLOAD,
                "recipient": PAYLOAD,
                "new_recipient_name": PAYLOAD,
                "destination_location": str(sector.pk),
            },
        )
        .content.decode()
    )
    for attribute in _inline_js_attributes(html):
        decoded = attribute.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")
        assert "');alert" not in decoded


def test_entry_form_ownership_cannot_inject_script(client_for, tech_user):
    html = client_for(tech_user).post(reverse("catalog:equipment_create"), {"ownership": PAYLOAD}).content.decode()
    for attribute in _inline_js_attributes(html):
        decoded = attribute.replace("&#x27;", "'").replace("&quot;", '"').replace("&amp;", "&")
        assert "');alert" not in decoded


def _all_routes():
    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield prefix + str(p.pattern), p

    return list(walk(get_resolver().url_patterns))


PUBLIC = {"health/", "contas/login/"}


def _concrete(route: str) -> str:
    route = re.sub(r"<int:\w+>", "1", route)
    route = re.sub(r"<slug:\w+>", "x", route)
    return "/" + route


def test_every_page_requires_login(client):
    """Nenhuma rota, exceto login e health check, responde a quem não está logado."""
    for route, _pattern in _all_routes():
        if route in PUBLIC:
            continue
        for method in ("get", "post"):
            response = getattr(client, method)(_concrete(route))
            assert response.status_code == 302 and "/contas/login/" in response["Location"], (method, route)


def test_viewer_cannot_change_anything(client_for, viewer_user, admin_user):
    """Perfil Consulta: todo POST que altera dados é recusado no servidor."""
    f.equipment(admin_user)
    f.consumable(admin_user, initial=1)
    client = client_for(viewer_user)
    allowed_posts = {"contas/sair/", "contas/senha/"}  # ações sobre a própria conta
    for route, _pattern in _all_routes():
        if route in PUBLIC or route in allowed_posts:
            continue
        response = client.post(_concrete(route))
        assert response.status_code in (403, 404, 405), (route, response.status_code)


def test_security_headers_present(client_for, tech_user):
    response = client_for(tech_user).get(reverse("core:home"))
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    policy = response["Content-Security-Policy"]
    for directive in ["default-src 'self'", "object-src 'none'", "frame-ancestors 'self'", "connect-src 'self'"]:
        assert directive in policy
    assert "camera=(self)" in response["Permissions-Policy"]


def test_session_cookie_flags(client, tech_user, settings):
    from .conftest import PASSWORD

    response = client.post(reverse("accounts:login"), {"username": "tecnico", "password": PASSWORD})
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"


def test_login_does_not_reveal_which_part_is_wrong(client, tech_user):
    wrong_user = client.post(reverse("accounts:login"), {"username": "ninguem", "password": "x"}).content.decode()
    wrong_pass = client.post(reverse("accounts:login"), {"username": "tecnico", "password": "x"}).content.decode()
    assert "Login ou senha incorretos." in wrong_user and "Login ou senha incorretos." in wrong_pass


def test_pdf_generator_cannot_read_server_files_or_network(tmp_path):
    """Um modelo de termo editado não consegue embutir arquivos do servidor nem acessar a rede."""
    import subprocess

    from apps.core.pdf import html_to_pdf

    secret = tmp_path / "segredo.txt"
    secret.write_text("SENHA-SECRETA-123")
    html = (
        f'<p>teste</p><img src="file://{secret}"><object data="file://{secret}"></object>'
        f'<link rel="stylesheet" href="file://{secret}"><img src="http://127.0.0.1:1/x.png">'
        '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4D'
        'wABBAEAwS2OUAAAAABJRU5ErkJggg==">'
    )
    pdf = html_to_pdf(html)
    path = tmp_path / "out.pdf"
    path.write_bytes(pdf)
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
    assert "teste" in text and "SENHA-SECRETA" not in text
    assert b"SENHA-SECRETA" not in pdf
