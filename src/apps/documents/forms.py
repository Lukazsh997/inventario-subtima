from django import forms

from apps.inventory.models import OperationType

from .models import DocumentStatus, ItemKind

OPERATION_CHOICES = [(t.value, t.label) for t in OperationType if t not in (OperationType.REVERSAL,)]


class TemplateForm(forms.Form):
    name = forms.CharField(label="Nome do termo", max_length=120)
    item_kind = forms.ChoiceField(label="Usado para", choices=ItemKind.choices)
    operation_types = forms.MultipleChoiceField(
        label="Tipos de operação", choices=OPERATION_CHOICES, widget=forms.CheckboxSelectMultiple
    )
    source = forms.CharField(
        label="Origem do texto / autorização",
        max_length=255,
        help_text="Ex.: Termo de Responsabilidade (DOCX) enviado pela SUBTIMA em 13/11/2026",
    )
    css = forms.CharField(
        label="Estilo (CSS)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10, "class": "font-monospace small", "spellcheck": "false"}),
    )
    body = forms.CharField(
        label="Conteúdo (HTML com variáveis)",
        widget=forms.Textarea(attrs={"rows": 22, "class": "font-monospace small", "spellcheck": "false"}),
    )


class StatusForm(forms.Form):
    status = forms.ChoiceField(label="Nova situação", choices=DocumentStatus.choices)
    note = forms.CharField(label="Observação", max_length=255, required=False)


class AssetForm(forms.Form):
    image = forms.ImageField(label="Nova imagem (PNG ou JPG, fundo transparente de preferência)")

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image.size > 2 * 1024 * 1024:
            raise forms.ValidationError("A imagem deve ter no máximo 2 MB.")
        if getattr(image, "content_type", "") not in ("image/png", "image/jpeg"):
            raise forms.ValidationError("Envie um arquivo PNG ou JPG.")
        return image
