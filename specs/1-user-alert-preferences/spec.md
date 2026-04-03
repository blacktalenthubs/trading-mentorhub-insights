# Feature Specification: User Alert Preferences (Admin-Only)

**Status**: Draft
**Created**: 2026-04-02
**Branch**: 1-user-alert-preferences

## Overview

The admin user can customize which types of alerts are sent to the Telegram group by toggling alert categories on/off and setting a minimum score filter. This controls what the group chat receives — reducing noise so only relevant, high-conviction alerts push to Telegram. All alerts are still recorded to the database and visible on the dashboard regardless of preferences.

This is scoped to admin-only (single user controlling the group feed). Multi-tenant per-user preferences with individual Telegram routing is a separate future ticket.

## Problem Statement

The Telegram group receives every alert the system generates — entry signals, breakouts, shorts, warnings, informational notices. On volatile days this creates 30-50+ alerts, causing fatigue and burying the high-quality signals. The admin needs a way to tune the group feed by category and score without modifying code.

## Functional Requirements

### FR-1: Alert Category Definitions
- The system groups all alert types into user-friendly categories
- Each category has a name, description, and list of underlying alert types
- Categories:

| Category | Description | Alert Types Included |
|----------|-------------|---------------------|
| **Entry Signals** | BUY alerts at support levels | MA bounces (20/50/100/200), EMA bounces, PDL reclaim, PDL bounce, inside day reclaim, session low double bottom, multi-day double bottom, fib retracement bounce, VWAP reclaim, opening low base, morning low retest, session low bounce, session low reversal, planned level touch |
| **Breakout Signals** | Price breaking above key levels | PDH breakout, inside day breakout, outside day breakout, opening range breakout, weekly/monthly high breakout, consolidation breakout (hourly + 15m), first hour high breakout, gap and go |
| **Short Signals** | SHORT entry and rejection alerts | EMA rejection short, hourly resistance rejection short, session high double top, consolidation breakdown, SPY short entry, PDH failed breakout, EMA loss short |
| **Exit Alerts** | Target hits, stop losses, sell warnings | Target 1 hit, target 2 hit, stop loss hit, auto stop out, trailing stop hit |
| **Resistance Warnings** | Approaching or rejected at resistance | Resistance prior high, PDH rejection, hourly resistance approach, MA resistance, EMA resistance, weekly/monthly high resistance/test |
| **Support Warnings** | Breakdown and support loss alerts | Support breakdown, prior day low breakdown, PDL resistance, session low breakdown, morning low breakdown, opening range breakdown, weekly/monthly low breakdown |
| **Swing Trade** | Multi-day swing setups and management | RSI zones, EMA crossovers, 200MA reclaim, pullback to 20EMA, swing targets/stops, MACD crossover, RSI divergence, bull flag, candle patterns |
| **Informational** | Context and market structure | First hour summary, VWAP loss, monthly EMA touch, weekly/monthly level touches, MA approach, hourly consolidation |

- Acceptance: Each alert type maps to exactly one category. No alert type is uncategorized.

### FR-2: Default Preferences
- All categories enabled by default, score filter = 0 (send everything)
- Acceptance: System behavior identical to today until admin changes preferences

### FR-3: Toggle Categories On/Off
- Admin can enable or disable any alert category from the Settings page
- Changes take effect on the next poll cycle (within 3 minutes)
- Acceptance: Disabling "Breakout Signals" stops all breakout alerts from going to the Telegram group. Re-enabling restores them.

### FR-4: Minimum Score Filter
- Admin can set a minimum score threshold (0-100)
- Alerts below the threshold are not sent to Telegram
- Default: 0 (all scores, no filtering)
- Exit Alerts (T1/T2/Stop) bypass the score filter — they always send regardless of score
- Acceptance: Admin sets minimum score to 60. A BUY alert with score 45 is not sent to Telegram. A stop loss hit with score 30 IS sent.

