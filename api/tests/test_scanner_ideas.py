"""Tests for feeding conviction / long-term ideas into the Today scan.

Covers the two pieces of logic added to the scanner that don't need a live DB:
  - meets_entry(): the entry gate idea-sourced names must clear.
  - _gather_idea_symbols(): builds the extra scan universe from the latest
    conviction + swing snapshots (dedup, exclude watchlist, cap).
Full HTTP integration is exercised against the deployment, like the rest of
the screener suite.
"""

from __future__ import annotations

import asyncio

from app.services.scanner import idea_qualifies, meets_entry
import app.routers.scanner as scanner


class _Snap:
    """Minimal stand-in for a ScreenerSnapshot (only .entries is read)."""

    def __init__(self, entries):
        self.entries = entries


def test_meets_entry_gate():
    # "Potential Entry" == AT SUPPORT + score >= 65 (the strict, at-entry gate).
    assert meets_entry({"action_label": "Potential Entry"}) is True
    assert meets_entry({"action_label": "Watch"}) is False
    assert meets_entry({}) is False


def test_idea_qualifies_gate():
    # Looser gate for idea-sourced names: at entry OR approaching, but not broken.
    assert idea_qualifies({"action_label": "Potential Entry"}) is True
    assert idea_qualifies({"action_label": "Watch"}) is True
    assert idea_qualifies({"action_label": "No Setup"}) is False
    assert idea_qualifies({}) is False


def test_gather_idea_symbols_dedup_exclude(monkeypatch):
    snaps = {
        "conviction": _Snap([{"symbol": "NVDA"}, {"symbol": "aaoi"}, {"symbol": "PLTR"}]),
        "swing": _Snap([{"symbol": "AAOI"}, {"symbol": "RKLB"}, {"symbol": ""}, {"symbol": "MU"}]),
    }

    async def fake_latest(kind):
        return snaps.get(kind)

    monkeypatch.setattr(scanner, "get_latest_snapshot", fake_latest)

    # NVDA + PLTR are already on the watchlist → excluded.
    result = asyncio.run(scanner._gather_idea_symbols(exclude={"NVDA", "PLTR"}))

    # AAOI is in both snapshots → conviction wins (listed first). Symbols are
    # upper-cased; the empty entry is skipped.
    assert result == {"AAOI": "conviction", "RKLB": "long_term", "MU": "long_term"}
    assert "NVDA" not in result and "PLTR" not in result and "" not in result


def test_gather_idea_symbols_respects_cap(monkeypatch):
    big = _Snap([{"symbol": f"S{i}"} for i in range(50)])

    async def fake_latest(kind):
        return big if kind == "conviction" else None

    monkeypatch.setattr(scanner, "get_latest_snapshot", fake_latest)

    result = asyncio.run(scanner._gather_idea_symbols(exclude=set()))
    assert len(result) == scanner._MAX_IDEA_SYMBOLS


def test_gather_idea_symbols_empty_when_no_snapshots(monkeypatch):
    async def fake_latest(kind):
        return None

    monkeypatch.setattr(scanner, "get_latest_snapshot", fake_latest)
    assert asyncio.run(scanner._gather_idea_symbols(exclude=set())) == {}
