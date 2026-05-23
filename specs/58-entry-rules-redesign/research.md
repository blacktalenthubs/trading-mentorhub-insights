# Research — Spec 58 Implementation Decisions

**Date**: 2026-05-22
**Status**: Complete — all `[NEEDS CLARIFICATION]` resolved via informed defaults grounded in tonight's live data validation.

Decisions are formatted: **Decision · Rationale · Alternatives considered**.

---

## R1. Where does confluence data come from — Pine payload or server-side recompute?

**Decision**: **Pine payload.** `ma_ema_daily.pine` already has every level (PDH/PDL/PWH/PWL/PMH/PML, all 7 daily MAs, the MTD AVWAP we built tonight). Include them in the alert webhook JSON as a `nearby_levels` array. The webhook compares the alert's `entry` against each level for confluence detection (within the configured band).

**Rationale**:
- Pine already computes these levels every bar — zero extra cost to attach them to the payload.
- Server-side recompute would add a yfinance round-trip (~1s latency, plus a failure mode if yfinance rate-limits or returns stale data).
- The contract becomes self-describing: every alert carries its own confluence context. Easier to debug, easier to audit in the DB.

**Alternatives considered**:
- *Webhook recomputes via yfinance.* Adds latency + dependency. Rejected.
- *Backend caches the most recent levels per symbol and matches by symbol+timestamp.* Cache-invalidation complexity. Rejected.

---

## R2. Confluence price band — what percentage?

**Decision**: **1.0%** of the alert's entry price. Two levels within 1% of each other (and within 1% of the entry) count as confluent.

**Rationale (validated 2026-05-22 live)**:
- **AVGO**: daily 21 EMA $413.02 vs PDL $410.50 — **0.61% spread**. Within band, correctly flags confluence.
- **AAOI**: daily 21 EMA $171.47 vs weekly 21 EMA (~$170-172) vs MTD AVWAP $180.28 — the EMA cluster is well under 1%; the MTD AVWAP is ~5% above (outside band) — annotation would correctly list the two daily EMAs only, not the AVWAP (which is the next *target*, not confluent support).
- 2% would over-cluster (NVDA had MTD at $217 and PM at $205 — 5.6% apart, not really the same level).
- 0.5% would miss the AVGO case (0.61% spread).

**Implementation**: surfaced as a Python constant `CONFLUENCE_BAND_PCT = 1.0` in `tv_webhook.py`, easy to tune.

**Alternatives considered**: 0.5%, 2%, ATR-relative. All rejected — 1% empirically right, simpler is better.

---

## R3. The ≤ 6 entry rules — exact final list

**Decision**: **4 entry-rule families** (well under the ≤ 6 ceiling, leaves headroom for one more if validated). Each maps to a single `alert_type_config` family:

| # | Rule | Pine alert_type | Trigger | Gate |
|---|------|-----------------|---------|------|
| 1 | **Buy 1 — MA pullback hold** | `ma_bounce_long_v3_*` (per-MA suffix retained) | Day's low tags a key MA, candle closes above it | Uptrend gate (FR-001) |
| 2 | **Buy 2 — Prior-high support hold** | `staged_pdh_held`, `staged_pwh_held`, `staged_pmh_held` (NEW types) | Price was above the prior high, pulls back to it, holds (close ≥ level) | Uptrend gate + higher-high chop gate |
| 3 | **Buy 2 — Prior-low reclaim** | `staged_pdl_reclaim`, `staged_pwl_reclaim`, `staged_pml_reclaim` (existing) | Price lost the prior low intraday then closed back above | Uptrend gate |
| 4 | **HTF support held** | `htf_support_held` (existing) | A long-term level (weekly/monthly) is defended on a pullback | Uptrend gate |

**Retired entry types** (delete from `alert_type_config` or hard-disable):
- `open_reclaimed`, `open_held`, `open_wick_reclaim`, `open_lost` — open-line entries (FR-007)
- `staged_pdh_break`, `staged_pwh_break`, `staged_pmh_break` — breakout-into-resistance entries (FR-005)
- `pullback_long` — generic, replaced by the more specific Buy-1
- `ma_proximity_long_v3_*` — proximity NOTICEs (heads-up, not entries)

