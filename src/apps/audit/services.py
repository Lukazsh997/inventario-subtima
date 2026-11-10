"""Registro de auditoria usado por todos os serviços de domínio."""

from datetime import date, datetime
from decimal import Decimal

from django.db import models

from apps.core.request_context import get_client_ip

from .models import AuditAction, AuditLog


def _serialize(value):
    if isinstance(value, models.Model):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def snapshot(instance: models.Model, fields: list[str]) -> dict:
    """Foto dos campos informados, para comparar antes e depois de uma alteração."""
    return {field: _serialize(getattr(instance, field)) for field in fields}


def diff(before: dict, after: dict) -> dict:
    return {key: {"de": before.get(key), "para": after.get(key)} for key in after if before.get(key) != after.get(key)}


def record(
    action: str | AuditAction,
    *,
    user=None,
    instance: models.Model | None = None,
    entity: str = "",
    entity_id: str = "",
    summary: str = "",
    changes: dict | None = None,
    username: str = "",
) -> AuditLog:
    if instance is not None:
        entity = entity or instance._meta.label_lower
        entity_id = entity_id or str(instance.pk)
        summary = summary or str(instance)[:255]
    authenticated = user is not None and getattr(user, "is_authenticated", False)
    return AuditLog.objects.create(
        user=user if authenticated else None,
        username=(user.get_username() if authenticated else username)[:150],
        action=str(action),
        entity=entity,
        entity_id=entity_id,
        summary=summary[:255],
        changes=changes or {},
        ip_address=get_client_ip(),
    )
