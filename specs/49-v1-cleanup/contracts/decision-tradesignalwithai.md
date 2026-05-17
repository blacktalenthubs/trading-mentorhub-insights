# Contract — Operator Decision Template (FR-417 + FR-402 + A4 + A6)

**Status**: Phase 1 design artifact for Spec 49. Template to be filled out during Phase D T-D3 and Phase D T-D6.
**Target file** (after fill-in): `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/specs/49-v1-cleanup/decision.md`
**Purpose**: Single decision log for Spec 49. Records the four operator decisions that the spec defers to operator judgment, plus the post-cleanup measurement.

---

## Template (copy → fill in → save as `decision.md`)

```markdown
# Spec 49 — Operator Decision Log

**Date filled**: YYYY-MM-DD
**Filled by**: <operator name>

---

## D-1. FR-417 — Legacy `tradesignalwithai.com` deployment

**Question**: What happens to the Streamlit deployment at `tradesignalwithai.com` after Spec 49 cleanup ships?

**Operator decision**: <ONE OF: sunset-with-holding-page | redirect-dns-to-tradingwithai-ai | leave-dormant>

**Rationale**: <one paragraph — typical reasons: SEO retention, existing user redirects, brand simplification>

**Live URL behavior after decision**: <describe what a visitor to https://tradesignalwithai.com will see / where they will be sent>

**Apply-by date**: <within 72 hours of filling this in>

**Confirmed applied**: <date> by <operator name>

---

## D-2. A4 — `intel_hub.py` + `trade_coach.py` retention

**Question**: Spec 49 amendment A4 retains `analytics/intel_hub.py` and `analytics/trade_coach.py` because `intel.py` exposes 13 React-consumed endpoints that transitively use them. Confirm this matches operator's product intent.

**Operator decision**: <ONE OF: keep-as-amended-A4 | re-evaluate-and-deprecate-intel-py>

**Rationale**: <one paragraph>

If re-evaluate-and-deprecate-intel-py: open a follow-up spec for the React frontend changes required to remove the 13 endpoints.

---

## D-3. A6 — `options_trade_store.py` deletion

**Question**: Is the options-trading UI shipped to users today? `routers/real_trades.py` has 6 import sites for `alerting/options_trade_store.py`. Deletion is gated on the answer.

**Operator decision**: <ONE OF: ui-shipped-retain | ui-not-shipped-delete>

**Rationale**: <one paragraph>

**Files deleted as a result of this decision (if any)**:
- (list)

---

## D-4. Phase D T-D6 — Post-cleanup LOC measurement

**Question**: What's the actual LOC reduction achieved versus the FR-402 baseline?

**Baseline (from Phase A3)**: <paste cloc grand-total line from loc-baseline.txt>

**Post-cleanup (from Phase D6)**: <paste cloc grand-total line from loc-postcleanup.txt>

**Reduction**: <X> LOC = <YY.Y>% (SC-101 target: ≥15%)

**SC-101 status**: <PASS | FAIL>

If FAIL: document remaining deletion candidates considered but not executed, and the reason for each (e.g., owner declined to delete `swing.py`'s endpoints because UI still active).

---

## D-5. SC-103 — 7-trading-day validation soak

**Soak start date**: <date Phase D6 completed>
**Soak end date**: <Phase D6 completion + 7 trading days, US calendar>

**Daily check log**:

| Date | V1-related errors in Railway logs? | Notes |
|------|-----------------------------------|-------|
| <day1> | none / list | |
| <day2> | | |
| ... | | |
| <day7> | | |

**SC-103 status**: <PASS | FAIL>

If FAIL: link to follow-up bug ticket(s).

---

## D-6. SC-105 — Outside-agent CLAUDE.md audit

**Audit date**: <date>
**Number of prompts**: 20
**Correctly identified V2 protected files**: <N>/20
**Correctly identified V2 dev workflow**: <N>/20
**SC-105 status**: <PASS (≥19/20) | FAIL>

If FAIL: identify which sections of CLAUDE.md need clarification; open a follow-up doc PR.

---

## Sign-off

Spec 49 considered done when D-1 through D-6 are all filled in and SC-101 / SC-103 / SC-105 all PASS.

**Final sign-off**: <date> by <operator name>
```

---

## Why one decision log

The earlier spec drafts implied multiple decision artifacts (operator URL decision, owner UI confirmations, success-criteria measurements). Consolidating them into one `decision.md` file keeps the audit trail in one place and avoids hunting through the spec directory at retrospective time.
