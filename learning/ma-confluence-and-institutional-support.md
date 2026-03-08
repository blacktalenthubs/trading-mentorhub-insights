# Learning: MA Confluence Detection & Institutional Support

## Date: 2026-03-03

## Real-World Evidence (Today's Session)

| Symbol | What Happened | Alerts Fired | What Was Missing |
|--------|---------------|-------------|------------------|
| LRCX | 50MA + horizontal support at ~$217, double-bottom bounce | `session_low_double_bottom`, `intraday_support_bounce` | No mention of 50MA at same level |
| NVDA | Weekly level $177 + 50MA confluence | `weekly_level_touch`, `intraday_support_bounce` | No MA confluence flag |
| TSLA | Below 20MA/50MA, those became resistance overhead | `ma_bounce_200` | No "MA flipped to resistance" awareness |
| SPY | 200MA institutional floor, all shorter MAs stacked as resistance | `ma_bounce_100` | Missing institutional significance weighting |

## Current Implementation Analysis

### MA Bounce Rules (BUY — MA as Support)

| Rule | File:Line | Uptrend Required? | Proximity | Stop Offset |
|------|-----------|-------------------|-----------|-------------|
| `check_ma_bounce_20` | intraday_rules.py:159 | YES (`ma20 > ma50`) | 0.3% | 0.5% |
| `check_ma_bounce_50` | intraday_rules.py:213 | NO (uses `prior_close > ma50` instead) | 0.3% | 0.5% |
| `check_ma_bounce_100` | intraday_rules.py:266 | NO | 0.5% | per config |
| `check_ma_bounce_200` | intraday_rules.py:315 | NO | 0.8% | per config |

**Key finding on MA20 bounce:** Requires `ma20 > ma50` (L177). This is correct — in a downtrend the 20MA is more likely resistance, so gating to uptrend makes sense. **Keep this as-is.**

**Key finding on MA50 bounce:** Uses `prior_close > ma50` guard (L230) — if prior close was already below MA50, it skips (breakdown not pullback). This is **more nuanced** than a simple uptrend filter. It allows bounces in neutral markets but blocks broken-MA scenarios. **This is actually reasonable**, but it missed LRCX because LRCX's prior close was below 50MA (it had already broken down then bounced intraday).

### MA Resistance Rule (SELL)

`check_ma_resistance` at L1453: Iterates 20→50→100→200, fires on **lowest rejecting MA**. Bar high near MA + close below MA. Straightforward, no gaps here.

### Horizontal Level BUY Alerts (need confluence enrichment)

These fire at specific price levels that could coincide with an MA:

| Rule | File:Line | Level Source | Entry Based On |
|------|-----------|-------------|----------------|
| `intraday_support_bounce` | L949 | Intraday detected supports | Support level |
| `session_low_double_bottom` | L1024 | Session low (bars min) | Session low |
| `prior_day_low_reclaim` | L364 | Prior day low | Prior day low |
| `planned_level_touch` | L1198 | Scanner entry level | Planned entry |
| `weekly_level_touch` | L1254 | Prior week low | Prior week low |
| `buy_zone_approach` | L1318 | Scanner support zone | Buy zone |
| `ma_bounce_20/50/100/200` | L159-357 | MA values | MA level |

### Data Pipeline: How MAs Reach Rules

```
fetch_prior_day(symbol)     ← analytics/intraday_data.py:95
  └── yfinance 1y history
  └── Computes MA20, MA50, MA100, MA200 on daily closes
  └── Returns dict with keys: ma20, ma50, ma100, ma200

evaluate_rules(symbol, bars, prior_day, ...)    ← intraday_rules.py:1808
  └── Extracts: ma20 = prior_day.get("ma20")  (L1846-1849)
  └── Passes to each rule function individually
  └── Also available at enrichment time (L2264-2287)
```

**All four MA values are already available** in `evaluate_rules` scope. No new data fetching needed.

### Enrichment Phase: Where Confluence Fits

The enrichment phase (L2263-2454) already:
- Applies structural stops (session low for MA bounces)
- Caps risk per symbol
- Finds smart resistance targets
- Adds volume/RS/regime/VWAP context
- Computes score via `_score_alert()`

**Confluence check should go here** — after all BUY signals are collected but before scoring. This way:
1. All signals exist (can check any BUY alert for MA proximity)
2. MAs are in scope (`ma20`, `ma50`, `ma100`, `ma200` are local vars)
3. Score boost can be applied at scoring time

## Implementation Design

### 1. Confluence Utility Function

