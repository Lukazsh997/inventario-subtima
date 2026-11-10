"""Verificações usadas pelo endpoint /health/ e pelo HEALTHCHECK do Docker."""

import uuid
from pathlib import Path

from django.conf import settings
from django.db import connection


def check_database() -> tuple[bool, str]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - o health check deve relatar qualquer falha
        return False, exc.__class__.__name__


def check_writable(directory: Path) -> tuple[bool, str]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".health-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, "ok"
    except OSError as exc:
        return False, exc.__class__.__name__


def run_checks() -> dict:
    db_ok, db_detail = check_database()
    media_ok, media_detail = check_writable(Path(settings.MEDIA_ROOT))
    return {
        "status": "ok" if db_ok and media_ok else "error",
        "version": settings.APP_VERSION,
        "checks": {
            "database": db_detail,
            "media": media_detail,
        },
    }
