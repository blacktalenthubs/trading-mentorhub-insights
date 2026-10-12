"""Settings > Alert Types lists in curated catalog order, not alphabetical.

Regression guard: alphabetical sort put `rc_daily_hrec` (h) above
`rc_daily_long` (l), hiding the primary "Daily RC long" under its RC-H variant
(and below the fold on mobile). The list must follow ALERT_TYPE_CATALOG order.
"""

from __future__ import annotations

from app.routers.alert_config import _CATALOG_END, _CATALOG_ORDER


def test_catalog_orders_long_before_hrec():
    # The RC families are authored long-first in the catalog.
    assert _CATALOG_ORDER["rc_daily_long"] < _CATALOG_ORDER["rc_daily_hrec"]
    assert _CATALOG_ORDER["rc_4h_long"] < _CATALOG_ORDER["rc_4h_hrec"]


class _Row:
    def __init__(self, alert_type: str, category: str):
        self.alert_type = alert_type
        self.category = category


def _sorted(rows):
    return [
        r.alert_type
        for r in sorted(
            rows,
            key=lambda r: (_CATALOG_ORDER.get(r.alert_type, _CATALOG_END), r.category, r.alert_type),
        )
    ]


def test_endpoint_sort_places_long_before_hrec():
    rows = [
        _Row("rc_daily_hrec", "Daily RC"),
        _Row("rc_daily_long", "Daily RC"),
        _Row("rc_4h_short", "4h reversal"),
        _Row("rc_4h_long", "4h reversal"),
    ]
    order = _sorted(rows)
    assert order.index("rc_daily_long") < order.index("rc_daily_hrec")
    assert order.index("rc_4h_long") < order.index("rc_4h_short")


def test_unknown_types_sort_last():
    rows = [_Row("zzz_not_in_catalog", "X"), _Row("rc_daily_long", "Daily RC")]
    assert _sorted(rows)[-1] == "zzz_not_in_catalog"
