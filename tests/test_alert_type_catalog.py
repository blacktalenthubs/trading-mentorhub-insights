"""The alert-type catalogue must FIT its own table.

seed_alert_type_config() runs every catalogue row in ONE transaction at API
startup, and main.py catches the failure as a warning. So a single row that
violates a column width doesn't fail loudly — it rolls back the whole seed and
EVERY new type silently never appears in Settings, with one warning line in the
logs as the only trace.

This has now happened twice: fv_* labels (the DB was widened 140→200 in response,
2026-07-18) and last4h_long at 201 chars against String(200), 2026-08-29. Both
times SQLite let it through locally — SQLite does not enforce VARCHAR lengths,
Postgres does — so the bug only ever surfaced in production.

These assertions are the cheap version of that lesson.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.models.alert_type_config import (  # noqa: E402
    ALERT_TYPE_CATALOG,
    OBSOLETE_ALERT_TYPES,
    AlertTypeConfig,
)

_COLS = AlertTypeConfig.__table__.c


@pytest.mark.parametrize("field, index", [("alert_type", 0), ("label", 1), ("category", 2)])
def test_catalog_fits_column_width(field, index):
    """Every catalogue value fits the column it is seeded into."""
    limit = _COLS[field].type.length
    over = [
        (row[0], len(row[index]), limit)
        for row in ALERT_TYPE_CATALOG
        if len(row[index]) > limit
    ]
    assert not over, (
        f"{field} exceeds String({limit}) — this ABORTS the whole startup seed "
        f"silently on Postgres, so no new alert type reaches Settings: {over}"
    )


def test_catalog_keys_are_unique():
    """A duplicate key would make ON CONFLICT overwrite one row with the other."""
    keys = [row[0] for row in ALERT_TYPE_CATALOG]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate alert_type keys in the catalogue: {sorted(dupes)}"


def test_catalog_rows_are_not_also_obsolete():
    """The seeder inserts the catalogue then DELETEs obsolete keys — a key in both
    lists is inserted and immediately dropped, so its Settings row never appears."""
    both = sorted({row[0] for row in ALERT_TYPE_CATALOG} & set(OBSOLETE_ALERT_TYPES))
    assert not both, f"seeded AND obsoleted (inserted then deleted): {both}"
