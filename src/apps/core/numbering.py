"""Numeração sequencial anual, segura sob concorrência (um único comando atômico no banco)."""

from django.db import connection
from django.utils import timezone

from .models import NumberSequence

_SQL = f"""
INSERT INTO {NumberSequence._meta.db_table} (prefix, year, last_value)
VALUES (%s, %s, 1)
ON CONFLICT (prefix, year) DO UPDATE SET last_value = {NumberSequence._meta.db_table}.last_value + 1
RETURNING last_value
"""  # noqa: S608 - apenas o nome da tabela é interpolado; valores vão como parâmetros


def next_number(prefix: str, *, width: int = 6) -> str:
    """Retorna o próximo número do ano corrente, ex.: next_number("OP") -> "OP-2026-000001".

    Deve ser chamada dentro da transação que grava o registro numerado: se ela
    for desfeita, o número volta a ficar disponível.
    """
    year = timezone.localdate().year
    with connection.cursor() as cursor:
        cursor.execute(_SQL, [prefix, year])
        value = cursor.fetchone()[0]
    return f"{prefix}-{year}-{value:0{width}d}"
