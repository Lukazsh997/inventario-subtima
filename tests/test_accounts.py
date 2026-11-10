import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts import services
from apps.accounts.roles import Role
from apps.audit.models import AuditAction, AuditLog

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db
User = get_user_model()


def test_password_is_hashed_with_argon2(admin_user):
    created = services.create_user(
        actor=admin_user,
        username="maria",
        full_name="Maria Souza",
        password="Outra-senha-forte-1",
        role=Role.TECHNICIAN,
    )
    created.refresh_from_db()
    assert created.password.startswith("argon2")
    assert "Outra-senha-forte-1" not in created.password


def test_create_user_is_audited(admin_user):
    created = services.create_user(
        actor=admin_user, username="joao", full_name="João", password="Senha-muito-forte-9", role=Role.VIEWER
    )
    entry = AuditLog.objects.get(action=AuditAction.CREATE, entity_id=str(created.pk))
    assert entry.user == admin_user
    assert entry.changes["role"]["para"] == Role.VIEWER


def test_weak_password_rejected(admin_user):
    with pytest.raises(ValidationError):
        services.create_user(actor=admin_user, username="fraco", full_name="Fraco", password="123", role=Role.VIEWER)
    assert not User.objects.filter(username="fraco").exists()


def test_technician_cannot_create_users_via_service(tech_user):
    with pytest.raises(PermissionDenied):
        services.create_user(
            actor=tech_user, username="x", full_name="X", password="Senha-muito-forte-9", role=Role.ADMIN
        )


def test_last_admin_cannot_be_demoted_or_deactivated(admin_user, make_user):
    other_admin = make_user("admin2", Role.ADMIN)
    services.set_active(actor=admin_user, user=other_admin, active=False)
    with pytest.raises(ValidationError):
        services.update_user(actor=admin_user, user=admin_user, full_name="Admin", role=Role.TECHNICIAN)
    with pytest.raises(ValidationError):
        services.set_active(actor=admin_user, user=admin_user, active=False)


def test_login_success_and_audit(client, tech_user):
    response = client.post(reverse("accounts:login"), {"username": "tecnico", "password": PASSWORD})
    assert response.status_code == 302
    assert AuditLog.objects.filter(action=AuditAction.LOGIN, user=tech_user).exists()


def test_login_lockout_after_repeated_failures(client, tech_user, settings):
    settings.LOGIN_MAX_FAILURES = 3
    for _ in range(3):
        client.post(reverse("accounts:login"), {"username": "tecnico", "password": "errada"})
    tech_user.refresh_from_db()
    assert tech_user.is_locked
    response = client.post(reverse("accounts:login"), {"username": "tecnico", "password": PASSWORD})
    assert response.status_code == 200  # continua na tela de login
    assert "bloqueada" in response.content.decode()
    assert AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).count() == 3


def test_admin_reset_unlocks_account(admin_user, tech_user, settings):
    settings.LOGIN_MAX_FAILURES = 1
    services.register_login_failure("tecnico")
    tech_user.refresh_from_db()
    assert tech_user.is_locked
    services.reset_password(actor=admin_user, user=tech_user, new_password="Nova-senha-forte-3")
    tech_user.refresh_from_db()
    assert not tech_user.is_locked
    assert tech_user.check_password("Nova-senha-forte-3")


def test_open_redirect_blocked_on_login(client, tech_user):
    response = client.post(
        reverse("accounts:login") + "?next=https://malicioso.example/", {"username": "tecnico", "password": PASSWORD}
    )
    assert response["Location"] == reverse("core:home")


def test_logout_requires_post(client_for, tech_user):
    client = client_for(tech_user)
    assert client.get(reverse("accounts:logout")).status_code == 405
    assert client.post(reverse("accounts:logout")).status_code == 302


def test_ensure_initial_admin_only_on_empty_database(db):
    first = services.ensure_initial_admin(username="root", password="Senha-inicial-forte-7", full_name="Admin")
    assert first is not None and first.role == Role.ADMIN
    second = services.ensure_initial_admin(username="outro", password="Senha-inicial-forte-7", full_name="X")
    assert second is None
    assert User.objects.count() == 1


def test_user_management_views(client_for, admin_user):
    client = client_for(admin_user)
    response = client.post(
        reverse("accounts:user_create"),
        {
            "username": "ana",
            "full_name": "Ana Lima",
            "email": "",
            "role": Role.TECHNICIAN,
            "sector": "",
            "password1": "Senha-da-Ana-2026",
            "password2": "Senha-da-Ana-2026",
        },
    )
    assert response.status_code == 302
    ana = User.objects.get(username="ana")
    response = client.post(reverse("accounts:user_toggle_active", args=[ana.pk]))
    ana.refresh_from_db()
    assert not ana.is_active
    assert "ana" in client.get(reverse("accounts:user_list") + "?status=inativos").content.decode()
