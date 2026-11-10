"""Leitura tipada de variáveis de ambiente.

Toda configuração do sistema vem do ambiente (12-factor), para que a mesma
imagem Docker sirva em qualquer servidor apenas trocando o arquivo .env.
"""

import os

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on", "sim"}
_FALSE = {"0", "false", "no", "off", "nao", "não", ""}


def env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        if required:
            raise ImproperlyConfigured(f"Variável de ambiente obrigatória ausente: {name}")
        return default if default is not None else ""
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ImproperlyConfigured(f"Valor inválido para {name}: use true ou false")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Valor inválido para {name}: esperado número inteiro") from exc


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]
