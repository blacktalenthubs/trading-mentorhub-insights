# Implementation Summary: Multi-Day Double Bottom Alert

**Date:** 2026-03-15
**Ticket:** Alert conviction tuning — capture structural multi-day double bottoms

---

## What was implemented

New `multi_day_double_bottom` alert rule that detects when price tests the same support zone on multiple daily bars and bounces. This captures the structural patterns visible on daily/4H charts that the existing `session_low_double_bottom` (intraday-only) misses.

## Files modified

| File | Change |
|---|---|
| `alert_config.py` | Added 8 constants (`DAILY_DB_*`), added to `ENABLED_RULES` and `BOUNCE_ALERT_TYPES` |
| `analytics/intraday_data.py` | Added `detect_daily_double_bottoms()` — clusters daily bar lows into support zones with 2+ touches |
| `analytics/intraday_data.py` | Added `_safe_daily_double_bottoms()` — error-safe wrapper |
| `analytics/intraday_data.py` | Extended `fetch_prior_day()` return dict with `daily_double_bottoms` field (no new API calls — piggybacks on existing 1y history) |
| `analytics/intraday_rules.py` | Added `MULTI_DAY_DOUBLE_BOTTOM` to `AlertType` enum |
| `analytics/intraday_rules.py` | Added `check_multi_day_double_bottom()` rule function |
| `analytics/intraday_rules.py` | Hooked into `evaluate_rules()` after session_low_double_bottom |
| `tests/test_intraday_rules.py` | Added `TestDetectDailyDoubleBottoms` (10 tests) and `TestMultiDayDoubleBottom` (9 tests) |

## Key design decisions

1. **No new API calls** — `fetch_prior_day()` already fetches 1 year of daily bars; we scan the last 20 completed bars from that existing data
2. **All daily bar lows considered** (not just strict swing lows) — the BTC $70,413 zone isn't a classic swing low on the daily chart but IS structural support tested multiple times
3. **Lower 75% range filter** — excludes trivial dips near highs while allowing volatile assets (crypto) to have wide ranges
4. **Close-based recovery check** — V-shaped recoveries have bars with wicks below the zone even as trend recovers; checking Close instead of Low catches these
5. **Confidence: high** for 3+ touches or volume exhaustion (< 0.8x avg); **medium** for 2 touches

## Validation results

| Symbol | Zones detected | Key zone |
|---|---|---|
| BTC-USD | 4 | **$70,339–$70,654 (3 touches)** — the exact zone from the charts |
| ETH-USD | 5 | $1,922–$1,930 (3 touches) |
| SPY | 5 | $673–$675 (4 touches), $677–$680 (5 touches) |
| AAPL | 5 | $253–$254 (3 touches) |
| NVDA | 5 | $179–$180 (3 touches) |
| TSLA | 5 | $394–$394 (4 touches) |
| META | 4 | $634–$636 (6 touches) |
| GOOGL | 4 | $299–$301 (6 touches) |

## Tests

- **593 tests pass** (19 new + 574 existing)
- `TestDetectDailyDoubleBottoms`: 10 tests covering detection logic
- `TestMultiDayDoubleBottom`: 9 tests covering the alert rule