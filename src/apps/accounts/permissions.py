"""Controle de acesso baseado em papéis (RBAC).

Cada papel concede um conjunto de capacidades. Views e serviços verificam
capacidades, nunca o nome do papel, para que mudar o que um papel pode fazer
exija alterar apenas o mapa abaixo.
"""

from enum import StrEnum
from functools import wraps

from django.core.exceptions import PermissionDenied

from .roles import Role


class Capability(StrEnum):
    ORG_VIEW = "org.view"  # consultar setores, locais e servidores
    RECIPIENTS_MANAGE = "recipients.manage"  # cadastrar e editar servidores recebedores
    SECTORS_MANAGE = "sectors.manage"  # cadastrar e editar setores e locais
    USERS_MANAGE = "users.manage"  # gerenciar usuários do sistema
    AUDIT_VIEW = "audit.view"  # consultar a auditoria
    INVENTORY_VIEW = "inventory.view"  # consultar equipamentos, consumíveis e movimentações
    CATALOG_MANAGE = "catalog.manage"  # cadastrar e editar equipamentos e consumíveis
    CATEGORIES_MANAGE = "categories.manage"  # cadastrar e editar categorias
    INVENTORY_OPERATE = "inventory.operate"  # registrar entradas, saídas, transferências etc.
    STOCK_ADJUST = "stock.adjust"  # ajuste de estoque de consumíveis
    EQUIPMENT_WRITE_OFF = "equipment.write_off"  # baixa definitiva de equipamento
    OPERATION_REVERSE = "operation.reverse"  # estorno de operação


ROLE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    Role.ADMIN: frozenset(Capability),
    Role.TECHNICIAN: frozenset(
        {
            Capability.ORG_VIEW,
            Capability.RECIPIENTS_MANAGE,
            Capability.INVENTORY_VIEW,
            Capability.CATALOG_MANAGE,
            Capability.INVENTORY_OPERATE,
        }
    ),
    Role.VIEWER: frozenset({Capability.ORG_VIEW, Capability.INVENTORY_VIEW}),
}


def capabilities_for(user) -> frozenset[Capability]:
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return frozenset()
    return ROLE_CAPABILITIES.get(getattr(user, "role", None), frozenset())


def has_capability(user, capability: Capability) -> bool:
    return capability in capabilities_for(user)


def ensure_capability(user, capability: Capability) -> None:
    """Usado pelos serviços: a regra vale mesmo que alguém chame o serviço fora da view."""
    if not has_capability(user, capability):
        raise PermissionDenied("Você não tem permissão para esta operação.")


def require_capability(capability: Capability):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            ensure_capability(request.user, capability)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
