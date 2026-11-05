"""Master-as-single-universe (trader decision 2026-11-04) — unit tests.

Background: the TBA Pine fired ISRG (2026-11-04) and ZTS (2026-11-02), the
webhooks delivered, and ~400 users received copies — but the trader (user 3)
got ZERO rows, because the desk wrote his copy only for symbols on his
PERSONAL watchlist while ISRG/ZTS sit on the platform MASTER watchlist.
His decision: "whatever we have in master should be used — we only keep
updating master — master should be in sync with scanner as well."

These tests cover the pure pieces of the fix:
1. tv_webhook._admin_master_matching — the admin's effective watcher set is
   personal ∪ master; non-admin routing is untouched by construction.
2. analytics.sync_master_from_tv.parse_tv_export — TV master2 export parsing
   for the TV → desk Master reconciliation script.
3. analytics.focus_gate.master_symbols — fails SAFE to an empty set when no
   DATABASE_URL is available (never invents a universe).
"""
from __future__ import annotations

import re

from api.app.routers.tv_webhook import _admin_master_matching

ADMIN_EMAILS = {"vbolofinde@gmail.com", "segunbolofinde@gmail.com"}
MASTER_EMAIL = "master@busytradersdesk"
# (user_id, email): 3 + 9 are the trader's two admin accounts, 184 is the
# master-universe holder, 7 is an ordinary platform user.
EMAILS = [
    (3, "vbolofinde@gmail.com"),
    (9, "segunbolofinde@gmail.com"),
    (184, "master@busytradersdesk"),
    (7, "someone@example.com"),
]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


class TestAdminMasterMatching:
    # (user_id, symbol) watchlist rows for ALL users, as _users_watching loads.
    ROWS = [
        (184, "ISRG"),   # master-only — the 2026-11-04 miss
        (184, "ZTS"),    # master-only — the 2026-11-02 miss
        (184, "AMGN"),
        (7, "ISRG"),     # an ordinary user watching it does not widen the admin set
        (3, "AMGN"),     # the trader's personal list
    ]

    def test_master_only_symbol_adds_admins(self):
        out = _admin_master_matching(self.ROWS, EMAILS, "ISRG", _norm, MASTER_EMAIL, ADMIN_EMAILS)
        assert out == {3, 9}

    def test_symbol_nowhere_on_master_adds_nobody(self):
        out = _admin_master_matching(self.ROWS, EMAILS, "NVDA", _norm, MASTER_EMAIL, ADMIN_EMAILS)
        assert out == set()

    def test_master_account_and_other_users_never_returned(self):
        out = _admin_master_matching(self.ROWS, EMAILS, "ZTS", _norm, MASTER_EMAIL, ADMIN_EMAILS)
        assert 184 not in out  # universe holder, not a recipient
        assert 7 not in out    # non-admin routing unchanged

    def test_no_master_account_no_union(self):
        rows = [(3, "AMGN"), (7, "ISRG")]
        out = _admin_master_matching(rows, EMAILS, "ISRG", _norm, MASTER_EMAIL, ADMIN_EMAILS)
        assert out == set()

    def test_matching_is_normalized(self):
        rows = [(184, "eth-usd")]
        out = _admin_master_matching(rows, EMAILS, "ETHUSD", _norm, MASTER_EMAIL, ADMIN_EMAILS)
        assert out == {3, 9}


class TestParseTvExport:
    def test_exchange_prefixes_sections_and_dots(self):
        from analytics.sync_master_from_tv import parse_tv_export

        text = "###Mega Tech,NASDAQ:AMGN,NASDAQ:CAKE\nNYSE:LLY, BRK.B"
        assert parse_tv_export(text) == ["AMGN", "BRK.B", "CAKE", "LLY"]

    def test_garbage_tokens_dropped(self):
        from analytics.sync_master_from_tv import parse_tv_export

        assert parse_tv_export("NASDAQ:AAPL, ,123,TOOLONGTICKERXX") == ["AAPL"]

    def test_empty_input(self):
        from analytics.sync_master_from_tv import parse_tv_export

        assert parse_tv_export("") == []


class TestMasterSymbolsFallback:
    def test_no_dsn_returns_empty_set(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from analytics.focus_gate import master_symbols

        assert master_symbols(force=True) == set()
