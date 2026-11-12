"""Carga inicial opcional dos suprimentos de impressora informados pela equipe.

Fonte: tabela "toners e suprimentos das impressoras" fornecida pela SUBTIMA em
10/11/2026 (docs/referencias/README.md). Cria os materiais com saldo 0 e estoque
mínimo 0; a equipe registra as entradas e ajusta os mínimos depois.

Uso:
  python manage.py carregar_suprimentos --usuario admin --simular
  python manage.py carregar_suprimentos --usuario admin
"""

import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog import services
from apps.catalog.models import Category, Consumable, ItemKind, Unit

DATA = Path(__file__).resolve().parents[2] / "data" / "suprimentos_impressoras.csv"


class Command(BaseCommand):
    help = "Cadastra os toners e tintas da tabela de referência (pula os que já existem)."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Login do administrador responsável pela carga")
        parser.add_argument("--simular", action="store_true", help="Mostra o que seria feito, sem gravar")

    def handle(self, *args, usuario, simular, **options):
        actor = get_user_model().objects.filter(username=usuario, is_active=True).first()
        if actor is None:
            raise CommandError(f"Usuário ativo não encontrado: {usuario}")
        with DATA.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))

        created = skipped = 0
        with transaction.atomic():
            for row in rows:
                name = row["nome"]
                if Consumable.objects.filter(name__iexact=name).exists():
                    skipped += 1
                    continue
                category, _ = Category.objects.get_or_create(name=row["categoria"], kind=ItemKind.CONSUMABLE)
                try:
                    services.save_consumable(
                        actor=actor,
                        consumable=None,
                        data={
                            "category": category,
                            "name": name,
                            "reference": row["referencia"],
                            "unit": Unit.UNIT,
                            "min_stock": 0,
                            "compatibility": row["compativel_com"],
                        },
                    )
                except ValidationError as exc:
                    self.stderr.write(f"{name}: {' '.join(exc.messages)}")
                    continue
                created += 1
                self.stdout.write(f"  + {name}")
            if simular:
                transaction.set_rollback(True)

        verb = "seriam criados" if simular else "criados"
        self.stdout.write(self.style.SUCCESS(f"{created} materiais {verb}; {skipped} já existiam."))
