"""Verificação da implantação: configuração, banco, volumes, backups e geração de PDF.

Uso:
  python manage.py verificar_implantacao              # relatório legível; código 1 se houver FALHA
  python manage.py verificar_implantacao --json       # instantâneo (contagens + marcador do volume)
  ... --comparar ARQUIVO|-                            # confere se nada se perdeu desde o instantâneo

Nada é gravado no banco. No volume de dados é criado uma única vez o arquivo
.marcador-persistencia, usado para provar que o volume sobrevive à recriação do container.
"""

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.health import check_writable

COUNTED = [
    ("usuarios", "accounts_user"),
    ("setores", "organization_sector"),
    ("servidores", "organization_recipient"),
    ("equipamentos", "catalog_equipment"),
    ("materiais", "catalog_consumable"),
    ("operacoes", "inventory_stockoperation"),
    ("movimentos", "inventory_stockmovement"),
    ("termos", "documents_generateddocument"),
    ("auditoria", "audit_auditlog"),
]
APPEND_ONLY = ["audit_auditlog", "inventory_stockoperation", "inventory_stockmovement", "inventory_operationaccessory"]
MARKER = ".marcador-persistencia"


class Command(BaseCommand):
    help = "Verifica a implantação (configuração, banco, volumes, backups, PDF) e a persistência dos dados."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Imprime o instantâneo em JSON.")
        parser.add_argument("--comparar", metavar="ARQUIVO", help="Instantâneo anterior (use - para stdin).")

    def handle(self, *args, **options):
        if options["json"]:
            self.stdout.write(json.dumps(snapshot(), ensure_ascii=False))
            return
        if options["comparar"]:
            source = options["comparar"]
            raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
            problems = compare(json.loads(raw), snapshot())
            for line in problems:
                self.stdout.write(self.style.ERROR(f"FALHA  {line}"))
            if problems:
                raise CommandError("Dados perdidos desde o instantâneo.")
            self.stdout.write(self.style.SUCCESS("OK     Nenhum dado perdido: banco e volume de arquivos persistiram."))
            return
        failures = 0
        for level, name, detail in run_all():
            style = {"OK": self.style.SUCCESS, "AVISO": self.style.WARNING, "FALHA": self.style.ERROR}[level]
            self.stdout.write(style(f"{level:<6} {name}: {detail}"))
            failures += level == "FALHA"
        if failures:
            raise CommandError(f"{failures} verificação(ões) com falha.")


def marker() -> str:
    path = Path(settings.DATA_DIR) / MARKER
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{uuid.uuid4()} {datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def snapshot() -> dict:
    counts = {}
    with connection.cursor() as cursor:
        for label, table in COUNTED:
            cursor.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 - nomes fixos acima
            counts[label] = cursor.fetchone()[0]
        cursor.execute("SELECT coalesce(max(id), 0) FROM audit_auditlog")
        last_audit = cursor.fetchone()[0]
    return {"versao": settings.APP_VERSION, "contagens": counts, "ultima_auditoria": last_audit, "marcador": marker()}


def compare(before: dict, after: dict) -> list[str]:
    problems = []
    if before.get("marcador") != after.get("marcador"):
        problems.append("o marcador do volume de dados mudou: o volume appdata não persistiu.")
    for label, value in before.get("contagens", {}).items():
        now = after["contagens"].get(label, 0)
        if now < value:
            problems.append(f"{label}: eram {value}, agora {now}.")
    if after.get("ultima_auditoria", 0) < before.get("ultima_auditoria", 0):
        problems.append("o histórico de auditoria regrediu.")
    return problems


def run_all() -> list[tuple[str, str, str]]:
    results = []

    def add(ok, name, detail, warn=False):
        results.append(("OK" if ok else ("AVISO" if warn else "FALHA"), name, detail))

    add(not settings.DEBUG, "DEBUG", "desligado" if not settings.DEBUG else "LIGADO (não use em produção)")
    weak = len(settings.SECRET_KEY) < 40 or "insecure" in settings.SECRET_KEY or "troque" in settings.SECRET_KEY
    add(not weak, "SECRET_KEY", "forte" if not weak else "curta ou valor de exemplo; gere outra")
    add(
        settings.USE_HTTPS,
        "HTTPS",
        "ativo" if settings.USE_HTTPS else "desligado (câmera do celular não funciona)",
        warn=True,
    )
    add("*" not in settings.ALLOWED_HOSTS, "ALLOWED_HOSTS", ", ".join(settings.ALLOWED_HOSTS))

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            version = cursor.fetchone()[0]
            cursor.execute(
                "SELECT c.relname, count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE NOT t.tgisinternal AND c.relname = ANY(%s) GROUP BY c.relname",
                [APPEND_ONLY],
            )
            triggers = dict(cursor.fetchall())
    except Exception as exc:  # noqa: BLE001
        add(False, "Banco de dados", exc.__class__.__name__)
        return results
    add(True, "Banco de dados", f"PostgreSQL {version}")
    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    add(not pending, "Migrações", "todas aplicadas" if not pending else f"{len(pending)} pendente(s)")
    missing = [t for t in APPEND_ONLY if triggers.get(t, 0) < 2]
    add(not missing, "Histórico imutável", "gatilhos ativos" if not missing else f"faltam gatilhos em {missing}")

    for label, directory in (("Volume de dados", Path(settings.MEDIA_ROOT)), ("Pasta de backups", settings.BACKUP_DIR)):
        ok, detail = check_writable(Path(directory))
        add(ok, label, f"{directory} gravável" if ok else f"{directory}: {detail}")
    add(True, "Marcador de persistência", marker())

    backups = sorted(Path(settings.BACKUP_DIR).glob("patrimonio-*.tar"), key=lambda p: p.stat().st_mtime)
    if not backups:
        add(False, "Último backup", "nenhum backup encontrado; rode o backup manual", warn=True)
    else:
        age_h = (time.time() - backups[-1].stat().st_mtime) / 3600
        add(age_h <= 26, "Último backup", f"{backups[-1].name} (há {age_h:.0f} h)", warn=True)

    from apps.documents.models import DocumentTemplate

    kinds = set(DocumentTemplate.objects.filter(active=True).values_list("item_kind", flat=True))
    add(bool(kinds), "Modelos de termo ativos", ", ".join(sorted(kinds)) or "nenhum", warn=True)

    try:
        from apps.core.pdf import html_to_pdf

        started = time.monotonic()
        pdf = html_to_pdf("<p style='font-family: Liberation Sans'>Verificação de PDF</p>")
        add(pdf.startswith(b"%PDF"), "Geração de PDF", f"ok em {time.monotonic() - started:.1f} s")
    except Exception as exc:  # noqa: BLE001
        add(False, "Geração de PDF", exc.__class__.__name__)
    return results
