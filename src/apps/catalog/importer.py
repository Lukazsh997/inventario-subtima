"""Importação em lote de equipamentos a partir de planilha (CSV ou XLSX).

Fluxo: ler → validar todas as linhas (sem gravar) → mostrar a prévia com os erros
→ confirmar → gravar tudo numa única transação. Se qualquer linha falhar na
gravação, nada é importado.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.inventory import services as inventory
from apps.organization.models import Recipient, Sector

from .identification import digits_only, normalize_scan
from .models import Category, Condition, Equipment, ItemKind, Ownership

MAX_ROWS = 2000
COLUMNS = [
    "categoria",
    "nome",
    "fabricante",
    "modelo",
    "propriedade",
    "locadora",
    "patrimonio",
    "serie",
    "codigo_locadora",
    "estado",
    "data_aquisicao",
    "observacoes",
    "setor_atual",
    "servidor_atual",
]
REQUIRED = ["categoria", "nome"]
EXAMPLE = [
    "Computadores desktop",
    "Desktop Dell OptiPlex 7010",
    "Dell",
    "OptiPlex 7010",
    "locado",
    "Locadora X",
    "",
    "8DBR9X1",
    "ACES0001123",
    "bom",
    "",
    "",
    "SMU",
    "12345",
]


@dataclass
class ImportRow:
    line: int
    values: dict
    errors: list[str] = field(default_factory=list)
    data: dict | None = None  # dados prontos para register_equipment
    placement: dict | None = None  # {"sector_id", "recipient_id"} se já está em uso


def template_csv() -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerow(EXAMPLE)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def read_table(uploaded) -> list[dict]:
    name = (uploaded.name or "").lower()
    raw = uploaded.read()
    if name.endswith(".xlsx"):
        rows = _read_xlsx(raw)
    elif name.endswith(".csv"):
        rows = _read_csv(raw)
    else:
        raise ValidationError("Envie um arquivo .csv ou .xlsx.")
    if not rows:
        raise ValidationError("A planilha está vazia.")
    header = [_key(h) for h in rows[0]]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ValidationError(f"Colunas obrigatórias ausentes: {', '.join(missing)}. Use o modelo de planilha.")
    unknown = [h for h in header if h and h not in COLUMNS]
    if unknown:
        raise ValidationError(f"Colunas não reconhecidas: {', '.join(unknown)}. Use o modelo de planilha.")
    records = []
    for values in rows[1:]:
        record = {h: _text(v) for h, v in zip(header, values, strict=False) if h}
        if any(record.values()):
            records.append(record)
    if len(records) > MAX_ROWS:
        raise ValidationError(f"Máximo de {MAX_ROWS} equipamentos por planilha; divida o arquivo.")
    return records


def _key(header) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", str(header or "")).encode("ascii", "ignore").decode().strip().lower()
    return text.replace(" ", "_").replace("-", "_")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_csv(raw: bytes) -> list[list]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        raise ValidationError("Não foi possível ler o arquivo CSV (codificação desconhecida).")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,\t") if text.strip() else csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx(raw: bytes) -> list[list]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura vira mensagem para o usuário
        raise ValidationError("Não foi possível abrir a planilha XLSX.") from exc
    sheet = workbook.worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def _choice(value: str, choices, default: str, label: str, errors: list) -> str:
    if not value:
        return default
    normalized = _key(value)
    for key, text in choices:
        if normalized in (key, _key(text), _key(text.split(" (")[0])):
            return key
    errors.append(f'{label} inválido: "{value}".')
    return default


def _parse_date(value: str, errors: list):
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    errors.append(f'Data de aquisição inválida: "{value}" (use dd/mm/aaaa).')
    return None


def validate(records: list[dict]) -> list[ImportRow]:
    categories = {_key(c.name): c for c in Category.objects.filter(kind=ItemKind.EQUIPMENT, active=True)}
    sectors = list(Sector.objects.filter(active=True))
    rows = []
    seen: dict[tuple, int] = {}
    for index, values in enumerate(records, start=2):  # linha 1 é o cabeçalho
        row = ImportRow(line=index, values=values)
        errors = row.errors
        category = categories.get(_key(values.get("categoria")))
        if category is None:
            errors.append(f'Categoria não encontrada: "{values.get("categoria", "")}".')
        if not values.get("nome"):
            errors.append("Informe o nome do equipamento.")
        ownership = _choice(values.get("propriedade", ""), Ownership.choices, Ownership.OWNED, "Propriedade", errors)
        condition = _choice(values.get("estado", ""), Condition.choices, Condition.GOOD, "Estado", errors)
        serial = normalize_scan(values.get("serie", "")) or None
        asset_tag = normalize_scan(values.get("patrimonio", "")) or None
        lessor_code = normalize_scan(values.get("codigo_locadora", "")) or None
        if not (serial or asset_tag or lessor_code):
            errors.append("Informe patrimônio, série ou código da locadora.")
        if ownership == Ownership.LEASED and not values.get("locadora"):
            errors.append("Equipamento locado: informe a locadora.")
        for kind, value in (
            ("série", serial),
            ("patrimônio", digits_only(asset_tag) or asset_tag),
            ("código da locadora", lessor_code),
        ):
            if value:
                key = (kind, value)
                if key in seen:
                    errors.append(f"{kind.capitalize()} {value} repetido na planilha (linha {seen[key]}).")
                seen[key] = index
        conflict = Q()
        if serial:
            conflict |= Q(serial_number=serial)
        if asset_tag:
            conflict |= Q(asset_tag_digits=digits_only(asset_tag) or asset_tag)
        if lessor_code:
            conflict |= Q(lessor_code=lessor_code)
        if conflict and (existing := Equipment.objects.filter(conflict).first()):
            errors.append(f"Já cadastrado: {existing}.")
        acquisition = _parse_date(values.get("data_aquisicao", ""), errors)

        sector = recipient = None
        if sector_text := values.get("setor_atual", ""):
            key = sector_text.strip().lower()
            matches = [s for s in sectors if key in (s.acronym.lower(), s.name.lower())]
            if len(matches) != 1:
                errors.append(f'Setor não encontrado (ou ambíguo): "{sector_text}".')
            else:
                sector = matches[0]
        if person_text := values.get("servidor_atual", ""):
            if sector is None:
                errors.append("Para informar o servidor, informe também o setor atual.")
            else:
                people = Recipient.objects.filter(active=True).filter(
                    Q(registration=person_text) | Q(full_name__iexact=person_text)
                )
                if people.count() != 1:
                    errors.append(f'Servidor não encontrado (ou ambíguo): "{person_text}". Cadastre-o antes.')
                else:
                    recipient = people.first()
        if sector is not None and recipient is None and not errors:
            errors.append("Equipamento em uso precisa do servidor responsável (servidor_atual).")

        if not errors:
            row.data = {
                "category": category,
                "name": values["nome"],
                "manufacturer": values.get("fabricante", ""),
                "model": values.get("modelo", ""),
                "ownership": ownership,
                "lessor": values.get("locadora", ""),
                "serial_number": serial or "",
                "asset_tag": asset_tag or "",
                "lessor_code": lessor_code or "",
                "condition": condition,
                "acquisition_date": acquisition,
                "notes": values.get("observacoes", ""),
            }
            if sector is not None:
                row.placement = {"sector": sector, "recipient": recipient}
        rows.append(row)
    return rows


@transaction.atomic
def import_rows(*, actor, rows: list[ImportRow]) -> list[Equipment]:
    """Grava todas as linhas válidas; qualquer falha desfaz a importação inteira."""
    if any(row.errors for row in rows):
        raise ValidationError("A planilha tem linhas com erro. Corrija e envie de novo.")
    created = []
    for row in rows:
        placement = None
        if row.placement:
            placement = inventory.OperationData(
                destination_sector=row.placement["sector"],
                recipient=row.placement["recipient"],
                notes="Inventário inicial: importado de planilha",
            )
        try:
            created.append(inventory.register_equipment(actor=actor, data=row.data, in_use=placement))
        except ValidationError as error:
            raise ValidationError(f"Linha {row.line}: {' '.join(error.messages)}") from error
    return created
