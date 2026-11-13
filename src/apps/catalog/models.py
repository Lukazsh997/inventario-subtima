from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel


class ItemKind(models.TextChoices):
    EQUIPMENT = "equipamento", "Equipamento (controle individual)"
    CONSUMABLE = "consumivel", "Material de consumo (controle por quantidade)"


class Category(TimeStampedModel):
    name = models.CharField("nome", max_length=100)
    kind = models.CharField("tipo", max_length=12, choices=ItemKind.choices)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        constraints = [models.UniqueConstraint("kind", Lower("name"), name="category_unique_name_per_kind_ci")]

    def __str__(self) -> str:
        return self.name


class EquipmentStatus(models.TextChoices):
    AVAILABLE = "disponivel", "Disponível"
    IN_USE = "em_uso", "Em uso"
    ON_LOAN = "emprestado", "Emprestado"
    MAINTENANCE = "manutencao", "Em manutenção"
    WRITTEN_OFF = "baixado", "Baixado"


class Ownership(models.TextChoices):
    OWNED = "proprio", "Próprio (patrimônio da Prefeitura)"
    LEASED = "locado", "Locado"


class Condition(models.TextChoices):
    NEW = "novo", "Novo"
    GOOD = "bom", "Bom"
    FAIR = "regular", "Regular"
    POOR = "ruim", "Ruim"
    UNUSABLE = "inservivel", "Inservível"


class Equipment(TimeStampedModel):
    """Equipamento com controle individual.

    Os campos de situação (status, setor, local e responsável atuais) são
    alterados somente pelos serviços de movimentação (apps.inventory.services).
    """

    category = models.ForeignKey(
        Category,
        verbose_name="categoria",
        on_delete=models.PROTECT,
        related_name="equipment",
        limit_choices_to={"kind": ItemKind.EQUIPMENT},
    )
    name = models.CharField("nome", max_length=150, help_text="Ex.: Desktop Dell OptiPlex 7010")
    manufacturer = models.CharField("fabricante", max_length=80, blank=True)
    model = models.CharField("modelo", max_length=120, blank=True)
    ownership = models.CharField("propriedade", max_length=8, choices=Ownership.choices, default=Ownership.OWNED)
    lessor = models.CharField("locadora", max_length=120, blank=True)
    serial_number = models.CharField("nº de série", max_length=80, null=True, blank=True)
    asset_tag = models.CharField("patrimônio", max_length=40, null=True, blank=True)
    asset_tag_digits = models.CharField(max_length=40, null=True, blank=True, editable=False)
    lessor_code = models.CharField(
        "código da locadora", max_length=40, null=True, blank=True, help_text="Ex.: ACES0001123"
    )
    condition = models.CharField(
        "estado de conservação", max_length=12, choices=Condition.choices, default=Condition.GOOD
    )
    acquisition_date = models.DateField("data de aquisição", null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    status = models.CharField(
        "situação",
        max_length=12,
        choices=EquipmentStatus.choices,
        default=EquipmentStatus.AVAILABLE,
        editable=False,
        db_index=True,
    )
    current_sector = models.ForeignKey(
        "organization.Sector",
        verbose_name="setor atual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="equipment",
    )
    current_location = models.ForeignKey(
        "organization.Location",
        verbose_name="local atual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="equipment",
    )
    current_recipient = models.ForeignKey(
        "organization.Recipient",
        verbose_name="responsável atual",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="equipment",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False, related_name="+")

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "equipamento"
        verbose_name_plural = "equipamentos"
        constraints = [
            models.UniqueConstraint(
                "serial_number", name="equipment_serial_unique", condition=Q(serial_number__isnull=False)
            ),
            models.UniqueConstraint(
                "asset_tag_digits", name="equipment_asset_tag_unique", condition=Q(asset_tag_digits__isnull=False)
            ),
            models.UniqueConstraint(
                "lessor_code", name="equipment_lessor_code_unique", condition=Q(lessor_code__isnull=False)
            ),
            models.CheckConstraint(
                condition=Q(serial_number__isnull=False) | Q(asset_tag__isnull=False) | Q(lessor_code__isnull=False),
                name="equipment_has_identifier",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.main_identifier})"

    @property
    def main_identifier(self) -> str:
        if self.asset_tag:
            return f"Patr. {self.asset_tag}"
        if self.lessor_code:
            return self.lessor_code
        return f"S/N {self.serial_number}"

    @property
    def is_leased(self) -> bool:
        return self.ownership == Ownership.LEASED

    @property
    def location_label(self) -> str:
        if self.status == EquipmentStatus.WRITTEN_OFF:
            return "Baixado"
        if self.current_sector is None:
            return "Estoque da TI"
        return str(self.current_sector)


class Unit(models.TextChoices):
    UNIT = "un", "unidade"
    BOX = "cx", "caixa"
    REAM = "resma", "resma"
    PACK = "pct", "pacote"
    METER = "m", "metro"
    ROLL = "rolo", "rolo"


class Consumable(TimeStampedModel):
    """Material de consumo controlado por quantidade (saldo em apps.inventory.StockBalance)."""

    category = models.ForeignKey(
        Category,
        verbose_name="categoria",
        on_delete=models.PROTECT,
        related_name="consumables",
        limit_choices_to={"kind": ItemKind.CONSUMABLE},
    )
    name = models.CharField("nome", max_length=150, help_text="Ex.: Toner HP 151A")
    reference = models.CharField(
        "código/referência", max_length=60, null=True, blank=True, help_text="Código do fabricante, ex.: W1510A"
    )
    unit = models.CharField("unidade", max_length=6, choices=Unit.choices, default=Unit.UNIT)
    min_stock = models.PositiveIntegerField("estoque mínimo", default=0)
    compatibility = models.CharField(
        "compatível com", max_length=255, blank=True, help_text="Ex.: HP LaserJet Pro MFP M4103fdw"
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "material de consumo"
        verbose_name_plural = "materiais de consumo"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="consumable_name_unique_ci"),
            models.UniqueConstraint(
                "reference", name="consumable_reference_unique", condition=Q(reference__isnull=False)
            ),
        ]

    def __str__(self) -> str:
        return self.name
