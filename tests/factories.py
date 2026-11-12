"""Criação de objetos de teste por meio dos próprios serviços (as mesmas regras da aplicação)."""

from apps.catalog import services as catalog
from apps.catalog.models import Category, Condition, ItemKind, Ownership, Unit
from apps.inventory import services as inventory
from apps.inventory.models import OperationType
from apps.organization.models import Recipient, Sector


def sector(name="Secretaria Municipal de Urbanismo", acronym=""):
    return Sector.objects.create(name=name, acronym=acronym)


def recipient(sector_obj, name="Maria Souza", registration=None):
    return Recipient.objects.create(full_name=name, sector=sector_obj, registration=registration)


def equipment_category():
    return Category.objects.get_or_create(name="Computadores desktop", kind=ItemKind.EQUIPMENT)[0]


def consumable_category():
    return Category.objects.get_or_create(name="Toners de impressora", kind=ItemKind.CONSUMABLE)[0]


def equipment_data(**overrides):
    data = {
        "category": equipment_category(),
        "name": "Desktop Dell OptiPlex",
        "manufacturer": "Dell",
        "model": "OptiPlex 7010",
        "ownership": Ownership.OWNED,
        "lessor": "",
        "serial_number": "",
        "asset_tag": "",
        "lessor_code": "",
        "condition": Condition.GOOD,
        "acquisition_date": None,
        "notes": "",
    }
    data.update(overrides)
    return data


def equipment(actor, **overrides):
    overrides.setdefault("serial_number", f"SN{equipment.counter}")
    equipment.counter += 1
    return inventory.register_equipment(actor=actor, data=equipment_data(**overrides))


equipment.counter = 1


def consumable(actor, name="Toner HP 151A", reference=None, min_stock=0, initial=0):
    item = catalog.save_consumable(
        actor=actor,
        consumable=None,
        data={
            "category": consumable_category(),
            "name": name,
            "reference": reference,
            "unit": Unit.UNIT,
            "min_stock": min_stock,
            "compatibility": "",
        },
    )
    if initial:
        inventory.move_consumables(
            actor=actor, op_type=OperationType.ENTRY, lines=[(item, initial)], data=inventory.OperationData()
        )
    return item
