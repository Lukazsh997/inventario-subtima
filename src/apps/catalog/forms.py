from django import forms

from .models import Category, Condition, ItemKind, Ownership, Unit


class CategoryForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=100)
    kind = forms.ChoiceField(label="Tipo", choices=ItemKind.choices)


class EquipmentForm(forms.Form):
    category = forms.ModelChoiceField(label="Categoria", queryset=Category.objects.none())
    name = forms.CharField(
        label="Nome do equipamento",
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Desktop Dell OptiPlex 7010"}),
    )
    manufacturer = forms.CharField(label="Fabricante", max_length=80, required=False)
    model = forms.CharField(label="Modelo", max_length=120, required=False)
    ownership = forms.ChoiceField(
        label="Propriedade",
        choices=Ownership.choices,
        initial=Ownership.OWNED,
        widget=forms.Select(attrs={"x-model": "ownership"}),
    )
    lessor = forms.CharField(label="Locadora", max_length=120, required=False)
    asset_tag = forms.CharField(
        label="Patrimônio",
        max_length=255,
        required=False,
        help_text="Código de barras da etiqueta da Prefeitura, ex.: 085.057",
    )
    serial_number = forms.CharField(
        label="Nº de série / Service Tag",
        max_length=255,
        required=False,
        help_text="Nas etiquetas da locadora, é o código de barras",
    )
    lessor_code = forms.CharField(
        label="Código da locadora",
        max_length=255,
        required=False,
        help_text="Ex.: ACES0001123 (impresso na etiqueta ou lido do QR)",
    )
    condition = forms.ChoiceField(label="Estado de conservação", choices=Condition.choices, initial=Condition.GOOD)
    acquisition_date = forms.DateField(
        label="Data de aquisição", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    notes = forms.CharField(label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    # max_length 255: o campo recebe a leitura bruta (ex.: link do QR); o serviço extrai e valida o código.
    identifier_fields = ("asset_tag", "serial_number", "lessor_code")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(kind=ItemKind.EQUIPMENT, active=True)

    def clean(self):
        data = super().clean()
        if not any((data.get(name) or "").strip() for name in self.identifier_fields):
            raise forms.ValidationError(
                "Leia ou digite pelo menos um identificador: patrimônio, nº de série ou código da locadora."
            )
        if data.get("ownership") == Ownership.LEASED and not (data.get("lessor") or "").strip():
            self.add_error("lessor", "Informe a locadora.")
        return data


class ConsumableForm(forms.Form):
    category = forms.ModelChoiceField(label="Categoria", queryset=Category.objects.none())
    name = forms.CharField(
        label="Nome", max_length=150, widget=forms.TextInput(attrs={"placeholder": "Ex.: Toner HP 151A"})
    )
    reference = forms.CharField(label="Código/referência do fabricante", max_length=60, required=False)
    unit = forms.ChoiceField(label="Unidade", choices=Unit.choices, initial=Unit.UNIT)
    min_stock = forms.IntegerField(
        label="Estoque mínimo",
        min_value=0,
        initial=0,
        help_text="Abaixo ou igual a este saldo, o material é destacado como crítico",
    )
    compatibility = forms.CharField(label="Compatível com", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(kind=ItemKind.CONSUMABLE, active=True)
