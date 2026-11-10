"""RBAC: o que cada perfil pode e não pode fazer, verificado no backend."""

import pytest
from django.urls import reverse

from apps.accounts.permissions import Capability, capabilities_for, has_capability

pytestmark = pytest.mark.django_db


def test_capabilities_by_role(admin_user, tech_user, viewer_user):
    assert capabilities_for(admin_user) == frozenset(Capability)
    assert has_capability(tech_user, Capability.RECIPIENTS_MANAGE)
    assert not has_capability(tech_user, Capability.USERS_MANAGE)
    assert not has_capability(tech_user, Capability.SECTORS_MANAGE)
    assert capabilities_for(viewer_user) == {Capability.ORG_VIEW}


def test_inactive_user_has_no_capabilities(admin_user):
    admin_user.is_active = False
    assert capabilities_for(admin_user) == frozenset()


def test_anonymous_is_redirected_to_login(client):
    response = client.get(reverse("organization:sector_list"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


@pytest.mark.parametrize(
    "url_name", ["accounts:user_list", "accounts:user_create", "audit:list", "organization:sector_create"]
)
def test_technician_blocked_from_admin_pages(client_for, tech_user, url_name):
    assert client_for(tech_user).get(reverse(url_name)).status_code == 403


@pytest.mark.parametrize(
    "url_name", ["organization:recipient_create", "organization:sector_create", "accounts:user_list"]
)
def test_viewer_cannot_open_forms(client_for, viewer_user, url_name):
    assert client_for(viewer_user).get(reverse(url_name)).status_code == 403


def test_viewer_cannot_post_directly(client_for, viewer_user):
    """Esconder o botão não basta: o POST direto também é recusado."""
    from apps.organization.models import Sector

    sector = Sector.objects.create(name="Secretaria de Saúde")
    client = client_for(viewer_user)
    response = client.post(reverse("organization:recipient_create"), {"full_name": "Fulano", "sector": sector.pk})
    assert response.status_code == 403
    assert not sector.recipients.exists()


@pytest.mark.parametrize("url_name", ["organization:sector_list", "organization:recipient_list", "core:home"])
def test_viewer_can_read(client_for, viewer_user, url_name):
    assert client_for(viewer_user).get(reverse(url_name)).status_code == 200
