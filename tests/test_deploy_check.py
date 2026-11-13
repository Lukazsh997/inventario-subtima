"""Comando verificar_implantacao: relatório, instantâneo e comparação de persistência."""

import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.core.management.commands.verificar_implantacao import compare, snapshot

from . import factories as f


@pytest.fixture
def dirs(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR / "media"
    settings.BACKUP_DIR = tmp_path / "backups"
    settings.DEBUG = False
    settings.SECRET_KEY = "k" * 50
    return settings


def test_report_ok_and_warns_without_backup(db, dirs):
    out = StringIO()
    call_command("verificar_implantacao", stdout=out)
    text = out.getvalue()
    assert "OK     Migrações: todas aplicadas" in text
    assert "OK     Histórico imutável" in text
    assert "AVISO  Último backup" in text
    assert "OK     Geração de PDF" in text


def test_report_fails_on_weak_secret(db, dirs):
    dirs.SECRET_KEY = "insecure-dev-key"
    with pytest.raises(CommandError):
        call_command("verificar_implantacao", stdout=StringIO())


def test_snapshot_marker_is_stable_and_compare_detects_loss(db, dirs, tech_user, tmp_path):
    f.equipment(tech_user)
    out = StringIO()
    call_command("verificar_implantacao", "--json", stdout=out)
    before = json.loads(out.getvalue())
    assert before["contagens"]["equipamentos"] == 1
    assert snapshot()["marcador"] == before["marcador"]
    path = tmp_path / "antes.json"
    path.write_text(out.getvalue())
    call_command("verificar_implantacao", "--comparar", str(path), stdout=StringIO())

    assert compare(before, {**before, "marcador": "outro"})
    lost = {**before, "contagens": {**before["contagens"], "equipamentos": 0}}
    assert compare(before, lost) == ["equipamentos: eram 1, agora 0."]
