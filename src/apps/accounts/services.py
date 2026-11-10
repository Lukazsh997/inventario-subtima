"""Casos de uso de usuários do sistema. Toda alteração passa por aqui e é auditada."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditAction

from .models import AuthSource, User
from .permissions import Capability, ensure_capability
from .roles import Role

AUDITED_FIELDS = ["username", "full_name", "email", "role", "sector", "is_active"]


def _count_active_admins(exclude: User | None = None) -> int:
    queryset = User.objects.filter(role=Role.ADMIN, is_active=True)
    if exclude is not None:
        queryset = queryset.exclude(pk=exclude.pk)
    return queryset.count()


def _guard_last_admin(user: User, *, new_role: str, new_active: bool) -> None:
    """Impede que o sistema fique sem nenhum administrador ativo."""
    was_admin = user.role == Role.ADMIN and user.is_active
    stays_admin = new_role == Role.ADMIN and new_active
    if was_admin and not stays_admin and _count_active_admins(exclude=user) == 0:
        raise ValidationError("É preciso manter pelo menos um administrador ativo.")


@transaction.atomic
def create_user(
    *, actor, username: str, full_name: str, password: str, role: str, sector=None, email: str = ""
) -> User:
    ensure_capability(actor, Capability.USERS_MANAGE)
    user = User(
        username=username.strip(),
        full_name=full_name.strip(),
        email=email.strip(),
        role=role,
        sector=sector,
        auth_source=AuthSource.LOCAL,
    )
    validate_password(password, user)
    user.set_password(password)
    user.full_clean()
    user.save()
    audit.record(
        AuditAction.CREATE,
        user=actor,
        instance=user,
        changes=audit.diff({}, audit.snapshot(user, AUDITED_FIELDS)),
    )
    return user


@transaction.atomic
def update_user(*, actor, user: User, full_name: str, role: str, sector=None, email: str = "") -> User:
    ensure_capability(actor, Capability.USERS_MANAGE)
    user = User.objects.select_for_update().get(pk=user.pk)
    _guard_last_admin(user, new_role=role, new_active=user.is_active)
    before = audit.snapshot(user, AUDITED_FIELDS)
    user.full_name = full_name.strip()
    user.role = role
    user.sector = sector
    user.email = email.strip()
    user.full_clean()
    user.save()
    changes = audit.diff(before, audit.snapshot(user, AUDITED_FIELDS))
    if changes:
        audit.record(AuditAction.UPDATE, user=actor, instance=user, changes=changes)
    return user


@transaction.atomic
def set_active(*, actor, user: User, active: bool) -> User:
    ensure_capability(actor, Capability.USERS_MANAGE)
    user = User.objects.select_for_update().get(pk=user.pk)
    if not active and user.pk == actor.pk:
        raise ValidationError("Você não pode desativar a sua própria conta.")
    _guard_last_admin(user, new_role=user.role, new_active=active)
    if user.is_active == active:
        return user
    user.is_active = active
    user.save(update_fields=["is_active"])
    audit.record(AuditAction.REACTIVATE if active else AuditAction.DEACTIVATE, user=actor, instance=user)
    return user


@transaction.atomic
def reset_password(*, actor, user: User, new_password: str) -> User:
    ensure_capability(actor, Capability.USERS_MANAGE)
    validate_password(new_password, user)
    user.set_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    user.save(update_fields=["password", "failed_login_count", "locked_until"])
    audit.record(AuditAction.PASSWORD_RESET, user=actor, instance=user)
    return user


def register_password_change(user: User) -> None:
    audit.record(AuditAction.PASSWORD_CHANGE, user=user, instance=user)


# --- Login e bloqueio por tentativas -------------------------------------------------


def is_locked(username: str) -> bool:
    user = User.objects.filter(username__iexact=username).only("locked_until").first()
    return bool(user and user.is_locked)


@transaction.atomic
def register_login_failure(username: str) -> None:
    user = User.objects.select_for_update().filter(username__iexact=username).first()
    audit.record(
        AuditAction.LOGIN_FAILED,
        username=username,
        entity="accounts.user",
        entity_id=str(user.pk) if user else "",
        summary=f"Tentativa de login: {username}",
    )
    if user is None:
        return
    user.failed_login_count += 1
    if user.failed_login_count >= settings.LOGIN_MAX_FAILURES:
        user.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
        user.failed_login_count = 0
    user.save(update_fields=["failed_login_count", "locked_until"])


def register_login_success(user: User) -> None:
    if user.failed_login_count or user.locked_until:
        User.objects.filter(pk=user.pk).update(failed_login_count=0, locked_until=None)
    audit.record(AuditAction.LOGIN, user=user, instance=user)


def register_logout(user: User) -> None:
    if user.is_authenticated:
        audit.record(AuditAction.LOGOUT, user=user, instance=user)


@transaction.atomic
def ensure_initial_admin(*, username: str, password: str, full_name: str) -> User | None:
    """Cria o primeiro administrador quando o banco ainda não tem nenhum usuário."""
    if not username or not password or User.objects.exists():
        return None
    user = User(username=username, full_name=full_name, role=Role.ADMIN, is_staff=False)
    validate_password(password, user)
    user.set_password(password)
    user.save()
    audit.record(AuditAction.CREATE, username="sistema", instance=user, summary=f"Administrador inicial: {username}")
    return user
