from django import forms

from .models import Sector


class SectorForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=200)
    acronym = forms.CharField(label="Sigla", max_length=30, required=False)
    parent = forms.ModelChoiceField(
        label="Vinculado a",
        queryset=Sector.objects.filter(active=True),
        required=False,
        empty_label="— nenhum (nível mais alto) —",
    )

    def __init__(self, *args, editing: Sector | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if editing is not None:
            self.fields["parent"].queryset = Sector.objects.filter(active=True).exclude(pk=editing.pk)


class LocationForm(forms.Form):
    name = forms.CharField(
        label="Descrição do local",
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Prédio sede, 2º andar, sala 204"}),
    )


class RecipientForm(forms.Form):
    full_name = forms.CharField(label="Nome completo", max_length=200)
    registration = forms.CharField(label="Matrícula", max_length=30, required=False)
    job_title = forms.CharField(label="Cargo/função", max_length=120, required=False)
    sector = forms.ModelChoiceField(label="Setor", queryset=Sector.objects.filter(active=True))
    phone = forms.CharField(label="Telefone/ramal", max_length=40, required=False)
