"""Normalização do que é lido das etiquetas (câmera ou leitor USB).

Etiquetas encontradas no órgão (ver docs/referencias):
- Patrimônio da Prefeitura: Code 128 com o número, ex. "085.057".
- Locadora: Code 128 com o nº de série; QR com link do WhatsApp cujo texto traz
  a série ou o código ACES, ex. "https://wa.me/552138991801?text= ACES0001123".
"""

import re
from urllib.parse import parse_qs, urlparse

_SPACES = re.compile(r"\s+")


def normalize_scan(raw: str) -> str:
    """Extrai o identificador útil de uma leitura: texto de links, sem espaços, em maiúsculas."""
    value = (raw or "").strip()
    if value.lower().startswith(("http://", "https://")):
        query = parse_qs(urlparse(value).query)
        texts = query.get("text") or query.get("t") or []
        value = texts[0] if texts else ""
    return _SPACES.sub("", value).upper()


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_identifier(value: str | None) -> str | None:
    """Forma canônica para gravar série, patrimônio e código da locadora (None se vazio)."""
    value = _SPACES.sub("", (value or "").strip()).upper()
    return value or None
