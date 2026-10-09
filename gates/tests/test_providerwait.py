import datetime

import pytest
from gates.providerwait import retry_seconds


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("usage limit; resets Oct 12, 3pm (Australia/Sydney)", 259020),
        ("usage limit; try again at 5:05 PM (Australia/Sydney)", 7320),
        ("usage limit; resets 2pm (Australia/Sydney)", 82620),
        ("usage limit reached", 1800),
    ],
)
def test_fr0_13_reset_date_clock_and_zone(tmp_path, message, expected):
    log = tmp_path / "provider.log"
    log.write_text(message)
    now = datetime.datetime(2026, 10, 9, 4, 4, tzinfo=datetime.UTC)
    assert retry_seconds([log], 1800, now=now) == expected


def test_fr0_13_unknown_provider_uses_bounded_probe(tmp_path):
    weekly = tmp_path / "weekly.log"
    weekly.write_text("usage limit; resets Oct 12, 3pm (Australia/Sydney)")
    unknown = tmp_path / "unknown.log"
    unknown.write_text("usage limit exceeded")
    now = datetime.datetime(2026, 10, 9, 4, 4, tzinfo=datetime.UTC)
    assert retry_seconds([weekly, unknown], 1800, now=now) == 1800
