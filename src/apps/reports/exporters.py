"""Exportação dos relatórios em CSV (abre direto no Excel/LibreOffice) e PDF A4."""

import csv
import io

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from .base import ReportResult


def to_csv(result: ReportResult) -> bytes:
    """CSV com BOM UTF-8 e separador ";" — o formato que o Excel em português abre sem assistente."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    for label, value in result.header:
        writer.writerow([label, value])
    if result.header:
        writer.writerow([])
    writer.writerow([c.label for c in result.columns])
    for row in result.rows:
        writer.writerow([_csv_safe(row.get(c.key, "")) for c in result.columns])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _csv_safe(value):
    """Evita que uma célula seja interpretada como fórmula ao abrir no Excel (CSV injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def to_pdf(report, result: ReportResult, *, filters: list[str], user) -> bytes:
    from apps.core.pdf import html_to_pdf

    html = render_to_string(
        "reports/pdf.html",
        {
            "report": report,
            "result": result,
            "filters": filters,
            "user": user,
            "generated_at": timezone.localtime(),
            "ORG_NAME": settings.ORG_NAME,
            "ORG_UNIT_NAME": settings.ORG_UNIT_NAME,
        },
    )
    return html_to_pdf(html)
