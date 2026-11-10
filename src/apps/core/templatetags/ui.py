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


@register.simple_tag(takes_context=True)
def active_if(context, prefix: str) -> str:
    request = context.get("request")
    if request and request.path.startswith(prefix):
        return "active"
    return ""
