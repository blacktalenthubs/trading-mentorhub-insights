"""Tests for the persisted Focus List feature (spec 55).

Two layers:
  - Pure service-helper unit tests (window classification, recommendation
    mapping) — no DB, no network.
  - Endpoint behaviour tests — the router coroutines are awaited directly
    against a real async SQLite DB, with the AI engine monkeypatched. No
    TestClient, so each test owns a single event loop (no cross-loop pools).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

# --- Import the API package with a clean cwd so pydantic Settings doesn't
#     choke on the repo-root .env (Streamlit-era vars it rejects as extras) ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_API = os.path.join(_HERE, "..", "api")
if _API not in sys.path:
    sys.path.insert(0, _API)

_prev_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp())
try:
    from app.config import get_settings
    get_settings()  # populate the lru_cache with defaults (no .env in cwd)
    import app.models  # noqa: F401  — register every model for create_all
    from app.database import Base
    from app.models.focus_list import FocusList
    from app.routers import focus_list as fl_router
    from app.services import focus_list_service as svc
finally:
    os.chdir(_prev_cwd)

from fastapi import HTTPException, Response  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from analytics.ai_best_setups import BestSetupsResult  # noqa: E402


# --- Helpers ---------------------------------------------------------------


class _FakeUser:
    def __init__(self, uid: int = 1):
        self.id = uid


def _pick(symbol="AAPL", direction="LONG", conviction="HIGH", timeframe="day"):
    """One engine pick (an EntryCandidate dict)."""
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "setup_type": "VWAP bounce",
        "entry": 100.0,
        "stop": 98.0,
        "t1": 103.0,
        "t2": 106.0,
        "conviction": conviction,
        "confluence": ["PDL 99.5", "rising 20MA"],
        "why_now": "VWAP reclaim holding above PDL",
        "current_price": 100.2,
        "distance_to_entry_pct": 0.2,
    }


def _result(day=None, swing=None, skipped=None, error=None, watchlist_size=3):
    return BestSetupsResult(
        generated_at=datetime.now().isoformat(),
        watchlist_size=watchlist_size,
        day_trade_picks=day or [],
        swing_trade_picks=swing or [],
        skipped=skipped or [],
        error=error,
    )


@contextlib.asynccontextmanager
async def _db(tmp_path):
    """Fresh async SQLite DB for one test — single event loop, disposed at end."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fl.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _patch_engine(monkeypatch, *results):
    """Monkeypatch generate_best_setups to yield the given results in order."""
    seq = iter(results)
    last = results[-1]

    def _fake(uid, factory):
        return next(seq, last)

    monkeypatch.setattr("analytics.ai_best_setups.generate_best_setups", _fake)


# --- Service unit tests: market window classification (FR-003) -------------


class TestClassifyMarketWindow:
    def test_pre_open(self):
        # 09:00 ET (EDT) == 13:00 UTC — before the 09:30 open
        assert svc.classify_market_window(
            datetime(2026, 5, 20, 13, 0, tzinfo=timezone.utc)
        ) == "pre_open"

    def test_pre_close(self):
        # 15:30 ET == 19:30 UTC — inside the last hour before the 16:00 close
        assert svc.classify_market_window(
            datetime(2026, 5, 20, 19, 30, tzinfo=timezone.utc)
        ) == "pre_close"

    def test_other_midday(self):
        # 12:00 ET == 16:00 UTC
        assert svc.classify_market_window(
            datetime(2026, 5, 20, 16, 0, tzinfo=timezone.utc)
        ) == "other"

    def test_other_after_close(self):
        # 17:00 ET == 21:00 UTC
        assert svc.classify_market_window(
            datetime(2026, 5, 20, 21, 0, tzinfo=timezone.utc)
        ) == "other"

    def test_naive_datetime_treated_as_utc(self):
        assert svc.classify_market_window(datetime(2026, 5, 20, 13, 0)) == "pre_open"


# --- Service unit tests: recommendation mapping (FR-008, FR-014) -----------


