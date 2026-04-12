# Feature Specification: Settings Redesign — User-Controlled Alert Filters

**Status**: Draft
**Created**: 2026-04-12
**Author**: Claude (speckit)
**Priority**: Critical — blocking launch. Users complain about alert noise; backend rate limits are a workaround. User-controlled filters are the real fix.

## Overview

The Settings page has deprecated sections (pattern toggles built for the retired rule engine) and is missing the controls users actually need to manage AI alert volume. This spec redesigns Settings around **user-controlled AI alert filters**, removes dead weight, and fixes the orphaned Position Sizing section.

Core principle: **The user owns their alert volume, not the backend.** Backend caps are a safety net; user preferences are the primary lever.

## Problem Statement

### Noise without agency

Today the stack:
- Free tier: 7 actionable + 3 WAIT Telegram alerts/day (backend rate limit)
- Pro / Trial: unlimited
- No way for a user to say "I only want HIGH conviction" or "no WAITs, ever" or "only SHORT setups"

Result:
- Free users feel spammed at launch (first scan cycle blasts them)
- Pro users get genuinely too many WAITs in choppy sessions (day can fire 20+ WAITs across 5 symbols)
- Backend rate limit is a blunt instrument — it just cuts delivery off, which looks like a bug

### Deprecated settings confuse users

Settings page currently shows:
- **"Trading Patterns"** section — 10+ pattern category toggles + a 0-100 min-score slider. These existed for the rule engine (`alert_type` categories). We've deprecated rule-based alerts (Spec 34 + `RULE_ENGINE_ENABLED=false`), so these toggles do nothing for AI signals.
- **"Position Sizing"** — stores portfolio size + risk% in localStorage, but the Telegram "Took It" handler ignores them and uses hardcoded `$50,000` notional.
- **Notification Channels** shows Email + Push checkboxes, but we have no email alert delivery and no push notification delivery implemented.

Every stale control erodes trust — the user toggles it and nothing happens.

## Goals

1. **Give users a real steering wheel** — conviction filter, WAIT on/off, direction filter, symbol-specific mute
2. **Remove every stale setting** — nothing on the page should be fake
3. **Replace pattern toggles** with controls that match the AI-only model
4. **Make Position Sizing real or remove it** — no half-working features on Settings
5. **Keep the backend rate limit** as a safety net for free tier (belt + suspenders)

## Non-Goals

- Not rebuilding notification preferences database schema from scratch (extend existing `users` table columns)
- Not adding per-symbol alert routing (future — e.g., "only send me ETH alerts")
- Not adding Email or Push delivery (those are separate features; just hide the UI until they exist)

## Current State — Audit

| Section | Purpose | Status | Action |
|---|---|---|---|
| `TelegramSetup` | Link/unlink Telegram | ✅ Works | Keep as-is |
| `NotificationChannels` | Telegram / Email / Push toggles | ⚠️ Email/Push not implemented | Keep Telegram toggle, hide Email + Push until features exist |
| `AlertPreferences` (Trading Patterns) | Rule-engine category toggles + min_score | ❌ Deprecated | Replace entirely with new `AIAlertFilters` |
| `ProfileSection` | Name + password | ✅ Works | Keep |
| `TradingSettings` (Position Sizing) | Portfolio size + risk% | ⚠️ Disconnected | Wire into trade creation OR remove. Per this spec: wire up. |
| `AutoAnalysisToggle` | AI CoPilot auto-analyze | ✅ Works | Keep, minor copy refresh |
| `ThemeToggle` | Dark/light | ✅ Works | Keep |
| `ReferralSection` | Referral code | ✅ Works | Keep |

## Proposed Design

### New section: "AI Alert Filters"

Replaces the deprecated "Trading Patterns" block. Lives in the left column of Settings (where alerts-related content belongs).

Controls, in order of importance:

#### 1. Minimum Conviction (radio)
```
Minimum conviction for Telegram alerts:
  ( ) High only          — tightest filter; only highest-probability signals
  ( ) Medium or higher   — default — balanced
  ( ) All (Low+)         — full AI firehose
```
Stored as `min_conviction` on User: `"low" | "medium" | "high"`. Defaults to `"medium"`.

Scanner consults this before each Telegram send. Drops alert if its conviction < user's threshold.

#### 2. WAIT alerts toggle
```
[✓] Send WAIT alerts
    See what the AI is ignoring. Builds trust, but can be chatty in choppy markets.
```
Stored as `wait_alerts_enabled` on User: boolean. Defaults to `true` for Pro/Trial, `false` for Free on signup.

