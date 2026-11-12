"""Formulários das operações. Os itens (equipamentos e linhas de material) chegam como
listas no POST e são validados aqui; as regras de negócio ficam nos serviços."""

from django import forms
from django.core.exceptions import ValidationError

from apps.catalog.models import Consumable, Equipment
from apps.organization import services as org_services
from apps.organization.models import Location, Recipient, Sector

from .models import CONSUMABLE_OPERATIONS, EQUIPMENT_OPERATIONS, OperationType
from .services import OperationData


class DestinationForm(forms.Form):
    """Setor de destino, local e servidor recebedor, com cadastro rápido de servidor."""

    destination_sector = forms.ModelChoiceField(
        label="Setor de destino", queryset=Sector.objects.filter(active=True), required=False
    )
    destination_location = forms.ModelChoiceField(
        label="Local", queryset=Location.objects.filter(active=True), required=False
    )
    recipient = forms.ModelChoiceField(
        label="Servidor que recebe", queryset=Recipient.objects.filter(active=True), required=False
    )
    new_recipient_name = forms.CharField(label="Nome do novo servidor", max_length=200, required=False)
    new_recipient_registration = forms.CharField(label="Matrícula", max_length=30, required=False)

    def resolve_recipient(self, actor) -> Recipient | None:
        """Retorna o servidor escolhido ou cadastra o novo informado (chamar dentro de uma transação)."""
        data = self.cleaned_data
        if data.get("recipient"):
            return data["recipient"]
        name = (data.get("new_recipient_name") or "").strip()
        if not name:
            return None
        sector = data.get("destination_sector")
        if sector is None:
            raise ValidationError("Escolha o setor antes de cadastrar um novo servidor.")
        registration = (data.get("new_recipient_registration") or "").strip()
        if registration and (existing := Recipient.objects.filter(registration=registration).first()):
            return existing
        return org_services.save_recipient(
            actor=actor, recipient=None, full_name=name, sector=sector, registration=registration
        )


class InitialPlacementForm(DestinationForm):
    """Na entrada: equipamento que já está em uso em um setor (inventário inicial)."""

    in_use = forms.BooleanField(
        label="Este equipamento já está em uso em um setor (inventário inicial)", required=False
    )

    def operation_data(self, actor) -> OperationData | None:
        if not self.cleaned_data.get("in_use"):
            return None
        return OperationData(
            destination_sector=self.cleaned_data.get("destination_sector"),
            destination_location=self.cleaned_data.get("destination_location"),
            recipient=self.resolve_recipient(actor),
            notes="Inventário inicial: equipamento já estava em uso",
        )


class OperationForm(DestinationForm):
    origin_sector = forms.ModelChoiceField(
        label="Setor que devolve", queryset=Sector.objects.filter(active=True), required=False
    )
    due_date = forms.DateField(
        label="Devolução prevista", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    third_party = forms.CharField(label="Assistência técnica / fornecedor", max_length=150, required=False)
    justification = forms.CharField(label="Justificativa", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    notes = forms.CharField(label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    generate_document = forms.BooleanField(label="Gerar o termo em PDF ao registrar", required=False, initial=True)

    allowed_types: list = []

    def __init__(self, *args, op_type: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.op_type = op_type

    def clean(self):
        data = super().clean()
        if self.op_type not in self.allowed_types:
            raise ValidationError("Tipo de operação inválido.")
        return data

    def operation_data(self, actor, *, accessories=None) -> OperationData:
        data = self.cleaned_data
        return OperationData(
            destination_sector=data.get("destination_sector"),
            destination_location=data.get("destination_location"),
            recipient=self.resolve_recipient(actor),
            origin_sector=data.get("origin_sector"),
            due_date=data.get("due_date"),
            third_party=data.get("third_party", ""),
            justification=data.get("justification", ""),
            notes=data.get("notes", ""),
            accessories=accessories,
        )


class EquipmentOperationForm(OperationForm):
    allowed_types = EQUIPMENT_OPERATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.equipment_ids: list[int] = []
        self.accessories: list[tuple[str, int]] = []

    def clean(self):
        data = super().clean()
        raw_ids = self.data.getlist("equipment_ids") if hasattr(self.data, "getlist") else []
        self.equipment_ids = sorted({int(v) for v in raw_ids if str(v).isdigit()})
        if not self.equipment_ids:
            raise ValidationError("Leia ou selecione pelo menos um equipamento.")
        descriptions = self.data.getlist("accessory_description") if hasattr(self.data, "getlist") else []
        quantities = self.data.getlist("accessory_quantity") if hasattr(self.data, "getlist") else []
        for index, description in enumerate(descriptions):
            if description.strip():
                quantity = quantities[index] if index < len(quantities) else "1"
                self.accessories.append((description.strip()[:150], int(quantity) if quantity.isdigit() else 1))
        return data

    def selected_equipment(self):
        ids = self.equipment_ids or [int(v) for v in self.data.getlist("equipment_ids") if v.isdigit()]
        return list(Equipment.objects.filter(pk__in=ids).select_related("current_sector", "current_recipient"))


class ConsumableOperationForm(OperationForm):
    allowed_types = CONSUMABLE_OPERATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lines: list[tuple[Consumable, int]] = []

    def raw_lines(self) -> list[dict]:
        if not hasattr(self.data, "getlist"):
            return []
        ids = self.data.getlist("consumable_id")
        quantities = self.data.getlist("quantity")
        return [{"consumable_id": c, "quantity": q} for c, q in zip(ids, quantities, strict=False)]

    def clean(self):
        data = super().clean()
        pairs = []
        for line in self.raw_lines():
            consumable_id, quantity = line["consumable_id"], line["quantity"].strip()
            if not consumable_id and not quantity:
                continue
            try:
                value = int(quantity)
            except ValueError as exc:
                raise ValidationError("Informe quantidades em números inteiros.") from exc
            if not consumable_id.isdigit():
                raise ValidationError("Escolha o material em todas as linhas.")
            pairs.append((int(consumable_id), value))
        if not pairs:
            raise ValidationError("Informe pelo menos um material e a quantidade.")
        consumables = Consumable.objects.in_bulk([c for c, _ in pairs])
        if len(consumables) != len({c for c, _ in pairs}):
            raise ValidationError("Algum material escolhido não existe.")
        self.lines = [(consumables[c], q) for c, q in pairs]
        return data


EQUIPMENT_TYPE_LABELS = [(t.value, t.label) for t in OperationType if t in EQUIPMENT_OPERATIONS]
CONSUMABLE_TYPE_LABELS = [(t.value, t.label) for t in OperationType if t in CONSUMABLE_OPERATIONS]
