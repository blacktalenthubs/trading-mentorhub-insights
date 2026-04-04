# Plan: Intraday Regime Narrator + Alert Clustering Intelligence

## Problem Statement

Two real-time AI features are missing from the alert pipeline:

1. **Intraday Regime Narrator** — When SPY regime flips mid-session (e.g., TRENDING_UP → PULLBACK), push a 2-3 sentence AI interpretation via Telegram. Currently regime changes happen silently — the trader has to notice them manually.

2. **Alert Clustering Intelligence** — When 2+ BUY alerts fire for the same symbol within a poll cycle (`_consolidate_signals` already detects this), send the cluster to Claude for a synthesis narrative. Currently consolidation just appends "+2 confirming: Type1, Type2" — no interpretation of why the confluence matters.

---

## Solution Architecture

```
┌────────────────────────────────────────────────────────────┐
│  monitor.py — poll_cycle()                                  │
│                                                             │
│  1. get_spy_context() → spy_ctx                            │
│  2. Compare spy_ctx["regime"] to _last_regime (in-memory)  │
│     If changed → regime_narrator.narrate_regime_shift()    │
│     → Telegram push                                         │
│                                                             │
│  3. evaluate_rules() per symbol → signals                  │
│  4. _consolidate_signals(signals) → consolidated           │
│  5. For each consolidated signal with confluence:          │
│     cluster_narrator.narrate_cluster() → append narrative  │
│     (reuse signal.narrative field — replaces default)      │
└────────────────────────────────────────────────────────────┘
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `analytics/regime_narrator.py` | Detect regime flips, generate AI interpretation, send Telegram |
| `analytics/cluster_narrator.py` | Generate AI synthesis for consolidated multi-signal clusters |

## Files to Modify

| File | Change |
|------|--------|
| `monitor.py` | Hook regime narrator (after spy_ctx fetch) + cluster narrator (after consolidation) |
| `alert_config.py` | Feature flags for both features |

---

## Implementation Details

### Feature 1: Intraday Regime Narrator (`analytics/regime_narrator.py`)

**Pattern:** Follows `eod_review.py` and `premarket_brief.py` — standalone module with `_resolve_api_key()`, system prompt, and `_send_telegram()`.

**State:** Module-level `_last_regime: str | None` and `_last_regime_session: str` — tracks last known regime per session. Resets on new session.

**Trigger:** Called every poll cycle from `monitor.py`. Only fires Claude + Telegram when regime actually changes.

**Dedup:** Max 4 regime narrations per session (prevent noisy flip-flopping in choppy markets).

**Claude prompt context:**
- Previous regime → new regime
- SPY price, MAs (20/50/200), RSI, EMA spread
- Intraday change %, session phase
- Whether SPY is at support/resistance

**Output:** 2-3 sentence plain-text Telegram push.

**Model:** Haiku (fast, cheap — this fires during market hours potentially multiple times).

### Feature 2: Alert Clustering Intelligence (`analytics/cluster_narrator.py`)

**Pattern:** Follows `narrator.py` — generates a narrative string that gets attached to the signal.

**Trigger:** In `monitor.py`, after `_consolidate_signals()` produces a signal with `confluence=True` or message containing `[+N confirming:]`. Instead of the default narrator, use the cluster narrator which gets the full list of confirming signal types.

**Claude prompt context:**
- Symbol, current price
- Primary signal (type, entry, stop, targets)
- All confirming signal types and their messages
- SPY regime, VWAP position, volume
- Why confluence matters at this specific price level

**Output:** 3-4 sentence synthesis replacing the default narrative.

**Model:** Haiku for score < 65, Sonnet for score >= 65 (same as narrator.py).

---

## Hook into monitor.py

### Regime Narrator (after SPY context fetch, before symbol loop):
```python
if REGIME_NARRATOR_ENABLED:
    check_regime_shift(spy_ctx)
```

### Cluster Narrator (replace default narrative for consolidated signals):
```python
if CLUSTER_NARRATOR_ENABLED and signal.confluence:
    signal.narrative = narrate_cluster(signal, confirming_types)
```

---

## Config Additions (alert_config.py)

```python
REGIME_NARRATOR_ENABLED = True
REGIME_NARRATOR_MAX_PER_SESSION = 4
CLUSTER_NARRATOR_ENABLED = True
```
