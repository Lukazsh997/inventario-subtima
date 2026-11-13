"""Estrutura comum dos relatórios.

Cada relatório declara título, filtros aceitos, colunas e como produzir as
linhas. A mesma definição alimenta a pré-visualização na tela, o CSV e o PDF,
para que os três mostrem exatamente os mesmos dados.
"""

from dataclasses import dataclass, field
from datetime import date

from django import forms

from apps.catalog.models import Category, EquipmentStatus, ItemKind
from apps.organization.models import Sector


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    align: str = "start"  # start | end


@dataclass
class ReportResult:
    columns: list[Column]
    rows: list[dict]
    summary: list[str] = field(default_factory=list)
    header: list[tuple[str, str]] = field(default_factory=list)  # pares rótulo/valor acima da tabela


class ReportFilterForm(forms.Form):
    """Todos os filtros possíveis; cada relatório exibe apenas os que usa."""

    de = forms.DateField(label="De", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    ate = forms.DateField(label="Até", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    categoria = forms.ModelChoiceField(
        label="Categoria", queryset=Category.objects.none(), required=False, empty_label="Todas"
    )
    setor = forms.ModelChoiceField(
        label="Setor", queryset=Sector.objects.filter(active=True), required=False, empty_label="Todos"
    )
    situacao = forms.ChoiceField(label="Situação", required=False)
    servidor = forms.CharField(label="Servidor (nome ou matrícula)", required=False, max_length=100)
    equipamento = forms.CharField(label="Equipamento (patrimônio, série ou ACES)", required=False, max_length=255)
    atrasados = forms.BooleanField(label="Somente com devolução atrasada", required=False)

    def __init__(self, *args, report=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.report = report
        kinds = {
            "categoria_eq": [ItemKind.EQUIPMENT],
            "categoria_mat": [ItemKind.CONSUMABLE],
            "categoria": [ItemKind.EQUIPMENT, ItemKind.CONSUMABLE],
        }
        for name, allowed in kinds.items():
            if report and name in report.filters:
                self.fields["categoria"].queryset = Category.objects.filter(kind__in=allowed).order_by("kind", "name")
        if report:
            self.fields["situacao"].choices = [("", "Todas"), *report.situation_choices]

    def visible(self):
        names = {"categoria" if f.startswith("categoria") else f for f in self.report.filters}
        if "periodo" in self.report.filters:
            names |= {"de", "ate"}
        return [self[name] for name in self.fields if name in names]

    def describe(self) -> list[str]:
        """Filtros aplicados, em texto, para o cabeçalho do PDF."""
        if not self.is_valid():
            return []
        data, parts = self.cleaned_data, []
        if data.get("de") or data.get("ate"):
            start = data["de"].strftime("%d/%m/%Y") if data.get("de") else "início"
            end = data["ate"].strftime("%d/%m/%Y") if data.get("ate") else "hoje"
            parts.append(f"Período: {start} a {end}")
        for key, label in (("categoria", "Categoria"), ("setor", "Setor")):
            if data.get(key):
                parts.append(f"{label}: {data[key]}")
        if data.get("situacao"):
            parts.append(f"Situação: {dict(self.fields['situacao'].choices).get(data['situacao'])}")
        if data.get("servidor"):
            parts.append(f"Servidor: {data['servidor']}")
        if data.get("equipamento"):
            parts.append(f"Equipamento: {data['equipamento']}")
        if data.get("atrasados"):
            parts.append("Somente atrasados")
        return parts


class Report:
    slug: str = ""
    title: str = ""
    description: str = ""
    filters: tuple[str, ...] = ()
    situation_choices: list[tuple[str, str]] = []
    landscape: bool = True
    requires: str | None = None  # filtro obrigatório para gerar (ex.: equipamento)

    def run(self, params: dict) -> ReportResult:  # pragma: no cover - implementado nas subclasses
        raise NotImplementedError

    @staticmethod
    def period_filter(queryset, params: dict, field_name: str):
        if params.get("de"):
            queryset = queryset.filter(**{f"{field_name}__date__gte": params["de"]})
        if params.get("ate"):
            queryset = queryset.filter(**{f"{field_name}__date__lte": params["ate"]})
        return queryset


EQUIPMENT_SITUATIONS = [(v, label) for v, label in EquipmentStatus.choices]


def fmt_date(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "astimezone"):
        from django.utils import timezone

        return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)
