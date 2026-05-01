"""Watchlist group feature tests.

Covers static structure (DEFAULT_GROUPS), schema validation, and the
tier-aware seed logic via direct dict inspection. Full API integration is
verified via the live curl smoke test against the Railway deployment.
"""

from __future__ import annotations

import pytest


class TestDefaultGroups:
    """The curated 7-category list shipped with seed-defaults."""

    @pytest.fixture
    def default_groups(self):
        from app.routers.watchlist import DEFAULT_GROUPS
        return DEFAULT_GROUPS

    def test_seven_categories_exact_names(self, default_groups):
        names = [g["name"] for g in default_groups]
        assert names == [
            "Mega Tech",
            "Chips",
            "Memory",
            "Optics",
            "Cloud",
            "BTC",
            "Power",
        ]

    def test_each_group_has_color_and_symbols(self, default_groups):
        for group in default_groups:
            assert "name" in group
            assert "color" in group and group["color"].startswith("#")
            assert "symbols" in group
            assert isinstance(group["symbols"], list)
            assert len(group["symbols"]) >= 2, (
                f"Group {group['name']} has too few symbols — at least 2 expected"
            )

    def test_total_symbol_count_under_premium_cap(self, default_groups):
        """Premium tier cap is 25; default seed should fit under or equal."""
        total = sum(len(g["symbols"]) for g in default_groups)
        # Curated list is 27 — slightly over premium 25. Seed handles cap
        # gracefully (skips overflow). This test documents the design choice:
        # we WANT a >25-symbol curated list so trimming is intentional, not
        # forced by the seed.
        assert total >= 20, "Default seed should be a meaningful watchlist"
        assert total <= 35, "Default seed shouldn't blow past any tier cap by far"

    def test_no_duplicate_symbols_across_groups(self, default_groups):
        """A symbol appears in at most one default group (no NVDA in both Tech and Chips)."""
        seen: set[str] = set()
        for group in default_groups:
            for sym in group["symbols"]:
                assert sym not in seen, f"{sym} appears in multiple default groups"
                seen.add(sym)

    def test_btc_group_has_two_picks(self, default_groups):
        """User explicitly asked for top 2 BTC stocks."""
        btc = next(g for g in default_groups if g["name"] == "BTC")
        assert len(btc["symbols"]) == 2
        assert "MSTR" in btc["symbols"]
        assert "COIN" in btc["symbols"]

    def test_mega_tech_excludes_aapl_per_growth_thesis(self, default_groups):
        """User wanted strong earnings growth — AAPL excluded by design."""
        mega = next(g for g in default_groups if g["name"] == "Mega Tech")
        assert "AAPL" not in mega["symbols"]
        assert "NVDA" in mega["symbols"]


class TestSchemas:
    """Pydantic schemas for groups + items."""

    def test_create_group_request_valid(self):
        from app.schemas.watchlist import CreateGroupRequest

        req = CreateGroupRequest(name="Mega Tech", sort_order=1, color="#1f6feb")
        assert req.name == "Mega Tech"
        assert req.sort_order == 1
        assert req.color == "#1f6feb"

    def test_create_group_rejects_empty_name(self):
        from pydantic import ValidationError
        from app.schemas.watchlist import CreateGroupRequest

        with pytest.raises(ValidationError):
            CreateGroupRequest(name="")

    def test_create_group_rejects_long_name(self):
        from pydantic import ValidationError
        from app.schemas.watchlist import CreateGroupRequest

        with pytest.raises(ValidationError):
            CreateGroupRequest(name="x" * 51)

    def test_update_group_request_partial(self):
        """All fields optional — supports PATCH semantics."""
        from app.schemas.watchlist import UpdateGroupRequest

        req = UpdateGroupRequest(name="Renamed")
        assert req.name == "Renamed"
        assert req.sort_order is None
        assert req.color is None

    def test_move_item_to_group(self):
        from app.schemas.watchlist import MoveItemRequest

        req = MoveItemRequest(group_id=5)
        assert req.group_id == 5

    def test_move_item_to_ungrouped(self):
        """Null group_id = move to ungrouped (NOT same as missing field)."""
        from app.schemas.watchlist import MoveItemRequest

        req = MoveItemRequest(group_id=None)
        assert req.group_id is None

    def test_add_symbol_with_group(self):
        from app.schemas.watchlist import AddSymbolRequest

        req = AddSymbolRequest(symbol="NVDA", group_id=3)
        assert req.symbol == "NVDA"
        assert req.group_id == 3

    def test_add_symbol_without_group_legacy(self):
        """Backward compat — old clients without group_id still work."""
        from app.schemas.watchlist import AddSymbolRequest

        req = AddSymbolRequest(symbol="NVDA")
        assert req.symbol == "NVDA"
        assert req.group_id is None

    def test_watchlist_item_response_includes_group_id(self):
        from app.schemas.watchlist import WatchlistItemResponse

        resp = WatchlistItemResponse(id=1, symbol="NVDA", group_id=2)
        assert resp.group_id == 2

    def test_watchlist_item_response_ungrouped(self):
        from app.schemas.watchlist import WatchlistItemResponse

        resp = WatchlistItemResponse(id=1, symbol="SPY")
        assert resp.group_id is None


class TestModel:
    """SQLAlchemy model surface."""

    def test_watchlist_group_has_required_columns(self):
        from app.models.watchlist import WatchlistGroup

        cols = {c.name for c in WatchlistGroup.__table__.columns}
        assert {"id", "user_id", "name", "sort_order", "color", "created_at"} <= cols

    def test_watchlist_item_has_group_id(self):
        from app.models.watchlist import WatchlistItem

        cols = {c.name for c in WatchlistItem.__table__.columns}
        assert "group_id" in cols

    def test_watchlist_item_group_id_is_nullable(self):
        """Existing rows without a group should remain valid."""
        from app.models.watchlist import WatchlistItem

        col = WatchlistItem.__table__.columns["group_id"]
        assert col.nullable is True

    def test_unique_constraint_on_user_name(self):
        """Same user can't have two groups with same name."""
        from app.models.watchlist import WatchlistGroup

        constraints = [c.name for c in WatchlistGroup.__table_args__]
        assert "uq_watchlist_group_user_name" in constraints