### FR-5: Settings UI
- Admin accesses alert preferences from the Settings page
- Each category shown as a toggle switch with name and description
- Score filter shown as a slider or number input
- Current preferences displayed on load
- Save button persists changes
- Acceptance: Admin can see all categories, toggle them, adjust score filter, save, and see changes reflected on next visit.

### FR-6: Preference-Aware Notification Gate
- Worker loads admin's preferences once per poll cycle
- Before calling `notify()`, checks if alert's category is enabled and score meets threshold
- If filtered out, alert is still recorded to DB but NOT sent to Telegram
- Acceptance: Filtered alert appears in dashboard history with notified_sms=False.

## Non-Functional Requirements

### Performance
- Preference lookup adds less than 50ms to the notification path
- Preferences loaded once per poll cycle, not per-alert

### Reliability
- If preference lookup fails, fall back to sending all alerts (fail-open)

## User Scenarios

### Scenario 1: Admin Reduces Group Noise
**Actor**: Admin (vbolofinde@gmail.com)
**Trigger**: Too many low-quality alerts in the Telegram group
**Steps**:
1. Admin opens Settings page
2. Disables: Informational, Resistance Warnings
3. Sets minimum score to 55
4. Saves
**Expected Outcome**: Group only receives Entry, Breakout, Short, Exit, Support Warning, and Swing alerts with score >= 55. Exit alerts still come through regardless of score. All alerts still visible on dashboard.

### Scenario 2: Alert Fires But Category Disabled
**Actor**: System (worker)
**Trigger**: PDH breakout signal for PLTR
**Steps**:
1. Worker detects PDH breakout
2. Loads admin prefs — Breakout Signals is disabled
3. Alert recorded to DB with notified_sms=False
4. No Telegram message sent
**Expected Outcome**: Alert in dashboard, not in Telegram group.

### Scenario 3: No Preferences Set (First Run)
**Actor**: System (worker)
**Trigger**: First alert after deployment
**Steps**:
1. No preference rows exist in DB
2. Worker uses defaults — all categories enabled, min_score=0
3. All alerts sent normally
**Expected Outcome**: Identical to current behavior. Zero disruption.

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| Alert Category | Grouping of related alert types | id, name, description, alert_types (defined in code) |
| User Alert Category Prefs | Per-user toggle settings | user_id, category_id, enabled |
| Min Alert Score | Per-user minimum score | user_id, min_alert_score (on user_notification_prefs) |

## Success Criteria

- [ ] Admin can toggle alert categories and see changes reflected within one poll cycle
- [ ] Disabling a category eliminates those alerts from Telegram without affecting dashboard
- [ ] Exit alerts (T1/T2/Stop) always delivered regardless of score filter
- [ ] Default behavior (no prefs set) is identical to current system
- [ ] Preference changes survive server restarts (persisted to database)

## Edge Cases

- Admin disables ALL categories: No Telegram alerts, all still in DB/dashboard
- Admin sets score filter to 100: Only perfect-score alerts plus exits
- New alert type added to code: Defaults to enabled (not in any disabled pref row)
- Database error on preference lookup: Fail-open, send all alerts

## Assumptions

- Alert categories are system-defined in alert_config.py
- Only the admin account's preferences control the group Telegram feed
- The worker resolves admin via ADMIN_EMAIL env var
- All alerts are still recorded to DB regardless of preferences

## Constraints

- Must work with both SQLite (local) and Postgres (production)
- Must not slow down the poll cycle
- All alerts still recorded to DB (audit trail)
- Single Notification Channel — group chat only

## Scope

### In Scope
- Alert category definitions and mapping in alert_config.py
- DB table for category preferences + min_score column
- Admin Settings UI with toggles and score slider
- Preference gate in monitor.py poll_cycle

### Out of Scope
- Per-user preferences with individual Telegram routing (separate multi-tenant ticket)
- Per-user watchlists driving different alert sets (multi-tenant)
- Per-symbol preferences (e.g., "only NVDA breakouts")
- Telegram bot commands for managing preferences
- Per-alert-type granularity (categories are the right abstraction)
- Time-based preferences (crypto quiet hours already handled separately)

## Clarifications

_Added during `/speckit.clarify` sessions_
