"""Contexto da requisição atual (usuário e IP) disponível para os serviços.

Os serviços de domínio recebem o usuário explicitamente; este contexto serve
apenas para enriquecer a auditoria com o IP de origem sem que cada serviço
precise conhecer o objeto request.
"""

from contextvars import ContextVar

_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def set_client_ip(ip: str | None):
    return _client_ip.set(ip)


def reset_client_ip(token) -> None:
    _client_ip.reset(token)


def get_client_ip() -> str | None:
    return _client_ip.get()
