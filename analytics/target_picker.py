"""Unified single-target picker — Sub-spec A (#64 Launch Value Master).

One target per entry, chosen from the chart stack the Pine already sends in the
`nearby_levels` payload field. Targets are NEVER R-multiples — price moves to the
next level, or until momentum exhausts, or it simply runs for the session. So a
target is one of three KINDS:

  - "level": the nearest clustered level/EMA above (long) / below (short) the entry
             — the first real resistance/support the trade can reach.
  - "rsi":   no level in that direction (blue sky / gap-and-go) → momentum target
             RSI 70 (or 80 when already strong-momentum, RSI >= 70). A valid,
             riskier setup, not a downgrade.
  - "eod":   no level and RSI unavailable → exit end-of-day.

Pure + deterministic so it unit-tests without a Pine round-trip (NFR-2). The caller
(tv_webhook) supplies entry, the parsed candidate prices, the direction, and the
daily RSI; this module owns the selection rules only.

Rules (Sub-spec A):
  - SKIP anything within ~0.3% of the entry — that's the level you're trading AT.
  - CLUSTER candidates within ~1% of the chosen target into one "wall"; wall_size
    feeds the grade (a wall is a stronger, stickier target than a lone level).
  - ONE target only (no T1/T2).
"""

from __future__ import annotations

from typing import Iterable, Optional, Union

SKIP_PCT = 0.003   # skip levels within 0.3% of entry (the level you're entering AT)
WALL_PCT = 0.01    # candidates within 1% of the target merge into one "wall"
STRONG_RSI = 70.0  # at/above this on a long, the momentum target steps 70 -> 80

# A candidate is either a bare price, or a (label, price) pair.
Candidate = Union[float, int, tuple, list]


def parse_nearby_levels(csv: Optional[str]) -> list[tuple[str, float]]:
    """Parse the Pine `nearby_levels` CSV into [(label, price), ...].

    Format (from build_payload_v2 / spec 58): "kind|value|label,kind|value|label".
    Bad/blank entries are skipped, never raised.
    """
    out: list[tuple[str, float]] = []
    if not csv:
        return out
    for item in csv.split(","):
        parts = item.split("|")
        if len(parts) < 2:
            continue
        try:
            value = float(parts[1])
        except (ValueError, TypeError):
            continue
        label = parts[2] if len(parts) > 2 and parts[2] else parts[0]
        out.append((label, value))
    return out


def _normalize(candidates: Iterable[Candidate]) -> list[tuple[Optional[str], float]]:
    norm: list[tuple[Optional[str], float]] = []
    for c in candidates or []:
        if isinstance(c, (int, float)):
            norm.append((None, float(c)))
        elif isinstance(c, (tuple, list)) and len(c) >= 2:
            try:
                norm.append((c[0], float(c[1])))
            except (TypeError, ValueError):
                continue
    return norm


def pick_target(
    entry: Optional[float],
    candidates: Iterable[Candidate],
    direction: str = "BUY",
    rsi: Optional[float] = None,
) -> Optional[dict]:
    """Pick the single target for an entry.

    Returns ``{"value", "kind", "label", "wall_size"}`` or ``None`` if entry is invalid.
      - kind "level": value is a price; wall_size = candidates clustered within ~1%.
      - kind "rsi":   value is an RSI level (70/80 long, 30 short); wall_size 0.
      - kind "eod":   value is None (exit end-of-day); wall_size 0.
    """
    if entry is None or entry <= 0:
        return None

    is_long = direction in ("BUY", "LONG")
    norm = _normalize(candidates)

    if is_long:
        side = [(lbl, p) for (lbl, p) in norm if p > entry * (1.0 + SKIP_PCT)]
        side.sort(key=lambda x: x[1])             # nearest above first
    else:
        side = [(lbl, p) for (lbl, p) in norm if p < entry * (1.0 - SKIP_PCT)]
        side.sort(key=lambda x: -x[1])            # nearest below first

    if side:
        label, target = side[0]
        wall = [p for (_, p) in side if abs(p - target) / target <= WALL_PCT]
        return {
            "value": round(target, 2),
            "kind": "level",
            "label": label,
            "wall_size": len(wall),
        }

    # Case B — no level in that direction (blue sky / gap-and-go / breakdown).
    if rsi is not None:
        if is_long:
            tgt = 80.0 if rsi >= STRONG_RSI else 70.0
        else:
            tgt = 30.0  # short momentum target = oversold
        return {"value": tgt, "kind": "rsi", "label": f"RSI {int(tgt)}", "wall_size": 0}

    return {"value": None, "kind": "eod", "label": "EOD", "wall_size": 0}