class TestRecommendationMapping:
    def test_maps_all_fields_and_qualifying_criteria(self):
        rec = svc.entry_candidate_to_recommendation(_pick(), "day_trade")
        assert rec["symbol"] == "AAPL"
        assert rec["trade_horizon"] == "day_trade"
        assert rec["direction"] == "LONG"
        assert rec["conviction"] == "HIGH"
        assert rec["entry"] == 100.0 and rec["stop"] == 98.0
        assert rec["t1"] == 103.0 and rec["t2"] == 106.0
        assert rec["why_now"].startswith("VWAP reclaim")
        # FR-014 — qualifying criteria surfaced from existing engine fields
        qc = rec["qualifying_criteria"]
        assert qc["entry_trigger"] == "VWAP bounce"
        assert qc["conviction_drivers"] == ["PDL 99.5", "rising 20MA"]
        assert qc["horizon_fit"] == "day_trade"

    def test_build_orders_day_then_swing_and_tags_horizon(self):
        recs = svc.build_recommendations(
            [_pick("AAPL")], [_pick("MSFT", timeframe="swing")]
        )
        assert [r["symbol"] for r in recs] == ["AAPL", "MSFT"]
        assert recs[0]["trade_horizon"] == "day_trade"
        assert recs[1]["trade_horizon"] == "swing"

    def test_build_handles_empty_and_none(self):
        assert svc.build_recommendations([], []) == []
        assert svc.build_recommendations(None, None) == []


# --- Endpoint tests: persistence + refresh survival (US1) ------------------