**Kept as NOTICE / non-entry** (recorded silently, not part of the ≤ 6 count):
- `htf_proximity` — heads-up only, not an entry trigger
- The four open-line types — keep the Pine *plot* (visual reference), drop the `alertcondition()` calls

**Out of scope (already-existing SHORT family)**: `*_rejection`, `*_failed_short`, `*_break` (PDL/PWL/PML break variants) — SHORT alerts, not covered by spec 58.

**Rationale**: Four families is closer to the user's "5-6" preference and gives a clean mental model (MA bounce / prior-high held / prior-low reclaim / HTF held). Each is a distinct setup with distinct math. The retirement list is explicitly justified by FR-005 (dual-role) and FR-007 (no open-line entries).

**Alternatives considered**:
- *Six families* (split MA into per-MA rules). Rejected — per-MA is a *suffix* of one family, not separate rules.
- *Three families* (drop HTF). Rejected — HTF support held is meaningfully different (longer-term defense) and validated by past performance.

---

## R4. Higher-high chop gate — concrete definition

**Decision**: A Buy-2 (continuation) alert fires only if the current bar's high equals or exceeds the running session high made at least once in the **last 30 minutes of the trading session**. Implementation in Pine: track `lastNewHighBar`; require `(time - time[lastNewHighBarOffset]) <= 30 * 60 * 1000`. If 30 minutes pass without a new session high, no further Buy-2 fires until a new high prints.

**Rationale**:
- "Stopped making new highs" needs a concrete timeout. 30 minutes is the smallest unit a discretionary trader naturally re-checks the tape.
- Empirically (INTC chart from earlier session research): INTC made its session high on bar 5, then 21 bars without a new high — the chop began ~30-45 minutes after the last new high. 30 min catches the inflection.
- Tighter (15 min) cuts too aggressively in slow tapes. Looser (60 min) lets late-session chop through.

**Buy-1 (MA bounce) is NOT subject to this gate** — pullback-to-MA is a setup that can fire in chop, the *MA itself* is the proof of trend continuation.

**Alternatives considered**: bar-count instead of time (rejected — TF-dependent), no gate (rejected — fails FR-006), 15/60 min variants.

---

## R5. MTD AVWAP — Pine or server?

**Decision**: **Pine**. `ma_ema_daily.pine` accumulates the MTD AVWAP using the same logic as `anchored_vwap_manual.pine` (built tonight): reset on month change, accumulate `hlc3 * volume` and `volume`. The value is included in the alert payload as `mtd_avwap`.

**Rationale**:
- We just built this exact computation in Pine tonight — proven to work.
- Server-side would need yfinance + a separate AVWAP routine + month-boundary tracking. Duplicates Pine work for no benefit.
- Pine has the freshest data (tick-level on TradingView's servers); yfinance lags by minutes.

**Alternatives considered**: server-side compute (rejected — duplication + latency).

---

## R6. New Pine alert message format

**Decision**: The Pine `alert()` JSON payload gains:

```json
{
  "rule_name": "ma_bounce_long_v3",       // existing
  "ma_tag": "ema21",                       // existing (used for per-MA dedup)
  "symbol": "AAOI",                        // existing
  "direction": "BUY",                      // existing
  "entry": 171.47,                         // existing
  "stop": 166.66,                          // existing
  "target_1": 177.96,                      // existing
  "target_2": 200.11,                      // existing
  "uptrend_pass": true,                    // NEW — did the uptrend gate fire? (true/false)
  "overhead_mas": [],                      // NEW — list of any MA labels above price (empty = clean uptrend)
  "nearby_levels": [                       // NEW — for confluence detection
    { "kind": "ema21",  "value": 171.47, "label": "EMA 21" },
    { "kind": "pdl",    "value": 410.50, "label": "PDL" },
    { "kind": "mtd_avwap", "value": 180.28, "label": "MTD AVWAP" }
    // ... all key MAs + prior-day/week/month H/L + MTD AVWAP
  ],
  "mtd_avwap": 180.28                      // NEW — convenience, also included in nearby_levels
}
```

The webhook strips the entry's own level from `nearby_levels` (so the EMA21 alert doesn't list "confluent with EMA21"), checks the rest against the 1% band, and appends a confluence string to the Telegram message.

