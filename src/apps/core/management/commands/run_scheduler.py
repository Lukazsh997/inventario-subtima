"""Agendador simples do container `scheduler`: backup diário e reavaliação dos alertas de estoque.

Evita dependências externas (cron, Celery, Redis). Novas tarefas periódicas
(reconciliação de saldos, empréstimos vencidos) serão acrescentadas aqui.
"""

import logging
import signal
import subprocess
import threading
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from config.env import env_str

logger = logging.getLogger("patrimonio.scheduler")
BACKUP_SCRIPT = "/app/scripts/backup.sh"


def parse_time(value: str) -> time:
    try:
        hour, minute = value.strip().split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError) as exc:
        raise CommandError(f"BACKUP_TIME inválido: {value!r} (use HH:MM)") from exc


def next_run(now: datetime, at: time) -> datetime:
    candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


class Command(BaseCommand):
    help = "Executa as tarefas agendadas (backup diário)."

    def handle(self, *args, **options):
        at = parse_time(env_str("BACKUP_TIME", "02:00"))
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        logger.info("Agendador iniciado", extra={"backup_time": at.strftime("%H:%M"), "tz": settings.TIME_ZONE})

        while not stop.is_set():
            now = timezone.localtime()
            target = next_run(now, at)
            if stop.wait(timeout=(target - now).total_seconds()):
                break
            self.run_backup()
            self.run_maintenance()
        logger.info("Agendador encerrado")

    def run_maintenance(self) -> None:
        """Reavalia todos os alertas de estoque (segurança contra qualquer divergência)."""
        from apps.alerts.services import evaluate_consumables

        try:
            evaluate_consumables(None)
            logger.info("Alertas de estoque reavaliados")
        except Exception as exc:  # noqa: BLE001 - o agendador não pode parar por falha de uma tarefa
            logger.error("Falha ao reavaliar alertas", extra={"erro": str(exc)})

    def run_backup(self) -> None:
        try:
            result = subprocess.run(  # noqa: S603 - caminho fixo, sem entrada do usuário
                [BACKUP_SCRIPT, "diario"], capture_output=True, text=True, timeout=3600, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error("Falha ao executar backup", extra={"erro": str(exc)})
            return
        if result.returncode == 0:
            logger.info("Backup concluído", extra={"arquivo": result.stdout.strip().splitlines()[-1:]})
        else:
            logger.error("Backup falhou", extra={"codigo": result.returncode, "saida": result.stderr[-2000:]})
