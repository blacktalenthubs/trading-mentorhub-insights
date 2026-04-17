# Spec 44 — Enforce AI Signal Commitment (Post-Parse WAIT Override)

**Status:** Draft — pending user approval
**Created:** 2026-04-16
**Related:** Spec 39 (signal logic ref), Spec 41 (prompt refactor + amendments 1-5)
**Priority:** Ship before next market open

---

## 1. Problem

On 2026-04-16, the AI day scanner returned **zero LONG trade alerts** for
SPY, NVDA, and ETH-USD during a session where SPY printed a new 52-week
high at $702.78. Every alert was delivered as `AI UPDATE` (Direction: WAIT).

But the AI's own Reason text described valid LONG setups with multiple
confirmations:

| Time (ET) | Symbol | AI UPDATE body | Confirmations per Spec 41 ladder |
|---|---|---|---|
| 13:46 | NVDA $198.36 | "VWAP reclaim with higher low structure from $197.30, volume 1.2x average supports bounce" | (a) higher-low, (c) volume 1.2x, (e) reclaim = **3 = HIGH** |
| 13:46 | SPY $700.88 | "VWAP reclaim after pullback, RSI overbought at 70.2 but price holding above key level with average volume" | (e) reclaim, (c) volume avg, structure hold = **2-3 = MEDIUM/HIGH** |
| 13:51 | NVDA $198.12 | "Price at VWAP support with average volume" | (c) volume avg, at level = **1-2 = LOW/MEDIUM** |
| 13:56 | NVDA $198.21 | "Price holding above VWAP after testing session low $197.30, higher low structure forming, RSI at 68.6 shows underlying strength" | (a) higher-low, at VWAP level, strength = **2 = MEDIUM** |

The user manually recognized these as valid LONG entries and took the
trades. The AI was right about the data — it just wouldn't commit.

### Root Cause

Spec 41 Amendment 4 added an **anti-hedging rule** to the prompt:

> "If your Reason contains 'fire long', 'valid breakout long', 'structure valid',
>  'reclaim valid', you MUST output Direction: LONG."