**Rationale**: One JSON payload carries the full setup context. The frontend scorecard can later expose the same info (confluence count, overhead MAs) without another lookup.

**Alternatives considered**: separate API endpoint for level fetch (rejected — extra round-trip), denormalize per-level fields (rejected — explodes the schema).

---

## R7. Telegram alert message format

**Decision**: Existing template + one new line per confluence:

```
SWING LONG (MA bounce) — AAOI $181.49
Entry $171.47 · Stop $166.66 · T1 $177.96 · T2 $200.11
Setup: held the EMA 21 — the day's low tagged it and the candle closed back above
Why: 1 of 8 daily MAs defended, zero overhead resistance
Confluence: weekly EMA 21 ($171.20), MTD AVWAP ($180.28)
```

**Rationale**: One line, scannable. The user can decide on conviction at a glance.

---

## R8. Migration strategy — retire alert types

**Decision**: Idempotent `ALTER`-style migration in `api/app/main.py` startup:

```python
# Spec 58 — retire open-line and breakout-into-resistance entry types.
RETIRED_ENTRY_TYPES = (
    "open_reclaimed", "open_held", "open_wick_reclaim", "open_lost",
    "staged_pdh_break", "staged_pwh_break", "staged_pmh_break",
    "pullback_long",
    "ma_proximity_long_v3_ema8", "ma_proximity_long_v3_ema21",
    "ma_proximity_long_v3_ema50", "ma_proximity_long_v3_ema100",
    "ma_proximity_long_v3_ema200", "ma_proximity_long_v3_sma",
)
for at in RETIRED_ENTRY_TYPES:
    await conn.execute(
        text("UPDATE alert_type_config SET enabled = false WHERE alert_type = :at"),
        {"at": f"tv_{at}"},
    )
```

`enabled=false` rather than DELETE so historical alerts in the `alerts` table still resolve their type (no FK orphans), and the UI still shows them under the "retired" filter for EOD review of legacy data.

**Rationale**: Hard-deleting types would orphan thousands of historical alerts. Soft-disable preserves the audit trail and is reversible if any single type proves valuable again. The `_BASE_CATALOG` in `alert_type_config.py` is also updated to set `default_enabled=False` for these types (so a fresh DB doesn't re-enable them).

**Alternatives considered**: DELETE rows (rejected — FK / audit trail concerns); silently skip in the webhook (rejected — DB stays inconsistent with code).

---

## R9. Order of implementation

**Decision**: Pine changes first, then backend. Each Pine alert change can be tested in isolation on the chart before deploying. Backend confluence parsing is a no-op until Pine starts sending `nearby_levels`, so the two halves can ship independently.

**Phased rollout** (per `quickstart.md`):
1. **Phase A — Pine** (deploy 1): uptrend gate added to `ma_ema_daily.pine` + payload augmentation. Webhook unchanged; new payload fields are ignored harmlessly until Phase B.
2. **Phase B — Backend** (deploy 2): `tv_webhook.py` parses `nearby_levels` + `uptrend_pass`, runs confluence detection, appends string. `alert_type_config.py` updated + migration runs. Retired types stop routing.
3. **Phase C — Validation** (1 week): user reads the scorecard, marks ✓/✗. Verifies SC-001 through SC-006.
4. **Phase D — Cleanup** (separate spec or commit): retire `swing_scanner.py`, `swing_quality.py`, and the 9 `swing_*` alert types. Mark spec 56 superseded.

**Rationale**: Forward-compatible payload means no risky big-bang. Either half can roll back independently.

---

## Open items (none — all resolved)

No `[NEEDS CLARIFICATION]` markers remain. All implementation decisions are made and grounded in either tonight's live validation or sound minimal-solution defaults.
