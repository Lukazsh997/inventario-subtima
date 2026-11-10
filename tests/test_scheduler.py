from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.core.management.base import CommandError

from apps.core.management.commands.run_scheduler import next_run, parse_time

TZ = ZoneInfo("America/Sao_Paulo")


def test_next_run_same_day():
    assert next_run(datetime(2026, 11, 10, 1, 0, tzinfo=TZ), time(2, 0)) == datetime(2026, 11, 10, 2, 0, tzinfo=TZ)


def test_next_run_next_day_when_time_passed():
    assert next_run(datetime(2026, 11, 10, 2, 0, tzinfo=TZ), time(2, 0)) == datetime(2026, 11, 11, 2, 0, tzinfo=TZ)


@pytest.mark.parametrize("value", ["2h", "25:00", "", "aa:bb"])
def test_invalid_backup_time(value):
    with pytest.raises(CommandError):
        parse_time(value)