If off, scanner skips WAIT delivery to that user entirely (ignores the tier-based 3/day WAIT cap since it's zero anyway).

#### 3. Direction filter (multi-select)
```
Alert me on:
  [✓] LONG entries
  [✓] SHORT entries
  [✓] RESISTANCE notices
  [✓] Exit signals (TAKE_PROFITS, EXIT_NOW)
```
Stored as comma-separated `alert_directions` on User: e.g., `"LONG,SHORT,RESISTANCE,EXIT"`. Defaults to all enabled.

Lets a LONG-only trader skip SHORT alerts entirely, etc.

#### 4. Per-symbol mute (Phase 2, not in v1)
Future: "Mute ETH for 1 hour / rest of day / permanently."

### Updated "Notification Channels" section

Remove Email + Push checkboxes. Keep just the Telegram master toggle:

```
Notifications
  [✓] Telegram alerts
      Real-time DM alerts with action buttons.
      [Manage Telegram connection above]
```

If user unchecks Telegram, they stop receiving ALL Telegram alerts (master kill switch). Useful for vacations / weekends.

Stored as existing `telegram_enabled` column (already on User model).

Once email delivery is built, re-add with its own toggle. Same for push. Until then: hidden.

### Reworked Position Sizing

Two options — pick one in implementation:

**Option A (recommended): Wire it up.**
- Keep the UI, but persist to DB (new column `default_portfolio_size`, `default_risk_pct` on User)
- Update `_handle_ack` in `telegram_bot.py` to read these values for the user when opening a RealTrade
- Calculation: `shares = (portfolio_size * risk_pct / 100) / (entry - stop)` — risk-based sizing, not fixed $50k

**Option B: Remove it.**
- Delete from Settings page until we ship risk-based sizing as a proper feature.

Either is acceptable. Option A is a small win for users who care about sizing.

### Data model changes

Add columns to `users` table:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS min_conviction VARCHAR(10) DEFAULT 'medium';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wait_alerts_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS alert_directions VARCHAR(100) DEFAULT 'LONG,SHORT,RESISTANCE,EXIT';
-- Optional (Option A for Position Sizing):
ALTER TABLE users ADD COLUMN IF NOT EXISTS default_portfolio_size REAL DEFAULT 50000;
ALTER TABLE users ADD COLUMN IF NOT EXISTS default_risk_pct REAL DEFAULT 1.0;
```

### Scanner changes

Before any Telegram delivery (LONG / SHORT / RESISTANCE / WAIT / EXIT), the scanner checks the user's preferences:

```python
def _user_wants_alert(user, alert_kind: str, conviction: str) -> bool:
    """alert_kind: 'LONG' | 'SHORT' | 'RESISTANCE' | 'WAIT' | 'EXIT'"""
    if not user.telegram_enabled:
        return False  # master kill switch

    if alert_kind == 'WAIT':
        return user.wait_alerts_enabled

    # Direction filter
    directions = (user.alert_directions or '').split(',')
    if alert_kind not in directions:
        return False

    # Conviction filter (skip for WAIT — no conviction on waits)
    conv_rank = {'low': 1, 'medium': 2, 'high': 3}
    user_min = conv_rank.get(user.min_conviction, 2)
    signal_level = conv_rank.get((conviction or 'medium').lower(), 2)
    if signal_level < user_min:
        return False

    return True
```

Used in:
- LONG delivery loop
- SHORT delivery loop
- RESISTANCE delivery loop
- WAIT delivery loop
- Exit scan delivery loop

Tier-based rate limits still apply AFTER this check. Preference filter is the first gate.

### API changes

Extend existing notification prefs endpoint:

```
GET  /api/v1/settings/notifications → add min_conviction, wait_alerts_enabled, alert_directions
PUT  /api/v1/settings/notifications → accept the same new fields
```

Backward compat: existing `telegram_enabled`, `email_enabled`, `push_enabled` fields stay.

### Frontend changes

Settings page layout after cleanup:

```
[Left column]                         [Right column]
────────────────                      ────────────────
Telegram Alerts                       Account
  (link/unlink)

Notifications                         ProfileSection
  [✓] Telegram
                                      TradingSettings
AI Alert Filters                        Portfolio Size
  Min conviction: [Medium ▼]            Risk per trade: [1%]
  [✓] WAIT alerts
  [✓] LONG  [✓] SHORT
  [✓] RESISTANCE  [✓] EXIT

AI CoPilot
  [✓] Auto-analyze on alert

Appearance
  [✓] Dark mode

────────────────────────────────────────
Referral
  (code + apply)
```

Remove: `AlertPreferences` component entirely.

## User Scenarios

### Scenario 1: Free user overwhelmed
**Actor**: Free tier user on first day, getting many WAITs on ETH
**Steps**:
1. Goes to Settings → AI Alert Filters
2. Unchecks "Send WAIT alerts"
3. Next scan cycle: no more WAITs on Telegram (still visible in dashboard "AI Waits" tab)
4. User keeps the 7/day actionable budget, uses zero of the 3/day WAIT budget
**Outcome**: Clean Telegram, no churn

### Scenario 2: Conservative Pro trader
**Actor**: Pro user, only wants tightest signals
**Steps**:
1. Settings → Minimum Conviction → "High only"
2. Scanner filters out MEDIUM and LOW conviction alerts
3. Their Telegram now only buzzes on textbook HIGH conviction setups
**Outcome**: Higher per-alert signal, lower volume

### Scenario 3: LONG-only trader
**Actor**: User whose strategy is only long setups
**Steps**:
1. Settings → AI Alert Filters
2. Unchecks SHORT and RESISTANCE (keeps LONG + EXIT)
3. Never sees another SHORT alert; still gets exit signals for open LONGs
**Outcome**: Aligned with their style, no noise

### Scenario 4: User removes deprecated section
**Actor**: Existing user who was using "Trading Patterns" to filter
**Migration**:
1. On first load after deploy, `AlertPreferences` component is gone
2. New defaults applied: min_conviction=medium, wait_alerts_enabled=true, all directions on
3. Optional: one-time tooltip "We simplified alert filters — see AI Alert Filters below"

## Functional Requirements

### FR-1: Remove deprecated "Trading Patterns" UI
- [ ] Delete `AlertPreferences` component from `web/src/pages/SettingsPage.tsx`
- [ ] Remove its import and references
- [ ] Keep backend endpoint for now (don't break other users); mark as deprecated in code comments
- Acceptance: Settings page no longer shows pattern toggles or min_score slider

### FR-2: New "AI Alert Filters" section
- [ ] Component renders min_conviction radio, wait_alerts_enabled toggle, direction checkboxes
- [ ] Loads current values from GET `/settings/notifications`
- [ ] Persists via PUT `/settings/notifications` with new fields
- [ ] Shows success toast on save; inline validation for nonsensical states (e.g., unchecking all directions)
- Acceptance: User can set values, reload page, and values persist

### FR-3: Extend data model + migration
- [ ] Add columns `min_conviction`, `wait_alerts_enabled`, `alert_directions` to `User` model (SQLAlchemy)
- [ ] Add `ALTER TABLE` migrations to `api/app/main.py` init block
- [ ] Backfill existing users with defaults (migration handles via `DEFAULT` clause)
- [ ] New signups auto-get defaults (model-level defaults)
- Acceptance: DB schema updated on next deploy; /admin/user-debug shows new fields

### FR-4: Notification preferences API
- [ ] Extend `GET /settings/notifications` response with `min_conviction`, `wait_alerts_enabled`, `alert_directions`
- [ ] Extend `PUT /settings/notifications` to accept + persist these fields
- [ ] Validate inputs: `min_conviction ∈ {low, medium, high}`, `alert_directions` subset of `{LONG, SHORT, RESISTANCE, EXIT}`
- Acceptance: curl the endpoint round-trips correctly

### FR-5: Scanner respects user preferences
- [ ] Add helper `_user_wants_alert(user, alert_kind, conviction)` in `analytics/ai_day_scanner.py`
- [ ] LONG delivery loop: check before sending Telegram
- [ ] SHORT delivery loop: same
- [ ] RESISTANCE delivery loop: same
- [ ] WAIT delivery loop: same (use `wait_alerts_enabled`)
- [ ] Exit scan delivery: check `EXIT` direction preference
- [ ] Tier rate limit still applies after user filter
- Acceptance: User disables WAITs → 0 WAIT messages delivered to them; dashboard still shows

### FR-6: Remove Email + Push from Notification Channels UI
- [ ] UI: show only Telegram toggle (hide Email + Push until features exist)
- [ ] Backend fields (`email_enabled`, `push_enabled`) stay in DB for future
- Acceptance: Settings shows one checkbox under Notifications; no stale Email/Push prompts

### FR-7 (optional): Wire up Position Sizing
- [ ] Add `default_portfolio_size`, `default_risk_pct` columns to User
- [ ] Persist via new endpoint or piggyback on profile update
- [ ] `_handle_ack` in `telegram_bot.py` reads user's values; falls back to $50k if unset
- [ ] Sizing math: `shares = (portfolio * risk_pct / 100) / (entry - stop)`
- Acceptance: User sets portfolio=$25k, risk=1% → takes ETH LONG @ $2200 stop $2193 → shares ≈ 35 (not the old fixed value)

If FR-7 is deferred, Position Sizing section must be **removed** from Settings (no half-wired UI).

### FR-8: Backfill + onboarding
- [ ] Existing users see defaults on next login (no forced reconfig)
- [ ] New signups: set `wait_alerts_enabled=true` for Pro/Trial, `wait_alerts_enabled=false` for Free
  - If free: we proactively reduce noise; they can turn on WAITs if they want
- Acceptance: Admin User Debug panel reflects new fields for all users after migration

## Testing

### Unit tests
- [ ] `_user_wants_alert` returns False when direction not in alert_directions
- [ ] `_user_wants_alert` returns False when conviction below min
- [ ] `_user_wants_alert` returns False for WAIT when wait_alerts_enabled=false
- [ ] `_user_wants_alert` returns False when telegram_enabled=false (master kill)
- [ ] Unknown conviction / direction defaults to safe behavior (don't crash)

### Integration tests
- [ ] PUT /settings/notifications with new fields → GET returns same values
- [ ] Nonsensical input rejected (e.g., `min_conviction=banana`)
- [ ] Empty `alert_directions` defaults to all on (no lockout)

### Manual
- [ ] Settings → toggle WAITs off → wait 5 min → no WAITs in Telegram
- [ ] Settings → Min conviction High → next LOW/MEDIUM alert skipped
- [ ] Settings → uncheck SHORT → next SHORT alert skipped
- [ ] Existing users: visit Settings → see defaults populated without saving

## Rollout

### Phase 1 — Backend + API (half-day)
- Model columns + migration
- Helper function
- Integrate into 5 delivery branches
- Extend notification preferences API

### Phase 2 — Frontend (half-day)
- Remove `AlertPreferences` component
- Build `AIAlertFilters` component
- Wire to API
- Clean up Notification Channels

### Phase 3 — Position Sizing fix (optional, half-day)
- If going Option A: model columns, wire into `_handle_ack`
- If going Option B: delete UI, document for later

### Phase 4 — Deploy + monitor
- Ship behind no feature flag (low risk — defaults preserve current behavior)
- Watch `/admin/user-debug` to see users adjusting preferences
- Smoke test the flow end-to-end

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| User unchecks everything → gets zero alerts → thinks app is broken | UI validation: if all directions unchecked, show warning "You won't receive any alerts." Allow save anyway — user's choice. |
| Migration on a live DB fails | Use `ADD COLUMN IF NOT EXISTS` + `DEFAULT` clause — idempotent. Tested against existing migration pattern in `api/app/main.py`. |
| Scanner breaks if new columns don't load | Defensive defaults in `_user_wants_alert`: missing value → allow delivery (fail-open on preference, fail-closed on hard rate limits). |
| Email/Push checkboxes removed → users wonder why | Small footer note: "Email & Push delivery coming soon." Or keep fields grayed out with "Coming soon." |
| Position Sizing change breaks existing trade acks | Fall back to current $50k behavior if columns null. No forced migration of existing trades. |

## Out of Scope

- Per-symbol mute ("don't alert me on ETH today")
- Time-based quiet hours in this pass (existing `quiet_hours_start/end` fields untouched; UI unchanged)
- Email or Push delivery implementation
- Mobile push notification setup
- SMS delivery
- Portfolio-aware position sizing beyond the simple $risk / (entry-stop) formula

## Success Criteria

- [ ] Deprecated "Trading Patterns" section removed from Settings
- [ ] Users can change min conviction, WAIT toggle, direction filters in < 30 seconds
- [ ] Scanner respects each preference — verifiable via User Debug panel
- [ ] Zero references in Settings UI to features that don't exist (Email, Push, Pattern toggles)
- [ ] Free user complaints about "too many alerts" drop to near-zero post-deploy
- [ ] No regressions in alert delivery for users who haven't touched Settings (defaults = current behavior)

## Related

- `web/src/pages/SettingsPage.tsx` — primary UI surface
- `api/app/routers/settings.py` — notification prefs endpoint
- `api/app/models/user.py` — schema changes
- `analytics/ai_day_scanner.py` — delivery filters
- `scripts/telegram_bot.py` — position sizing in `_handle_ack`
- `tickets/deprecate-rule-based-alerting.md` — the deprecation this spec completes
- `tickets/ai-scan-rate-limit-persistence.md` — parallel work; preferences don't replace rate limits (belt + suspenders)
- Spec 30 — Tier Gating (respects tier limits after user filter)

## Open Questions

- Default for WAIT on Free: suggestion is `false` (less noise on signup) but could go either way. Lean toward `false` for cleaner first impression.
- Position Sizing Option A vs B: leaning Option A (wire it up) — it's a small change that's been promised to users already.
- Should min_conviction default differ by tier? Free=High (less noise, fewer Telegrams), Pro=Medium (full experience)? Worth considering.
