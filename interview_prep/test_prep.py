"""Sanity tests for the interview prep tracker. Run: python3 -m pytest interview_prep -v"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import store  # noqa: E402
from curriculum import TRACKS, all_items  # noqa: E402


def test_curriculum_ids_are_unique_and_well_formed():
    items = all_items()
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids)), "duplicate item ids"
    for it in items:
        track, topic, n = it["id"].split(".")
        assert track == it["track"]
        assert topic == it["topic"]
        assert n.isdigit()


def test_every_topic_has_checks_and_content():
    for track_id, track in TRACKS.items():
        expected = 5 if track_id == "system_design" else 3
        for topic in track["topics"]:
            assert len(topic["items"]) == expected, topic["id"]
            assert topic["priority"] in {"high", "medium", "low"}, topic["id"]
            assert topic["teleprompter"].strip(), topic["id"]
            assert topic["template"].strip(), topic["id"]


def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "PROGRESS_PATH", tmp_path / "p.json")
    data = store.load()
    assert data == {"items": {}, "log": []}

    store.set_done(data, "coding.two_sum.1", True)
    store.set_confidence(data, "coding.two_sum.1", 3)
    store.set_notes(data, "coding.two_sum.notes", "hashmap")
    store.save(data)

    again = store.load()
    assert store.is_done(again, "coding.two_sum.1")
    assert store.get_item(again, "coding.two_sum.1")["confidence"] == 3
    assert store.get_item(again, "coding.two_sum.notes")["notes"] == "hashmap"
    assert again["log"][0]["action"] == "done"


def test_set_done_is_idempotent():
    data = {"items": {}, "log": []}
    store.set_done(data, "x", True)
    store.set_done(data, "x", True)
    assert len(data["log"]) == 1
    store.set_done(data, "x", False)
    assert len(data["log"]) == 2
    assert data["items"]["x"]["done_at"] is None


def test_streak_counts_consecutive_days():
    today = date(2026, 9, 26)
    data = {"items": {}, "log": []}
    assert store.streak(data, today) == 0
    for d in ("2026-09-24", "2026-09-25", "2026-09-26"):
        data["log"].append({"date": d, "item_id": "a", "action": "done"})
    assert store.streak(data, today) == 3
    # Yesterday counts, so a missed today does not break the streak yet.
    assert store.streak(data, date(2026, 9, 27)) == 3
    assert store.streak(data, date(2026, 9, 28)) == 0


def test_load_survives_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "p.json"
    p.write_text("{not json")
    monkeypatch.setattr(store, "PROGRESS_PATH", p)
    assert store.load() == {"items": {}, "log": []}


@pytest.mark.parametrize("track_id", list(TRACKS))
def test_track_has_goal_and_cadence(track_id):
    t = TRACKS[track_id]
    assert t["goal"] and t["cadence"] and t["icon"]
