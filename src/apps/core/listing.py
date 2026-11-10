"""Utilitários de listagem reutilizados por todos os módulos: busca e paginação."""

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q, QuerySet


def apply_search(queryset: QuerySet, term: str, fields: list[str]) -> QuerySet:
    term = (term or "").strip()
    if not term:
        return queryset
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": term})
    return queryset.filter(condition)


def paginate(request, queryset: QuerySet, per_page: int | None = None):
    paginator = Paginator(queryset, per_page or settings.PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()
