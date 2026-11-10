import json
import logging

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.audit import services as audit
from apps.audit.models import AuditAction, AuditLog
from config.logging import JsonFormatter

pytestmark = pytest.mark.django_db


def test_health_check_ok_without_login(client):
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": "ok", "media": "ok"}


def test_health_check_reports_unwritable_media(client, settings, tmp_path):
    blocker = tmp_path / "arquivo"
    blocker.write_text("x")
    settings.MEDIA_ROOT = blocker / "media"  # caminho impossível: pai é um arquivo
    response = client.get(reverse("core:health"))
    assert response.status_code == 503
    assert response.json()["checks"]["media"] != "ok"


def test_audit_log_is_append_only_in_database(admin_user):
    entry = audit.record(AuditAction.LOGIN, user=admin_user, instance=admin_user)
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(summary="adulterado")
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()
    entry.refresh_from_db()
    assert entry.summary != "adulterado"


def test_audit_records_client_ip(client_for, admin_user):
    client = client_for(admin_user)
    client.post(reverse("organization:sector_create"), {"name": "Governo"}, REMOTE_ADDR="10.1.2.3")
    entry = AuditLog.objects.get(action=AuditAction.CREATE, entity="organization.sector")
    assert entry.ip_address == "10.1.2.3"


def test_json_log_formatter():
    record = logging.makeLogRecord(
        {"name": "app", "levelname": "INFO", "msg": "olá %s", "args": ("mundo",), "extra_field": 42}
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "olá mundo"
    assert payload["extra_field"] == 42


def test_security_headers(client_for, admin_user):
    response = client_for(admin_user).get(reverse("core:home"))
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_csrf_enforced_on_post(admin_user):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(admin_user)
    response = client.post(reverse("organization:sector_create"), {"name": "Sem token"})
    assert response.status_code == 403
