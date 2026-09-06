"""Scanner UI controls — the per-rule toggle plumbing.

The scanner's live rules must be registered in ALERT_TYPE_CATALOG so they appear
in Settings and can be toggled OFF (opt-out delivery). Exit/lifecycle types stay
out (recorded-only, nothing to toggle). The editable-watchlist half is exercised
by the monitor poll, not unit-tested here.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.models.alert_type_config import ALERT_TYPE_CATALOG  # noqa: E402
from alert_config import ENABLED_RULES  # noqa: E402


_EXITS = {"auto_stop_out", "stop_loss_hit", "target_1_hit", "target_2_hit"}
_CATALOG_KEYS = {k for k, _l, _c, _d in ALERT_TYPE_CATALOG}


def test_every_scanner_entry_rule_is_toggleable():
    """Each delivering scanner rule is in the catalog → shows in Settings, can be silenced."""
    missing = [r for r in ENABLED_RULES if r not in _EXITS and r not in _CATALOG_KEYS]
    assert missing == [], f"scanner rules not registered in the catalog: {missing}"


def test_exit_lifecycle_types_not_added_as_toggles():
    """Exit types are recorded-only — they should not appear as scanner toggles.

    (They may exist elsewhere in the catalog, but the scanner block must not add them.)
    """
    from app.models.alert_type_config import _scanner_catalog
    scanner_keys = {k for k, _l, _c, _d in _scanner_catalog()}
    assert not (_EXITS & scanner_keys), f"exit types leaked into scanner toggles: {_EXITS & scanner_keys}"


def test_new_wmq_holds_registered_with_clean_labels():
    labels = {k: l for k, l, _c, _d in ALERT_TYPE_CATALOG}
    for k in ("pwl_reclaim", "pql_reclaim", "swing_reclaim_pqh"):
        assert k in labels
        # A real name, not the "Pwl Reclaim" title-case fallback.
        assert "hold" in labels[k].lower(), f"{k} → {labels[k]!r}"


def test_scanner_catalog_defaults_on():
    """Scanner rules default ON in the catalog (opt-out — they deliver by default)."""
    from app.models.alert_type_config import _scanner_catalog
    for k, _l, _c, default_enabled in _scanner_catalog():
        assert default_enabled is True, f"{k} should default ON"
