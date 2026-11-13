"""Preenchimento dos modelos de termo e geração do PDF.

Segurança: os modelos são editáveis pelo administrador. Por isso são renderizados
por um motor de templates isolado (sem {% load %} de bibliotecas, sem {% include %})
e recebem SOMENTE dados simples (textos e números), nunca objetos do banco: um
modelo não consegue alcançar senhas, sessões ou outras tabelas.
"""

import base64
from datetime import date
from pathlib import Path

from django.conf import settings
from django.template import Context, Engine, TemplateSyntaxError
from django.utils import timezone

from .models import DocumentAsset, DocumentTemplate

MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]

_ENGINE = Engine(autoescape=True, libraries={}, loaders=[], debug=False, string_if_invalid="")

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_ASSETS = {
    "brasao": ("Brasão de Duque de Caxias", ASSETS_DIR / "brasao.png"),
    "logo_dc": ("Logotipo Prefeitura de Duque de Caxias", ASSETS_DIR / "logo-dc.png"),
}

PAGE_CSS = """
@page { size: A4; margin: 15mm 20mm 18mm 20mm; }
html { font-family: Arial, "Liberation Sans", sans-serif; font-size: 11pt; color: #000; }
.doc-control { position: fixed; bottom: -12mm; right: 0; font-family: Arial, "Liberation Sans", sans-serif;
  font-size: 6.5pt; color: #777; }
"""


def long_date(value: date) -> str:
    return f"{value.day:02d} de {MONTHS[value.month - 1]} de {value.year}"


def secretariat_of(sector) -> str:
    """Secretaria a que o setor pertence, para frases como "da Secretaria Municipal de Urbanismo".

    Sobe a hierarquia a partir do próprio setor e usa o primeiro nível cujo nome começa
    com "Secretaria". Se não houver, usa o nível logo abaixo do topo, ignorando um topo
    que represente a Prefeitura inteira; em último caso, o próprio setor. Assim o termo
    nunca mostra "Prefeitura Municipal de ..." no lugar da secretaria ou do setor.
    """
    chain, node, seen = [], sector, set()
    while node is not None and node.pk not in seen:
        chain.append(node)
        seen.add(node.pk)
        node = node.parent
    for item in chain:
        if item.name.strip().lower().startswith("secretaria"):
            return item.name
    top = chain[-1]
    if top.name.strip().lower().startswith("prefeitura"):
        return chain[-2].name if len(chain) > 1 else sector.name
    return top.name


def _sector_parts(sector) -> dict:
    if sector is None:
        return {"nome": "", "sigla": "", "rotulo": "", "secretaria": ""}
    label = f"{sector.name} / {sector.acronym}" if sector.acronym else sector.name
    return {"nome": sector.name, "sigla": sector.acronym, "rotulo": label, "secretaria": secretariat_of(sector)}


def _person(recipient) -> dict:
    if recipient is None:
        return {"nome": "", "matricula": "", "cargo": "", "setor": ""}
    return {
        "nome": recipient.full_name,
        "matricula": recipient.registration or "",
        "cargo": recipient.job_title,
        "setor": recipient.sector.name,
    }


def build_context(operation, *, number: str, issued_on: date | None = None) -> dict:
    """Dados do termo, apenas tipos simples. Também é guardado junto do termo emitido."""
    issued_on = issued_on or timezone.localdate()
    items = []
    for m in operation.movements.select_related("equipment", "equipment__category", "consumable").order_by("id"):
        if m.equipment_id:
            e = m.equipment
            items.append(
                {
                    "descricao": e.name,
                    "categoria": e.category.name,
                    "estado": e.get_condition_display(),
                    "fabricante": e.manufacturer,
                    "modelo": e.model,
                    "marca_modelo": " ".join(p for p in [e.manufacturer, e.model] if p),
                    "patrimonio": e.asset_tag or "",
                    "serie": e.serial_number or "",
                    "codigo_locadora": e.lessor_code or "",
                    "patrimonio_serie": e.asset_tag or e.serial_number or e.lessor_code or "",
                    "locado": e.is_leased,
                    "quantidade": 1,
                    "unidade": "unidade",
                }
            )
        else:
            c = m.consumable
            quantity = abs(m.quantity)
            unit = c.get_unit_display()
            items.append(
                {
                    "descricao": c.name,
                    "material": c.name,
                    "codigo": c.reference or "",
                    "quantidade": quantity,
                    "unidade": unit if quantity == 1 else _plural(unit),
                    "categoria": c.category.name,
                }
            )
    return {
        "termo": {
            "numero": number,
            "data": issued_on.strftime("%d/%m/%Y"),
            "data_extenso": long_date(issued_on),
            "dia": f"{issued_on.day:02d}",
            "mes": MONTHS[issued_on.month - 1],
            "ano": str(issued_on.year),
            "cidade": settings.DOC_CITY,
        },
        "operacao": {
            "numero": operation.number,
            "tipo": operation.get_type_display(),
            "data": timezone.localtime(operation.performed_at).strftime("%d/%m/%Y %H:%M"),
            "data_extenso": long_date(timezone.localtime(operation.performed_at).date()),
            "justificativa": operation.justification,
            "observacoes": operation.notes,
            "devolucao_prevista": operation.due_date.strftime("%d/%m/%Y") if operation.due_date else "",
            "assistencia": operation.third_party,
        },
        "origem": _sector_parts(operation.origin_sector),
        "destino": _sector_parts(operation.destination_sector),
        "local": operation.destination_location.name if operation.destination_location else "",
        "recebedor": _person(operation.recipient),
        "responsavel": {"nome": operation.performed_by.full_name, "login": operation.performed_by.username},
        "itens": items,
        "acessorios": [{"descricao": a.description, "quantidade": a.quantity} for a in operation.accessories.all()],
        "orgao": {"nome": settings.ORG_NAME, "unidade": settings.ORG_UNIT_NAME},
    }


def _plural(unit: str) -> str:
    return {
        "unidade": "unidades",
        "caixa": "caixas",
        "resma": "resmas",
        "pacote": "pacotes",
        "metro": "metros",
        "rolo": "rolos",
    }.get(unit, unit)


def asset_data_uris() -> dict:
    uris = {}
    for asset in DocumentAsset.objects.all():
        encoded = base64.b64encode(bytes(asset.content)).decode()
        uris[asset.key] = f"data:{asset.content_type};base64,{encoded}"
    return uris


def check_template(css: str, body: str) -> None:
    """Valida a sintaxe antes de salvar um modelo (levanta TemplateSyntaxError)."""
    _ENGINE.from_string(css)
    _ENGINE.from_string(body)


def render_html(template: DocumentTemplate, data: dict) -> str:
    context = Context({**data, "imagens": asset_data_uris()})
    css = _ENGINE.from_string(template.css).render(context)
    body = _ENGINE.from_string(template.body).render(context)
    control = (
        f"Termo {data['termo']['numero']} · Operação {data['operacao']['numero']} · "
        f"emitido pelo Sistema de Patrimônio TI em {data['termo']['data']}"
    )
    return (
        f'<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><style>{PAGE_CSS}{css}</style>'
        f'</head><body>{body}<div class="doc-control">{_escape(control)}</div></body></html>'
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_pdf(template: DocumentTemplate, data: dict) -> bytes:
    from apps.core.pdf import html_to_pdf

    return html_to_pdf(render_html(template, data))


__all__ = ["TemplateSyntaxError", "build_context", "check_template", "render_html", "render_pdf"]
