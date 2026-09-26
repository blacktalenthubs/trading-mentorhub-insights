"""Progress persistence for the interview prep tracker.

Everything is stored in one JSON file (``interview_prep/progress.json``) so it
survives restarts, is easy to back up, and can be committed if you want history.

Schema::

    {
      "items": {
        "<item_id>": {
          "done": true,
          "done_at": "2026-09-26",
          "confidence": 2,        # 1 = shaky, 2 = ok, 3 = can teach it
          "notes": "..."
        }
      },
      "log": [ {"date": "2026-09-26", "item_id": "...", "action": "done"} ]
    }
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

PROGRESS_PATH = Path(
    os.environ.get(
        "INTERVIEW_PREP_PROGRESS",
        Path(__file__).with_name("progress.json"),
    )
)


def _empty() -> dict[str, Any]:
    return {"items": {}, "log": []}


def load() -> dict[str, Any]:
    if not PROGRESS_PATH.exists():
        return _empty()
    try:
        with PROGRESS_PATH.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty()
    data.setdefault("items", {})
    data.setdefault("log", [])
    return data


def save(data: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_PATH.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(PROGRESS_PATH)


def get_item(data: dict[str, Any], item_id: str) -> dict[str, Any]:
    return data["items"].get(item_id, {"done": False, "done_at": None, "confidence": 0, "notes": ""})


def set_done(data: dict[str, Any], item_id: str, done: bool) -> None:
    item = get_item(data, item_id)
    if item["done"] == done:
        return
    item["done"] = done
    item["done_at"] = date.today().isoformat() if done else None
    data["items"][item_id] = item
    data["log"].append(
        {"date": date.today().isoformat(), "item_id": item_id, "action": "done" if done else "undone"}
    )


def set_confidence(data: dict[str, Any], item_id: str, confidence: int) -> None:
    item = get_item(data, item_id)
    item["confidence"] = int(confidence)
    data["items"][item_id] = item


def set_notes(data: dict[str, Any], item_id: str, notes: str) -> None:
    item = get_item(data, item_id)
    item["notes"] = notes
    data["items"][item_id] = item


def is_done(data: dict[str, Any], item_id: str) -> bool:
    return bool(get_item(data, item_id)["done"])


def done_dates(data: dict[str, Any]) -> list[str]:
    """Distinct ISO dates on which at least one item was completed, ascending."""
    return sorted({e["date"] for e in data["log"] if e["action"] == "done"})


def streak(data: dict[str, Any], today: date | None = None) -> int:
    """Consecutive days (ending today or yesterday) with at least one completion."""
    today = today or date.today()
    days = set(done_dates(data))
    if not days:
        return 0
    cursor = today
    if cursor.isoformat() not in days:
        cursor = date.fromordinal(cursor.toordinal() - 1)
        if cursor.isoformat() not in days:
            return 0
    count = 0
    while cursor.isoformat() in days:
        count += 1
        cursor = date.fromordinal(cursor.toordinal() - 1)
    return count
