"""Cadastro de categorias, dados cadastrais de equipamentos e materiais de consumo.

A entrada de um equipamento no inventário (que cria o registro e a operação de
Entrada) fica em apps.inventory.services.register_equipment, porque é uma
movimentação de estoque.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.accounts.permissions import Capability, ensure_capability
from apps.audit import services as audit
from apps.audit.models import AuditAction
from apps.inventory.models import StockBalance

from .identification import digits_only, normalize_identifier, normalize_scan
from .models import Category, Consumable, Equipment, EquipmentStatus, ItemKind

CATEGORY_FIELDS = ["name", "kind", "active"]
EQUIPMENT_FIELDS = [
    "category",
    "name",
    "manufacturer",
    "model",
    "ownership",
    "lessor",
    "serial_number",
    "asset_tag",
    "lessor_code",
    "condition",
    "acquisition_date",
    "notes",
]
CONSUMABLE_FIELDS = ["category", "name", "reference", "unit", "min_stock", "compatibility", "active"]


def _save(instance, message: str) -> None:
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise ValidationError(message) from exc


# --- Busca por código lido -------------------------------------------------------------


def find_equipment_by_code(raw: str):
    """Equipamentos cujo nº de série, patrimônio ou código da locadora corresponde à leitura."""
    code = normalize_scan(raw)
    if not code:
        return Equipment.objects.none()
    condition = Q(serial_number=code) | Q(lessor_code=code) | Q(asset_tag=code)
    digits = digits_only(code)
    if digits:
        condition |= Q(asset_tag_digits=digits)
    return Equipment.objects.filter(condition).select_related("category", "current_sector")


def identifier_conflicts(*, serial_number=None, asset_tag=None, lessor_code=None, exclude_pk=None) -> list[str]:
    """Mensagens de conflito para identificadores já usados por outro equipamento."""
    messages = []
    queryset = Equipment.objects.all()
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    if serial_number and (other := queryset.filter(serial_number=serial_number).first()):
        messages.append(f"O nº de série {serial_number} já pertence a: {other}.")
    if asset_tag:
        key = digits_only(asset_tag) or asset_tag
        if other := queryset.filter(asset_tag_digits=key).first():
            messages.append(f"O patrimônio {asset_tag} já pertence a: {other}.")
    if lessor_code and (other := queryset.filter(lessor_code=lessor_code).first()):
        messages.append(f"O código da locadora {lessor_code} já pertence a: {other}.")
    return messages


def apply_equipment_fields(equipment: Equipment, data: dict) -> None:
    """Copia os campos cadastrais normalizados e valida identificadores (sem salvar)."""
    category = data["category"]
    if category.kind != ItemKind.EQUIPMENT:
        raise ValidationError("A categoria escolhida não é de equipamentos.")
    equipment.category = category
    equipment.name = " ".join(data["name"].split())
    equipment.manufacturer = data.get("manufacturer", "").strip()
    equipment.model = data.get("model", "").strip()
    equipment.ownership = data["ownership"]
    equipment.lessor = data.get("lessor", "").strip()
    # Os campos podem receber a leitura bruta da etiqueta (inclusive o link do QR da locadora).
    equipment.serial_number = normalize_scan(data.get("serial_number") or "") or None
    equipment.asset_tag = normalize_scan(data.get("asset_tag") or "") or None
    equipment.asset_tag_digits = (
        (digits_only(equipment.asset_tag) or equipment.asset_tag.upper()) if equipment.asset_tag else None
    )
    equipment.lessor_code = normalize_scan(data.get("lessor_code") or "") or None
    equipment.condition = data["condition"]
    equipment.acquisition_date = data.get("acquisition_date")
    equipment.notes = data.get("notes", "").strip()
    for field in ("serial_number", "asset_tag", "lessor_code"):
        value = getattr(equipment, field)
        limit = Equipment._meta.get_field(field).max_length
        if value and len(value) > limit:
            label = Equipment._meta.get_field(field).verbose_name
            raise ValidationError(f"O {label} lido tem mais de {limit} caracteres; confira a leitura.")
    if not (equipment.serial_number or equipment.asset_tag or equipment.lessor_code):
        raise ValidationError("Informe pelo menos um identificador: nº de série, patrimônio ou código da locadora.")
    conflicts = identifier_conflicts(
        serial_number=equipment.serial_number,
        asset_tag=equipment.asset_tag,
        lessor_code=equipment.lessor_code,
        exclude_pk=equipment.pk,
    )
    if conflicts:
        raise ValidationError(conflicts)


@transaction.atomic
def update_equipment(*, actor, equipment: Equipment, data: dict) -> Equipment:
    """Corrige dados cadastrais. Situação, setor e responsável só mudam por movimentação."""
    ensure_capability(actor, Capability.CATALOG_MANAGE)
    equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
    if equipment.status == EquipmentStatus.WRITTEN_OFF:
        raise ValidationError("Equipamento baixado não pode ser alterado.")
    before = audit.snapshot(equipment, EQUIPMENT_FIELDS)
    apply_equipment_fields(equipment, data)
    _save(equipment, "Identificador já cadastrado em outro equipamento.")
    if changes := audit.diff(before, audit.snapshot(equipment, EQUIPMENT_FIELDS)):
        audit.record(AuditAction.UPDATE, user=actor, instance=equipment, changes=changes)
    return equipment


# --- Categorias ------------------------------------------------------------------------


@transaction.atomic
def save_category(*, actor, category: Category | None, name: str, kind: str) -> Category:
    ensure_capability(actor, Capability.CATEGORIES_MANAGE)
    creating = category is None
    category = category or Category()
    if not creating and kind != category.kind and (category.equipment.exists() or category.consumables.exists()):
        raise ValidationError("Não é possível mudar o tipo de uma categoria que já tem itens.")
    before = {} if creating else audit.snapshot(category, CATEGORY_FIELDS)
    category.name = " ".join(name.split())
    category.kind = kind
    _save(category, "Já existe uma categoria com este nome.")
    changes = audit.diff(before, audit.snapshot(category, CATEGORY_FIELDS))
    if creating or changes:
        audit.record(
            AuditAction.CREATE if creating else AuditAction.UPDATE, user=actor, instance=category, changes=changes
        )
    return category


@transaction.atomic
def set_category_active(*, actor, category: Category, active: bool) -> Category:
    ensure_capability(actor, Capability.CATEGORIES_MANAGE)
    if category.active != active:
        category.active = active
        category.save(update_fields=["active", "updated_at"])
        audit.record(AuditAction.REACTIVATE if active else AuditAction.DEACTIVATE, user=actor, instance=category)
    return category


# --- Materiais de consumo --------------------------------------------------------------


@transaction.atomic
def save_consumable(*, actor, consumable: Consumable | None, data: dict) -> Consumable:
    ensure_capability(actor, Capability.CATALOG_MANAGE)
    if data["category"].kind != ItemKind.CONSUMABLE:
        raise ValidationError("A categoria escolhida não é de materiais de consumo.")
    creating = consumable is None
    consumable = consumable or Consumable()
    before = {} if creating else audit.snapshot(consumable, CONSUMABLE_FIELDS)
    consumable.category = data["category"]
    consumable.name = " ".join(data["name"].split())
    consumable.reference = normalize_identifier(data.get("reference"))
    consumable.unit = data["unit"]
    consumable.min_stock = data.get("min_stock") or 0
    consumable.compatibility = data.get("compatibility", "").strip()
    _save(consumable, "Já existe um material com este nome ou código.")
    if creating:
        StockBalance.objects.create(consumable=consumable, quantity=0)
    changes = audit.diff(before, audit.snapshot(consumable, CONSUMABLE_FIELDS))
    if creating or changes:
        audit.record(
            AuditAction.CREATE if creating else AuditAction.UPDATE, user=actor, instance=consumable, changes=changes
        )
    return consumable


@transaction.atomic
def set_consumable_active(*, actor, consumable: Consumable, active: bool) -> Consumable:
    ensure_capability(actor, Capability.CATALOG_MANAGE)
    if consumable.active != active:
        consumable.active = active
        consumable.save(update_fields=["active", "updated_at"])
        audit.record(AuditAction.REACTIVATE if active else AuditAction.DEACTIVATE, user=actor, instance=consumable)
    return consumable
