"""Eventos de domínio síncronos.

Um módulo publica um fato (ex.: "saldos de consumíveis mudaram") sem conhecer
quem reage a ele. Os assinantes rodam na mesma transação de quem publicou:
se o assinante falhar, a operação inteira é desfeita, e nada fica inconsistente.
"""

from collections import defaultdict
from collections.abc import Callable

CONSUMABLES_CHANGED = "consumables_changed"  # payload: consumable_ids: list[int]
OPERATION_REVERSED = "operation_reversed"  # payload: operation, reversal, actor

_subscribers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    if handler not in _subscribers[event]:
        _subscribers[event].append(handler)


def publish(event: str, **payload) -> None:
    for handler in list(_subscribers[event]):
        handler(**payload)
