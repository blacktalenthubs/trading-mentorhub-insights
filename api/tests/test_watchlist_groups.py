"""Watchlist group feature tests.

Covers static structure (DEFAULT_GROUPS), schema validation, and the
tier-aware seed logic via direct dict inspection. Full API integration is
verified via the live curl smoke test against the Railway deployment.
"""

from __future__ import annotations

import pytest


class TestDefaultGroups:
    """The focused 3-tier watchlist shipped with seed-defaults / reset-defaults.

    Restructured 2026-06-17 from the old 12-sector layout: act on Tier 1 daily,
    drop to Tier 2/3 only when a name is clearly in play (~19 names total).
    """

    TIER1 = "Tier 1 · Daily Drivers"
    TIER2 = "Tier 2 · High Volatility"
    TIER3 = "Tier 3 · Sector Movers"

    @pytest.fixture
    def default_groups(self):
        from app.routers.watchlist import DEFAULT_GROUPS
        return DEFAULT_GROUPS

    def test_default_categories_exact_names(self, default_groups):
        names = [g["name"] for g in default_groups]
        assert names == [self.TIER1, self.TIER2, self.TIER3]

    def test_tier1_has_index_context_plus_core_drivers(self, default_groups):
        t1 = next(g for g in default_groups if g["name"] == self.TIER1)["symbols"]
        # Index context to anchor the tape...
        assert "SPY" in t1 and "QQQ" in t1
        # ...plus the core single-name drivers traded daily.
        for sym in ("NVDA", "AMD", "TSLA", "PLTR", "MU"):
            assert sym in t1, f"{sym} expected in Tier 1"

    def test_tier_symbol_membership(self, default_groups):
        by_name = {g["name"]: g["symbols"] for g in default_groups}
        assert by_name[self.TIER2] == ["SMCI", "AAOI", "RKLB", "IONQ", "HOOD"]
        assert by_name[self.TIER3] == ["AVGO", "MSFT", "MSTR", "META", "CEG", "VST", "SNDK"]

    def test_each_group_has_color_and_symbols(self, default_groups):
        for group in default_groups:
            assert "name" in group
            assert "color" in group and group["color"].startswith("#")
            assert "symbols" in group
            assert isinstance(group["symbols"], list)
            assert len(group["symbols"]) >= 2, (
                f"Group {group['name']} has too few symbols — at least 2 expected"
            )

    def test_total_symbol_count_is_focused(self, default_groups):
        """A deliberately narrow list (~19) so daily focus stays tight."""
        total = sum(len(g["symbols"]) for g in default_groups)
        assert total == 19, "Expected the focused 3-tier list to total 19 names"

    def test_no_duplicate_symbols_across_groups(self, default_groups):
        """A symbol appears in at most one tier."""
        seen: set[str] = set()
        for group in default_groups:
            for sym in group["symbols"]:
                assert sym not in seen, f"{sym} appears in multiple default groups"
                seen.add(sym)

    def test_exactly_three_tiers(self, default_groups):
        assert len(default_groups) == 3


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
