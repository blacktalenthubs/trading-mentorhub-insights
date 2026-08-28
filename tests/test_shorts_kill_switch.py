"""short_alerts_enabled — the master switch for SHORT alerts (2026-08-27).

Guards the trap this was written for: an EMPTY short_symbols allowlist does NOT block
shorts (the guard is `if short_symbols and ...`, so blank skips the check and every short
routes). The kill switch is the thing that actually means "no shorts".
"""
import re
from pathlib import Path

SRC = Path("api/app/routers/tv_webhook.py").read_text()
CFG = Path("api/app/models/regime_config.py").read_text()


class TestKillSwitchWiring:
    def test_default_is_enabled(self):
        """Deploying must not change behaviour — shorts stay on until deliberately turned off."""
        assert '"short_alerts_enabled": "true"' in CFG

    def test_switch_is_read_from_regime_config(self):
        assert 'shorts_enabled = (_rc.get("short_alerts_enabled", "true")' in SRC

    def test_suppresses_with_its_own_reason(self):
        assert 'suppressed_reason="shorts_disabled"' in SRC

    def test_covers_both_direction_spellings(self):
        block = SRC[SRC.index("if not shorts_enabled"):][:400]
        assert '"SHORT", "SELL"' in block

    def test_has_no_rc_4h_exemption(self):
        """The allowlist exempts tv_rc_4h; the kill switch must NOT — a switch that
        quietly lets a family through is worse than no switch."""
        block = SRC[SRC.index("if not shorts_enabled"):][:400]
        assert "tv_rc_4h" not in block

    def test_runs_before_the_allowlist(self):
        """Order matters: the allowlist would otherwise route a short the switch bans."""
        # match the CODE, not the same phrase quoted in the warning comment above it
        assert SRC.index("if not shorts_enabled") < SRC.index("if short_symbols and (sig.direction")


class TestBlankAllowlistTrapDocumented:
    def test_warning_replaces_the_wrong_claim(self):
        assert "BLANK = no shorts" not in CFG
        assert 'BLANK does NOT mean "no shorts"' in CFG