This relies on the AI self-policing. In practice the AI uses different
phrasing ("supports bounce", "higher low structure forming", "holding above
key level") that bypasses the trigger-phrase list. The AI hedges with RSI
context ("RSI overbought at 70.2 but...") to justify WAIT — directly
contradicting Amendment 3 ("structure beats RSI").

**There is no Python-side enforcement.** The code path is:

```
parse_day_trade_response()  →  direction = "WAIT"
SHORT policy gate            →  no effect (not SHORT)
staleness gate               →  no effect (not LONG)
WAIT branch (line 1272)      →  emits AI UPDATE, skips LONG handling
```

Between parse and the WAIT branch, nothing asks: "did the reason describe
a valid setup while direction says WAIT?"

### Why prompt-only fixes won't work

Spec 41 already has 5 amendments — each adding rules the AI must juggle.
The prompt now contains competing instructions: "fire at durable levels"
vs "session high breakouts are secondary" vs "structure beats RSI" vs
"conviction scales with confirmation" vs "anti-hedging trigger phrases."

When rules conflict, the model picks the safe path (WAIT). More prompt
rules make this worse, not better. **The fix must be in code.**

---

## 2. Goal

Add a **post-parse override gate** in `scan_day_trade()` that detects when
the AI described a valid LONG (or SHORT) setup in its Reason but returned
Direction: WAIT, and overrides the direction to fire the trade alert.

**Philosophy:** The AI already does the hard work — reading bars, identifying
levels, counting confirmations. It just won't commit. Let it analyze; enforce
commitment in code.

---

## 3. Design

### 3.1 WAIT-to-LONG Override Gate

**Location:** `analytics/ai_day_scanner.py`, in `scan_day_trade()`, between
the parse (line 1109) and the SHORT policy gate (line 1114).

**Logic:**

```python
if parsed.get("direction") == "WAIT":
    reason_lower = (parsed.get("reason") or "").lower()

    # Setup keywords that indicate AI identified a valid LONG setup
    LONG_SETUP_SIGNALS = [
        "reclaim",           # VWAP reclaim, MA reclaim
        "bounce",            # PDL bounce, session low bounce, support bounce
        "higher low",        # higher-low structure = bullish
        "holding above",     # holding above VWAP/support = bullish
        "supports",          # "volume supports bounce", "structure supports entry"
        "breakout",          # level breakout (if at PDH/weekly high)
        "flipped support",   # resistance becomes support
        "bull",              # bullish candle/structure
    ]

    # Hedge phrases the AI uses to justify WAIT despite valid setup
    HEDGE_PHRASES = [
        "overbought",        # "RSI overbought" — per amendment 3, not a gate
        "limits upside",     # hedging language
        "limits conviction", # hedging language
        "no confirmed",      # "no confirmed rejection" — but we're looking at LONG
        "yet",               # "no structure yet" — but reason describes structure
    ]

    setup_detected = any(kw in reason_lower for kw in LONG_SETUP_SIGNALS)
    is_hedging = any(kw in reason_lower for kw in HEDGE_PHRASES)

    if setup_detected:
        # Override: AI described a setup but said WAIT
        parsed["direction"] = "LONG"
        parsed["conviction"] = "LOW"  # conservative — user decides
        parsed["_override"] = True    # flag for logging/audit
        logger.info(
            "AI day scan %s: WAIT→LONG override (reason describes setup: %s)%s",
            symbol, reason[:80],
            " [hedging detected]" if is_hedging else "",
        )
```

### 3.2 Why LOW conviction on override

The AI refused to commit — we don't know why beyond the reason text. Setting
LOW conviction:
- Still fires the alert (user sees it)
- Respects users with `min_conviction=medium` (they filter it out)
- Lets the user decide — which is the whole philosophy
- Avoids overcorrecting (we're not sure AI was wrong to hesitate)

### 3.3 SHORT mirror (SPY only)

Same logic for SHORT setups described but returned as WAIT. Apply SHORT
policy immediately after override (non-SPY → RESISTANCE, SPY LOW → RESISTANCE).

```python
SHORT_SETUP_SIGNALS = [
    "rejection",          # PDH rejection, resistance rejection
    "lower high",         # lower-high structure = bearish
    "failing",            # failing at resistance
    "breakdown",          # support breakdown
    "lost vwap",          # lost VWAP = bearish
    "bear",               # bearish candle/structure
]
```

If SHORT signals detected and no LONG signals present → override to SHORT
with LOW conviction. SHORT policy gate then handles SPY-only filtering.

### 3.4 What does NOT trigger override

- Reason is empty or generic ("no setup", "mid-range", "consolidation")
- Reason only mentions RSI without setup language ("RSI neutral at 55")
- Reason describes approaching a level but not at it ("moving toward PDH")
- Direction is already LONG/SHORT/RESISTANCE (override only applies to WAIT)

### 3.5 Entry/Stop/T1 handling on override

If the AI returned WAIT but included Entry/Stop/T1 fields (common when it
hedges), use those values. If missing:
- `entry`: use live price (we're at the level per proximity filter)
- `stop`: leave None (alert fires without stop — user sets manually)
- `t1`/`t2`: leave None

---

## 4. Scope

### Files changed

| File | Change |
|---|---|
| `analytics/ai_day_scanner.py` | Add ~25-line override gate in `scan_day_trade()` after parse, before SHORT policy |
| `tests/test_ai_day_scanner.py` | Add 6-8 tests for override logic |

### NOT changed

- Prompt text (no new amendments — the prompt is fine, it reads data correctly)
- Swing scanner (different pipeline, LONG-only already)
- Best setups (different pipeline, on-demand)
- Alert store, notifier, delivery gates (unchanged)
- Dedup, heartbeat, proximity filter (unchanged)

---

## 5. Test Plan

### Unit tests (add to `tests/test_ai_day_scanner.py`)

| # | Scenario | Input | Expected |
|---|---|---|---|
| 1 | WAIT + "VWAP reclaim with higher low" | direction=WAIT, reason="VWAP reclaim with higher low structure, volume 1.2x" | direction=LONG, conviction=LOW, _override=True |
| 2 | WAIT + "PDL bounce" | direction=WAIT, reason="PDL bounce at $197, RSI overbought limits upside" | direction=LONG, conviction=LOW (hedge detected) |
| 3 | WAIT + "holding above VWAP" | direction=WAIT, reason="price holding above VWAP after session low test" | direction=LONG, conviction=LOW |
| 4 | WAIT + "mid-range, no setup" | direction=WAIT, reason="price mid-range between levels, no structure" | direction=WAIT (no override) |
| 5 | WAIT + "approaching PDH" | direction=WAIT, reason="approaching PDH, RSI at 70" | direction=WAIT (no setup signal, "approaching" not in list) |
| 6 | WAIT + "rejection at PDH" (SPY) | direction=WAIT, reason="PDH rejection with lower high forming" | direction=SHORT → RESISTANCE per SPY policy |
| 7 | LONG already | direction=LONG, reason="PDL bounce confirmed" | direction=LONG (no override needed) |
| 8 | WAIT + empty reason | direction=WAIT, reason="" | direction=WAIT (no override) |

### Manual verification (post-deploy)

1. Run tests: `python3 -m pytest tests/test_ai_day_scanner.py -v`
2. Deploy to Railway during non-market hours
3. Monitor first market session:
   - Check logs for `WAIT→LONG override` entries
   - Compare override rate to total WAIT count (expect ~30-50% override)
   - Verify overridden alerts have valid entry/stop/T1 in Telegram
4. If override rate > 70% — the AI is systematically hedging; consider prompt simplification (separate spec)
5. If override rate < 10% — gate is too conservative; expand keyword list

---

## 6. Rollback Plan

**Env flag:** `WAIT_OVERRIDE_ENABLED` (default `true`).

```python
_WAIT_OVERRIDE = os.environ.get("WAIT_OVERRIDE_ENABLED", "true").lower() == "true"
```

Set `WAIT_OVERRIDE_ENABLED=false` in Railway env to disable instantly.
No redeploy needed (worker reads env at cycle start).

Alternatively: revert commit.

---

## 7. Why This Works

The level-proximity pre-filter (Spec 42) already guarantees the AI is only
called when price is within 0.5% of a key level. If the AI is called AND
describes a setup in its reason, the setup is real — price is at the level,
the AI sees structure, it just won't commit.

This gate is a safety net, not a replacement for AI judgment. It catches
the specific failure mode of "analyzed correctly, committed wrong" that
appeared on 2026-04-16 and likely occurred on prior days undetected.

The conviction is set to LOW so the user still has the final say. Users
with `min_conviction=medium` won't see overridden alerts at all. Power
users who want every level test will see them.

---

## 8. Future Considerations (out of scope for this spec)

- **Telemetry:** log override rate per symbol per day → if a symbol
  consistently gets overridden, the prompt may need symbol-specific tuning
- **Confidence escalation:** if AI said WAIT but reason has 3+ confirmations,
  override to MEDIUM instead of LOW
- **Prompt simplification:** if override rate stays > 50% for a week, the
  prompt has too many competing rules — consider a separate spec to strip
  it down further
- **Swing scanner:** apply same override logic if needed (currently LONG-only
  so less relevant)
