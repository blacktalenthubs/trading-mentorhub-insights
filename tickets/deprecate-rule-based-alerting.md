# Deprecate Rule-Based Alerting — AI Scan Takes Over

**Priority**: High (execute after EOD 2026-04-12)
**Created**: 2026-04-12
**Owner**: TBD

## Why

AI scan has proven more accurate and context-aware than the 78-rule engine:

- Catches setups rules miss (META $595, ETH VWAP hold)
- Says WAIT in chop — rules fire false PDL bounces
- Now has level dedup + higher-low confirmation structure
- Position-aware per user (no duplicate LONGs)
- Rate-limited per tier (7/day free, unlimited Pro)
- Multi-user safe (no cross-user data leakage)

Rule engine has been a constant source of bugs (20+ commits in 2 days destabilizing it). Maintaining two systems in parallel adds complexity without incremental value.

## Scope

### Disable / Remove

| Component | File | Action |
|---|---|---|
| Rule-based monitor polling | `api/app/background/monitor.py` | Disable alert firing, keep outcome tracking |
| Intraday rule evaluation | `analytics/intraday_rules.py` | Remove from scheduler, keep module for reference |
| Swing rule scanner | `analytics/swing_scanner.py` | Already disabled, confirm |
| Rule-based alert types in `alert_type` column | DB | Stop creating new ones; historical rows stay for replay |
| Rule engine tests | `tests/test_intraday_rules.py`, `tests/test_swing_*.py` | Mark as skipped or remove |

### Keep

| Component | Reason |
|---|---|
| Alert model + table | AI scan writes here too |
| Outcome tracking (T1 hit, stopped out) | Works for AI scan alerts too |
| Alert history / session summary / replay | Works regardless of source |
| Pattern Library (14 patterns) | Educational, not tied to rule engine |
| Trade Review page | Works for any alert source |
| `/alerts/*` API endpoints | Shared infrastructure |

### UI Cleanup

- Remove "AI Scan" vs "Rules" filter on Trade Review page (everything is AI now)
- Remove rule-based signal tab on Trading V2 page
- Update landing page language: remove any mention of "78 rules" or "rule engine"

## Implementation Steps

1. **Disable rule scheduler jobs** — comment out `evaluate_intraday_rules` registration in `api/app/main.py` scheduler setup
2. **Disable Telegram firing in monitor.py** — keep the outcome-tracking loop but skip alert creation
3. **Update `useAlertsHistory` consumers** — simplify UI since source distinction is gone
4. **Remove or skip rule tests** — currently 51 failing, most are rule-engine drift
5. **Update /copilot education** — patterns are taught generally, not tied to rules
6. **Migration note** — historical rule-based alerts in DB stay for replay; no data deletion

## Safety

- **Keep rule code in repo** for 30 days in case we need to revert
- **Feature flag the disable** — `RULE_ENGINE_ENABLED=False` env var so we can toggle back without redeploy
- **Monitor AI scan reliability for 7 days** before deleting rule code
- Do this AFTER market close today (EOD 2026-04-12)

## Acceptance

- [ ] No rule-based alerts fire after toggle
- [ ] AI scan continues firing as expected
- [ ] Outcome tracking (T1 hit, stopped out) still works
- [ ] Trade Review page works without source filter
- [ ] Landing page has no rule-engine references
- [ ] Tests for rule engine removed or skipped — test suite green
- [ ] Feature flag `RULE_ENGINE_ENABLED` documented in CLAUDE.md

## Followups (out of scope here)

- After 30 days of AI-only, delete rule code entirely
- Consolidate signal flow — single "AI Alert" concept in UI
- Update marketing/SEO to lead with "AI trading platform" (already done in Spec 28 rebuild)

## Related

- Spec 28 — Platform rebrand (already positions AI as core)
- `tickets/ai-scan-rate-limit-persistence.md` — persist rate limits to DB
- AI scan improvements (2026-04-11 to 2026-04-12):
  - Position awareness (commit `0d531da`)
  - Level dedup fix (commit `bd130b5`)
  - Higher-low confirmation (commit `bd130b5`)
  - Multi-user scoping (commit `0d531da`)
  - VWAP computed server-side (commit `cad200c`)