```python
CONFLUENCE_BAND_PCT = 0.005  # 0.5% — MA within this % of entry = confluence

def _check_ma_confluence(
    entry: float,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
) -> tuple[bool, str, str]:
    """Check if any MA is near the alert's entry level.

    Returns (has_confluence, ma_label, ma_value_str).
    Prioritizes higher MAs (200 > 100 > 50 > 20) since they're
    more significant institutional levels.
    """
    # Check in reverse order: 200MA first (most significant)
    for label, ma in [("200MA", ma200), ("100MA", ma100), ("50MA", ma50), ("20MA", ma20)]:
        if ma is None or ma <= 0:
            continue
        proximity = abs(entry - ma) / ma
        if proximity <= CONFLUENCE_BAND_PCT:
            return True, label, f"${ma:.2f}"
    return False, "", ""
```

**Insertion point:** After BUY signals are collected, inside the enrichment loop (around L2268).

**Skip self-MA confluence:** If a signal is `ma_bounce_50`, don't flag "50MA confluence" on itself. Map:
```python
_MA_SELF_LABELS = {
    AlertType.MA_BOUNCE_20: "20MA",
    AlertType.MA_BOUNCE_50: "50MA",
    AlertType.MA_BOUNCE_100: "100MA",
    AlertType.MA_BOUNCE_200: "200MA",
}
```

### 2. AlertSignal Dataclass Changes

Add two fields:
```python
confluence: bool = False
confluence_ma: str = ""  # e.g., "50MA", "200MA"
```

### 3. Enrichment Integration (in evaluate_rules enrichment loop)

```python
for sig in signals:
    if sig.direction == "BUY" and sig.entry:
        self_ma = _MA_SELF_LABELS.get(sig.alert_type, "")
        has_conf, ma_label, ma_val = _check_ma_confluence(
            sig.entry, ma20, ma50, ma100, ma200,
        )
        if has_conf and ma_label != self_ma:
            sig.confluence = True
            sig.confluence_ma = ma_label
            sig.message += f" | {ma_label} confluence at {ma_val} — institutional support"
            if sig.confidence == "medium":
                sig.confidence = "high"
```

### 4. Score Boost

In `_score_alert()` or after the scoring call:
```python
if sig.confluence:
    sig.score = min(100, sig.score + 10)
```

### 5. MA50 Bounce Relaxation

Current guard at L230:
```python
if prior_close is not None and prior_close <= ma50:
    return None  # was already below — this is breakdown, not pullback
```

**Change to:** Still allow the bounce but downgrade confidence:
```python
counter_trend = prior_close is not None and prior_close <= ma50
# Don't skip — 50MA is institutional, bounces happen from below too

# ... (existing proximity/close checks) ...

confidence = "medium" if counter_trend else ("high" if proximity <= 0.001 else "medium")
msg_suffix = " (counter-trend)" if counter_trend else ""
```

This captures the LRCX scenario: prior close was below 50MA, but intraday it bounced off it.

### 6. MA Role-Flip Tracking

Lightweight approach — no new state needed. Check if close is below MA in `prior_day`:

```python
def _recently_broken_ma(
    close: float,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
) -> list[str]:
    """Return list of MA labels that were recently broken (close below MA)."""
    broken = []
    for label, ma in [("20MA", ma20), ("50MA", ma50), ("100MA", ma100), ("200MA", ma200)]:
        if ma is not None and ma > 0 and close < ma:
            broken.append(label)
    return broken
```

Use in `check_ma_resistance` enrichment: if an MA was recently broken (prior close below it), boost the resistance signal:
```python
sig.message += f" | {ma_label} recently broken — acting as resistance"
```

## Edge Cases

1. **Self-confluence:** MA bounce 50 should NOT flag "50MA confluence" — handled by `_MA_SELF_LABELS` skip
2. **Multiple MA confluence:** If both 50MA and 100MA are near entry, report the highest (200 > 100 > 50 > 20)
3. **MA near overhead resistance:** If MA is above entry but within confluence band, it's resistance not support — skip (only count MAs at or below entry)
4. **Stale MAs:** MA values come from prior day close; intraday they shift slightly. The 0.5% band accounts for this

## Files to Modify

| File | Changes |
|------|---------|
| `analytics/intraday_rules.py` | Add `_check_ma_confluence()`, add confluence fields to `AlertSignal`, integrate in enrichment loop, relax MA50 guard, add role-flip enrichment |
| `alert_config.py` | Add `CONFLUENCE_BAND_PCT = 0.005` |
| `alerting/telegram_formatter.py` | Show confluence tag in Telegram messages (if exists) |

## Verification Plan

1. **Unit test:** `_check_ma_confluence()` with known values — verify proximity math
2. **Unit test:** MA50 bounce fires when prior_close < ma50 (counter-trend)
3. **Replay test:** Replay LRCX 2026-03-03 bars — `session_low_double_bottom` should get "50MA confluence" tag
4. **Replay test:** Replay NVDA 2026-03-03 — `weekly_level_touch` should get MA confluence tag
5. **Build test:** All existing tests pass
