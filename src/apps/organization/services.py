"""Casos de uso de setores, locais e servidores recebedores (com auditoria)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.permissions import Capability, ensure_capability
from apps.audit import services as audit
from apps.audit.models import AuditAction

from .models import Location, Recipient, Sector

SECTOR_FIELDS = ["name", "acronym", "parent", "active"]
LOCATION_FIELDS = ["name", "sector", "active"]
RECIPIENT_FIELDS = ["full_name", "registration", "job_title", "sector", "phone", "active"]


def _save_unique(instance, message: str) -> None:
    """Salva convertendo violação de unicidade do banco em erro de validação legível."""
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise ValidationError(message) from exc


def _check_parent(sector: Sector, parent: Sector | None) -> None:
    if parent is None or sector.pk is None:
        return
    if parent.pk == sector.pk or sector.pk in {a.pk for a in parent.ancestors()}:
        raise ValidationError("Um setor não pode ficar vinculado a ele mesmo nem a um setor subordinado a ele.")


def _set_active(actor, instance, active: bool, capability: Capability):
    ensure_capability(actor, capability)
    if instance.active == active:
        return instance
    instance.active = active
    instance.save(update_fields=["active", "updated_at"])
    audit.record(AuditAction.REACTIVATE if active else AuditAction.DEACTIVATE, user=actor, instance=instance)
    return instance


# --- Setores ---------------------------------------------------------------------------


@transaction.atomic
def save_sector(*, actor, sector: Sector | None, name: str, acronym: str = "", parent: Sector | None = None) -> Sector:
    ensure_capability(actor, Capability.SECTORS_MANAGE)
    creating = sector is None
    sector = sector or Sector()
    before = {} if creating else audit.snapshot(sector, SECTOR_FIELDS)
    _check_parent(sector, parent)
    sector.name = " ".join(name.split())
    sector.acronym = acronym.strip().upper()
    sector.parent = parent
    _save_unique(sector, "Já existe um setor com este nome.")
    after = audit.snapshot(sector, SECTOR_FIELDS)
    if creating:
        audit.record(AuditAction.CREATE, user=actor, instance=sector, changes=audit.diff({}, after))
    elif changes := audit.diff(before, after):
        audit.record(AuditAction.UPDATE, user=actor, instance=sector, changes=changes)
    return sector


@transaction.atomic
def set_sector_active(*, actor, sector: Sector, active: bool) -> Sector:
    if not active and sector.children.filter(active=True).exists():
        raise ValidationError("Desative primeiro os setores vinculados a este.")
    return _set_active(actor, sector, active, Capability.SECTORS_MANAGE)


# --- Locais ----------------------------------------------------------------------------


@transaction.atomic
def save_location(*, actor, location: Location | None, sector: Sector, name: str) -> Location:
    ensure_capability(actor, Capability.SECTORS_MANAGE)
    creating = location is None
    location = location or Location()
    before = {} if creating else audit.snapshot(location, LOCATION_FIELDS)
    location.sector = sector
    location.name = " ".join(name.split())
    _save_unique(location, "Este setor já tem um local com esta descrição.")
    after = audit.snapshot(location, LOCATION_FIELDS)
    if creating:
        audit.record(AuditAction.CREATE, user=actor, instance=location, changes=audit.diff({}, after))
    elif changes := audit.diff(before, after):
        audit.record(AuditAction.UPDATE, user=actor, instance=location, changes=changes)
    return location


@transaction.atomic
def set_location_active(*, actor, location: Location, active: bool) -> Location:
    return _set_active(actor, location, active, Capability.SECTORS_MANAGE)


# --- Servidores recebedores ------------------------------------------------------------


@transaction.atomic
def save_recipient(
    *,
    actor,
    recipient: Recipient | None,
    full_name: str,
    sector: Sector,
    registration: str = "",
    job_title: str = "",
    phone: str = "",
) -> Recipient:
    ensure_capability(actor, Capability.RECIPIENTS_MANAGE)
    creating = recipient is None
    recipient = recipient or Recipient()
    before = {} if creating else audit.snapshot(recipient, RECIPIENT_FIELDS)
    recipient.full_name = " ".join(full_name.split())
    recipient.registration = registration.strip() or None
    recipient.job_title = job_title.strip()
    recipient.phone = phone.strip()
    recipient.sector = sector
    _save_unique(recipient, "Já existe um servidor com esta matrícula.")
    after = audit.snapshot(recipient, RECIPIENT_FIELDS)
    if creating:
        audit.record(AuditAction.CREATE, user=actor, instance=recipient, changes=audit.diff({}, after))
    elif changes := audit.diff(before, after):
        audit.record(AuditAction.UPDATE, user=actor, instance=recipient, changes=changes)
    return recipient


@transaction.atomic
def set_recipient_active(*, actor, recipient: Recipient, active: bool) -> Recipient:
    return _set_active(actor, recipient, active, Capability.RECIPIENTS_MANAGE)
