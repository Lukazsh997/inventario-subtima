"""Filtros e tags de interface reutilizáveis."""

from django import template

register = template.Library()


@register.filter
def add_class(field, css: str):
    """Acrescenta classes CSS ao widget de um campo de formulário."""
    existing = field.field.widget.attrs.get("class", "")
    classes = f"{existing} {css}".strip()
    if field.errors:
        classes += " is-invalid"
    return field.as_widget(attrs={"class": classes})


@register.simple_tag
def status_badge(equipment):
    """Etiqueta colorida com a situação do equipamento."""
    from django.utils.html import format_html

    return format_html(
        '<span class="badge badge-status-{}">{}</span>', equipment.status, equipment.get_status_display()
    )


@register.filter
def get_item(mapping, key):
    """Valor de um dicionário por chave variável (linhas de relatório)."""
    return mapping.get(key, "") if hasattr(mapping, "get") else ""


@register.filter
def signed(value) -> str:
    try:
        return f"{int(value):+d}"
    except (TypeError, ValueError):
        return ""


@register.simple_tag(takes_context=True)
def active_if(context, prefix: str) -> str:
    request = context.get("request")
    if request and request.path.startswith(prefix):
        return "active"
    return ""