def test_run_persists_and_latest_returns_it(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(monkeypatch, _result(day=[_pick()]))

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                payload = await fl_router.run_focus_list(
                    force=False, user=_FakeUser(1), db=s
                )
                await s.commit()
            assert payload["status"] == "has_setups"
            assert payload["runs_today"] == 1
            assert len(payload["recommendations"]) == 1

            # Refresh survival: latest returns the identical list, no AI run.
            async with Session() as s:
                latest = await fl_router.latest_focus_list(_FakeUser(1), s)
            assert latest["id"] == payload["id"]
            assert latest["recommendations"] == payload["recommendations"]
            assert latest["is_stale"] is False

    asyncio.run(_t())


def test_run_empty_watchlist_saves_no_setups(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(monkeypatch, _result(watchlist_size=0))

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                payload = await fl_router.run_focus_list(
                    force=False, user=_FakeUser(1), db=s
                )
                await s.commit()
            assert payload["status"] == "no_setups"
            assert "watchlist" in (payload["message"] or "").lower()
            assert payload["recommendations"] == []

    asyncio.run(_t())


def test_failed_run_preserves_prior_and_skips_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(
        monkeypatch,
        _result(day=[_pick()]),                       # run 1 — good
        _result(error="AI call failed: timeout"),     # run 2 — failed
    )

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                good = await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            async with Session() as s:
                failed = await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            assert failed["status"] == "failed"
            assert failed["runs_today"] == 1  # failed run consumed no quota

            # latest still returns the prior good list — failure never destroys it
            async with Session() as s:
                latest = await fl_router.latest_focus_list(_FakeUser(1), s)
            assert latest["id"] == good["id"]
            assert latest["status"] == "has_setups"

    asyncio.run(_t())


# --- Endpoint tests: quota hard cap + cadence (US3) ------------------------


def test_hard_cap_returns_429_and_reads_still_work(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "free")  # cap = 1
    _patch_engine(monkeypatch, _result(day=[_pick()]))

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            # second run over the free cap
            async with Session() as s:
                with pytest.raises(HTTPException) as ei:
                    await fl_router.run_focus_list(False, _FakeUser(1), s)
            assert ei.value.status_code == 429
            # reads are never quota-gated
            async with Session() as s:
                latest = await fl_router.latest_focus_list(_FakeUser(1), s)
            assert latest["status"] == "has_setups"

    asyncio.run(_t())


def test_cadence_check_blocks_third_run_until_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(monkeypatch, _result(day=[_pick()]))

    async def _t():
        async with _db(tmp_path) as Session:
            for _ in range(2):
                async with Session() as s:
                    await fl_router.run_focus_list(False, _FakeUser(1), s)
                    await s.commit()
            # third run without force — soft cadence pre-check, no scan
            async with Session() as s:
                blocked = await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            assert blocked.get("cadence_check") is True
            assert blocked["runs_today"] == 2
            async with Session() as s:
                hist = await fl_router.focus_list_history(
                    user=_FakeUser(1), db=s
                )
            assert hist["total"] == 2  # no row saved by the blocked run

            # forced third run proceeds
            async with Session() as s:
                forced = await fl_router.run_focus_list(True, _FakeUser(1), s)
                await s.commit()
            assert forced["status"] == "has_setups"
            assert forced["runs_today"] == 3

    asyncio.run(_t())


# --- Endpoint tests: dedicated page reads (US2) ----------------------------


def test_latest_returns_204_for_new_user(tmp_path):
    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                out = await fl_router.latest_focus_list(_FakeUser(99), s)
            assert isinstance(out, Response)
            assert out.status_code == 204

    asyncio.run(_t())


def test_history_is_newest_first_and_includes_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(
        monkeypatch,
        _result(day=[_pick()]),                    # older — good
        _result(error="AI call failed: timeout"),  # newer — failed
    )

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            async with Session() as s:
                await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            async with Session() as s:
                hist = await fl_router.focus_list_history(user=_FakeUser(1), db=s)
            assert hist["total"] == 2
            assert hist["items"][0]["status"] == "failed"  # newest first
            assert hist["items"][0]["recommendation_count"] == 0
            assert hist["items"][1]["status"] == "has_setups"

    asyncio.run(_t())


def test_detail_404_for_missing_or_other_users_list(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(monkeypatch, _result(day=[_pick()]))

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                created = await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            # owner can read it
            async with Session() as s:
                got = await fl_router.focus_list_detail(created["id"], _FakeUser(1), s)
            assert got["id"] == created["id"]
            # another user gets 404 (existence not leaked)
            async with Session() as s:
                with pytest.raises(HTTPException) as ei:
                    await fl_router.focus_list_detail(created["id"], _FakeUser(2), s)
            assert ei.value.status_code == 404
            # missing id → 404
            async with Session() as s:
                with pytest.raises(HTTPException) as ei2:
                    await fl_router.focus_list_detail(999999, _FakeUser(1), s)
            assert ei2.value.status_code == 404

    asyncio.run(_t())


# --- Endpoint tests: window labelling (US3) --------------------------------


def test_run_labels_market_window(tmp_path, monkeypatch):
    monkeypatch.setattr(fl_router, "get_user_tier", lambda u: "pro")
    _patch_engine(monkeypatch, _result(day=[_pick()]))
    # 13:00 UTC == 09:00 ET → pre_open
    monkeypatch.setattr(fl_router, "utcnow", lambda: datetime(2026, 5, 20, 13, 0))

    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                payload = await fl_router.run_focus_list(False, _FakeUser(1), s)
                await s.commit()
            assert payload["market_window"] == "pre_open"

    asyncio.run(_t())


# --- Retention: 30-day prune-on-write -------------------------------------


def test_save_focus_list_prunes_lists_older_than_30_days(tmp_path):
    async def _t():
        async with _db(tmp_path) as Session:
            async with Session() as s:
                await svc.save_focus_list(
                    s, user_id=1,
                    generated_at=svc.utcnow() - timedelta(days=40),
                    session_date="2026-04-10", market_window="other",
                    status="has_setups", watchlist_size=1,
                    recommendations=[], skipped=[], message=None,
                )
                await s.commit()
            async with Session() as s:
                await svc.save_focus_list(
                    s, user_id=1,
                    generated_at=svc.utcnow(),
                    session_date=svc.et_today(), market_window="other",
                    status="has_setups", watchlist_size=1,
                    recommendations=[], skipped=[], message=None,
                )
                await s.commit()
            async with Session() as s:
                rows = (await s.execute(
                    select(FocusList).where(FocusList.user_id == 1)
                )).scalars().all()
            assert len(rows) == 1  # the 40-day-old list was pruned
            assert rows[0].session_date == svc.et_today()

    asyncio.run(_t())
