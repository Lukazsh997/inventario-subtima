"""Leitura das etiquetas reais do órgão (valores decodificados das fotos em docs/referencias)."""

import pytest
from django.core.exceptions import ValidationError

from apps.catalog.identification import normalize_scan
from apps.catalog.models import Ownership
from apps.catalog.services import find_equipment_by_code
from apps.inventory import services as inventory

from . import factories as f


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("085.057", "085.057"),
        ("https://wa.me/552138991801?text= ACES0001123", "ACES0001123"),
        ("https://wa.me/552138991801?text= 2419391010456", "2419391010456"),
        ("  8dbr9x1\n", "8DBR9X1"),
        ("https://exemplo.local/sem-texto", ""),
        ("", ""),
    ],
)
def test_normalize_scan(raw, expected):
    assert normalize_scan(raw) == expected


@pytest.fixture
def leased_dell(admin_user):
    return inventory.register_equipment(
        actor=admin_user,
        data=f.equipment_data(
            ownership=Ownership.LEASED, lessor="Locadora", serial_number="8dbr9x1", lessor_code="aces0001123"
        ),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scan",
    [
        "8DBR9X1",  # código de barras da etiqueta da locadora (série)
        "https://wa.me/552138991801?text= ACES0001123",  # QR da locadora
        "aces0001123",  # digitado
    ],
)
def test_find_leased_equipment_by_any_label_code(leased_dell, scan):
    assert list(find_equipment_by_code(scan)) == [leased_dell]


@pytest.mark.django_db
def test_find_owned_equipment_by_asset_tag_with_or_without_dots(admin_user):
    item = f.equipment(admin_user, asset_tag="085.057", serial_number="")
    assert list(find_equipment_by_code("085.057")) == [item]
    assert list(find_equipment_by_code("085057")) == [item]
    assert not find_equipment_by_code("085058").exists()


@pytest.mark.django_db
def test_identifiers_are_normalized_and_unique(admin_user, leased_dell):
    assert leased_dell.serial_number == "8DBR9X1"
    assert leased_dell.lessor_code == "ACES0001123"
    with pytest.raises(ValidationError, match="já pertence"):
        f.equipment(admin_user, serial_number=" 8dbr9x1 ")
    f.equipment(admin_user, asset_tag="085.057", serial_number="")
    with pytest.raises(ValidationError, match="patrimônio 085057 já pertence"):
        f.equipment(admin_user, asset_tag="085057", serial_number="")


@pytest.mark.django_db
def test_equipment_requires_an_identifier(admin_user):
    with pytest.raises(ValidationError, match="pelo menos um identificador"):
        inventory.register_equipment(actor=admin_user, data=f.equipment_data(serial_number=""))
