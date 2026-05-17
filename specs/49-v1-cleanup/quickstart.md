# Quickstart Runbook — Spec 49 V1 Cleanup

**Purpose**: The sequenced step-by-step for executing the cleanup safely.
**Audience**: The maintainer running the cleanup, with operator coordination for the Railway env-flag gate.
**Prerequisite**: The six FR amendments listed in [plan.md](./plan.md#constitution-check) MUST be applied to `spec.md` first. Do not start Phase B with the original FR-405 wording — the deletion list will break the V2 pipeline (see [research.md §3](./research.md#3-hidden-v2-imports-of-tier-3-doomed-modules-resolves-fr-411-expectations--drives-phase-b-sequencing)).

**Total estimated time**: ~7 working days + 7 trading days of validation soak.

---

## Phase A — Amendments + pre-flight (Day 1–2)

### A1 — Apply the six FR amendments to `spec.md`

Either run `/speckit-clarify` on this spec with the six findings phrased as questions, OR edit `spec.md` directly:

| Amendment | Edit |
|-----------|------|
| A1 | FR-407 / FR-408: rename `spy_regime_gate` → `compute_spy_gate` (function actually at `intraday_rules.py:7642`) |
| A2 | FR-407: append "Also preserve `_targets_for_long` and `_targets_for_short`, promoting them to public `targets_for_long` / `targets_for_short` in `analytics/alert_types.py` since `tv_webhook.py:378` reaches into them." |
| A3 | FR-405: remove `htf_bias` from Tier 3 deletion list (consumed by `tv_webhook.py:368` and `monitor.py:24` — V2-live). Move to "Retained" section. |
| A4 | FR-405: remove `intel_hub` from Tier 3. `intel.py` exposes 13 React-consumed endpoints, 11 transitively use `intel_hub`. Move to "Retained — trim instead." |
| A5 | FR-405: remove `trade_coach` from Tier 3. `intel.py:163,322` calls it. Move to "Retained." |
| A6 | FR-405: mark `options_trade_store` as "Owner-confirm before delete." `routers/real_trades.py` has 6 import sites. |

Commit the amended spec (single commit, message: `spec: amend 49 after pre-flight findings (A1–A6)`).

### A2 — Operator flips Railway env flags

Per [research.md §7](./research.md#7-railway-env-flag-confirmation-procedure-resolves-fr-401):
1. Railway dashboard → `worker` service → Variables tab.
2. Set `RULE_ENGINE_ENABLED=false` and `AI_SCAN_ENABLED=false`.
3. Redeploy worker.
4. Tail logs for ~30 seconds; confirm both startup messages appear:
   - `Rule engine DISABLED (RULE_ENGINE_ENABLED=false).`
   - `AI scans DISABLED (AI_SCAN_ENABLED=false) — rule-based alerts only`

### A3 — Capture FR-402 LOC baseline

`brew install cloc` (if missing), then:

```bash
cd /Users/mentorhub/Documents/master-domain-hub/trade-analytics
cloc --vcs=git --exclude-dir=node_modules,web/dist,web/ios,.venv . | tee specs/49-v1-cleanup/loc-baseline.txt
```

Record the grand-total LOC. Multiply by 0.85 → that's the SC-101 ceiling.

### A4 — Confirm `options_trade_store` UI status

Ask the owner: "is the options-trading UI shipped to users?"
- **Yes** → retain `alerting/options_trade_store.py` and `routers/real_trades.py` options endpoints.
- **No** → add to Tier 3 deletion list and proceed.

Record the answer in `specs/49-v1-cleanup/decision-tradesignalwithai.md` (alongside the FR-417 sunset decision) so the audit trail is single-file.

### A5 — Wait one trading session

After A2's flag flip, wait for one full RTH session (09:30–16:00 ET, US holiday calendar). Tail:
- Telegram `tradecopilot-alerts` channel for V1-flavored alerts.
- `alerts` Postgres table — query `SELECT DISTINCT alert_type FROM alerts WHERE fired_at > now() - interval '1 day' ORDER BY 1;` — every value must match Pine's V2 taxonomy (no `ma_bounce`, `support_bounce`, `gap_fill`, etc.).

**Gate**: if any V1-flavored row appears, debug before proceeding to Phase B.

---

## Phase B — Tier 1 + Tier 2 deletions (Day 3)

### B1 — Tier 1 safe deletions (FR-403)

No grep audit required — these have no consumers.

```bash
cd /Users/mentorhub/Documents/master-domain-hub/trade-analytics
rm =0.31.0 monitor.log backup_pre_v2_20260404_0854.json
rm data/trades.db* api/tradesignal_dev.db
rm -rf pages/_archive pages/_archive_v1
rm web/alert-dashboard.html prototype/redesign-v2.html
rm -rf signal-pro-images
rm docs/img*.png docs/tradecopilot_alerts_2026-03-*.pdf
rm improvements/alert-rules-inventory.html
rm -rf images
rm data/spy_*.csv data/spy_pattern_report.txt
```

Run tests: `python3 -m pytest tests/ -v` — must be green.

Commit: `chore: tier-1 safe deletions (spec 49 FR-403)`.

### B2 — Tier 2 V1 stack deletion (FR-404, gated on Phase A5)

**Pre-deletion grep audit (FR-411)**:
```bash
for f in monitor.py worker.py monitor_thread.py app.py auth.py models.py config.py \
         ui_theme.py alerts_pdf.py parsers/parser_1099.py parsers/parser_statement.py; do
  echo "=== $f ==="
  grep -rn "from $(basename $f .py)\|import $(basename $f .py)" api/app triage-agent web/src --include="*.py" --include="*.ts" --include="*.tsx" 2>/dev/null || echo "  (no V2 importers — safe)"
done
```

Any V2 importer reported = STOP and resolve before proceeding.

Then:
```bash
rm monitor.py worker.py monitor_thread.py
rm app.py auth.py models.py config.py ui_theme.py alerts_pdf.py
rm -rf pages/
rm parsers/parser_1099.py parsers/parser_statement.py

# V1 React pages (coordinate with Spec 50 — App.tsx route changes)
rm web/src/pages/AlertsPage.tsx web/src/pages/ScannerPage.tsx web/src/pages/ChartsPage.tsx
rm web/src/pages/ScorecardPage.tsx web/src/pages/HistoryPage.tsx web/src/pages/ImportPage.tsx
rm web/src/pages/BacktestPage.tsx web/src/pages/PaperTradingPage.tsx
rm web/src/pages/SwingTradesPage.tsx web/src/pages/AICoachPage.tsx
rm web/src/pages/TradingPage.tsx   # v1 — TradingPageV2 stays
```

Run tests + React build:
```bash
python3 -m pytest tests/ -v
cd web && npm run build && cd ..
```

Both must succeed. Commit: `chore: tier-2 V1 stack deletion (spec 49 FR-404)`.

### B3 — Rebuild iOS Capacitor bundle

After B2, the iOS bundle still references deleted React pages. Re-bundle and re-submit:

```bash
cd web
npm run build
npx cap sync ios
# Open Xcode, archive, upload via Transporter
```

This is a release-engineering task, not part of the spec's success criteria, but it should happen before any user-facing release of the V3 web app.

---

## Phase C — Extraction + Tier 3 sequenced deletions (Day 4–6)

### C1 — Create `analytics/alert_types.py`

Following [data-model.md "Module 1"](./data-model.md#module-1--analyticsalert_typespy):

1. Open `analytics/intraday_rules.py` at line 175 (`AlertType`).
2. Copy the enum verbatim into a new file `analytics/alert_types.py`.
3. Copy the `AlertSignal` dataclass at line 320 verbatim.
4. Copy `_targets_for_long` and `_targets_for_short` (search for `def _targets_for_`); rename to `targets_for_long` / `targets_for_short` (FR amendment A2).
5. Add minimal imports per data-model.md.

Run unit test for the new module:
```bash
python3 -c "from analytics.alert_types import AlertType, AlertSignal, targets_for_long, targets_for_short; print(AlertType.__members__.keys())"
```

### C2 — Create `analytics/regime_gate.py`

Following [data-model.md "Module 2"](./data-model.md#module-2--analyticsregime_gatepy):

1. Open `analytics/intraday_rules.py` at line 7642 (`compute_spy_gate`).
2. Identify the function's full dependency closure (the helpers it calls inline).
3. Copy `compute_spy_gate` + every helper it transitively calls into `analytics/regime_gate.py`.
4. Verify the module imports only stdlib + pandas + (optionally) `analytics._bar_utils` if you factor shared helpers.

```bash
python3 -c "from analytics.regime_gate import compute_spy_gate; help(compute_spy_gate)"
```

### C3 — Repoint every importer

Per [data-model.md "Importer rewrite checklist"](./data-model.md#importer-rewrite-checklist-phase-c-t-c3):

```bash
# Mechanical replace — review each diff before commit
grep -rl "from analytics.intraday_rules import" api/app/ triage-agent/ analytics/ alerting/ tests/ | \
  xargs sed -i '' 's|from analytics.intraday_rules import \(AlertSignal\|AlertType\|AlertSignal, AlertType\|AlertType, AlertSignal\)|from analytics.alert_types import \1|g'

# Special case for tv_webhook.py:378 — manual edit:
#   from analytics.intraday_rules import _targets_for_long, _targets_for_short
#   →
#   from analytics.alert_types import targets_for_long, targets_for_short
# And rename the function-call sites in the same file.
```

Run tests: `python3 -m pytest tests/ -v`. Green = proceed.

Commit: `refactor: extract alert_types + regime_gate from intraday_rules (spec 49 FR-407/408)`.

### C4 — Cut V2-hot importers of Tier 3 modules (sequencing fix)

Per [research.md §3](./research.md#3-hidden-v2-imports-of-tier-3-doomed-modules-resolves-fr-411-expectations--drives-phase-b-sequencing), the following V2 sites import Tier 3 modules and MUST be cut BEFORE the modules themselves can be deleted:

| Importer | Action |
|----------|--------|
| `api/app/main.py:293–427` (V1 scheduler block) | Delete the entire `if AI_SCAN_ENABLED:` block — every import inside it goes (`ai_day_scanner`, `ai_swing_scanner`) |
| `api/app/routers/ai_coach.py:88` (`ai_best_setups`) | Delete the import + the route handler that uses it (the "Best Setups of the Day" endpoint) |
| `api/app/routers/auth.py:325` (`ai_day_scanner`) | Delete the import + the auth-side helper that calls it |
| `api/app/routers/admin.py:239` (`ai_day_scanner`) | Delete the import + the admin endpoint that calls it |
| `api/app/routers/backtest.py` (entire file) | Delete the file (no V2 consumer; was the V1 backtest UI) |
| `api/app/services/scanner.py` (entire file) | Delete the file |
| `api/app/routers/swing.py` (entire file, **pending owner confirmation**) | If swing UI is dead, delete file and its routes; else retain and accept `swing_rules` + `swing_scanner` as alive |

Run tests + React build after each cut. Commit per logical group.

### C5 — Delete remaining Tier 3 modules (FR-405, amended)

After C4, the modules have no remaining V2 importers. Delete:

```bash
cd analytics
rm ai_day_scanner.py ai_swing_scanner.py ai_best_setups.py ai_conviction.py
rm signal_engine.py swing_rules.py
rm spy_patterns.py cluster_narrator.py regime_narrator.py
rm post_market_review.py weekly_review.py monthly_report.py eod_review.py
rm position_advisor.py pretrade_check.py exit_coach.py game_plan.py
rm trade_replay.py trade_review.py journal_insights.py
rm confluence.py trade_matcher.py wash_sale.py categorizer.py _cache.py
# NOTE: do NOT delete htf_bias.py (A3), intel_hub.py (A4), trade_coach.py (A5)

cd ../alerting
rm swing_scanner.py swing_refresher.py paper_trader.py narrator.py
# Conditional on A4/A6:
# rm options_trade_store.py real_trade_store.py    # only if owner confirms options UI dead
```

Run tests: `python3 -m pytest tests/ -v`.

Commit: `chore: tier-3 deletions (spec 49 FR-405 amended)`.

### C6 — Delete `intraday_rules.py`

After C3 + C5, run the SC-104 check:

```bash
grep -rn "from analytics.intraday_rules" .
# Must return zero rows.
```

If clean: `rm analytics/intraday_rules.py`. Run tests. Commit: `chore: delete intraday_rules.py post-extraction (spec 49 FR-409)`.

### C7 — Trim `intel.py` (9 unreferenced routes)

Per [research.md §6](./research.md#6-apiapproutersintelpy-status--owner-confirm-path-resolved), confirm none of these are called by `scripts/telegram_bot.py` or any worker process, then delete from `intel.py`:

- `/scanner-context`
- `/decision-quality`
- `/pre-trade-check`
- `/position-check`
- `/classify-pattern/{sym}`
- `/premarket`
- `/eod-recap`
- `/trade-replay/{alert_id}`
- `/journal`

Keep the 13 React-consumed routes (`/win-rates`, `/fundamentals/{sym}`, `/daily/{sym}`, `/weekly/{sym}`, `/mtf/{sym}`, `/game-plan`, `/trade-journal`, `/analysis-history`, `/analysis/{id}/outcome`, `/coach`, `/public-track-record`, `/analyze-chart`, `/acked-win-rates`).

Run tests + React build. Commit: `chore: trim 9 unreferenced intel.py routes`.

---

## Phase D — Documentation + tests (Day 7)

### D1 — Replace root CLAUDE.md

Copy [contracts/claude-md-draft.md](./contracts/claude-md-draft.md) → `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/CLAUDE.md` (replacing the existing file).

Commit: `docs: rewrite CLAUDE.md for V2 production (spec 49 FR-413)`.

### D2 — Prepend supersedence notice to Spec 46

Prepend [contracts/spec-46-supersedence.md](./contracts/spec-46-supersedence.md)'s content to `trade-analytics/specs/46-stable-state-reference/spec.md`. Existing V1 baseline below the notice stays untouched.

Commit: `docs: mark spec 46 superseded by spec 48 manifest (spec 49 FR-416)`.

### D3 — Record FR-417 operator decision

Operator chooses one of {sunset with holding page, redirect DNS to `tradingwithai.ai`, leave dormant}. Record in `specs/49-v1-cleanup/decision-tradesignalwithai.md` (template at [contracts/decision-tradesignalwithai.md](./contracts/decision-tradesignalwithai.md)). Apply the chosen behavior at the live URL within 72 hours of the decision.

### D4 — Move abandoned-direction tickets to archive (FR-418)

```bash
cd /Users/mentorhub/Documents/master-domain-hub/trade-analytics
mkdir -p tickets/archive
git mv tickets/ai-alert-scoring.md tickets/ai-trade-coach.md tickets/ai-trade-narrator.md \
       tickets/ai-dynamic-stops-targets.md tickets/ai-market-regime-classifier.md \
       tickets/ai-trade-journal-analyst.md tickets/ai-support-resistance-prediction.md \
       tickets/ai-eod-review.md tickets/ai-smart-watchlist.md tickets/ai-feature-roadmap.md \
       tickets/deprecate-rule-based-alerting.md \
       tickets/archive/
```

Commit: `chore: archive abandoned-direction tickets (spec 49 FR-418)`.

### D5 — Delete dead test files (FR-412)

Per [research.md §8](./research.md#8-test-suite-topology-resolves-fr-412--constitution-check-test-config-gap):

```bash
cd tests
rm test_swing_rules.py test_ai_day_scanner.py test_ai_best_setups.py
rm test_signal_engine_bar.py test_mtf_analysis.py test_breakout_confirmation.py
rm test_ema_resistance.py test_phase2_volume_vwap.py test_phase3_notice_demotion.py
rm test_phase3b_ema_8_21.py test_phase4_replay.py test_phase4_targets.py
rm test_eod_review.py test_copilot_education.py
rm test_swing_entries.py test_swing_refresher.py test_paper_trader.py
rm test_narrator.py test_premarket_brief.py test_premarket_send.py
rm test_telegram_ai_commands.py test_weekly_setup.py test_auto_analysis.py
rm test_score_v2.py test_reproject_plan.py test_intraday_rules.py
rm test_alert_dedup.py
# Keep test_htf_bias.py (A3), test_intel_hub.py (A4), test_trade_coach.py (A5).
# Add NEW test_alert_types.py, test_regime_gate.py (Phase C).
```

Run final test suite: `python3 -m pytest tests/ -v`. Must be green.

Commit: `chore: prune V1 test files (spec 49 FR-412)`.

### D6 — Post-cleanup LOC measurement (SC-101)

```bash
cloc --vcs=git --exclude-dir=node_modules,web/dist,web/ios,.venv . | tee specs/49-v1-cleanup/loc-postcleanup.txt
```

Compare against baseline. Confirm ≥15% reduction. Document the actual percentage in `specs/49-v1-cleanup/decision-tradesignalwithai.md` (alongside the FR-417 decision — keep one decision log file for this spec).

---

## Phase E — Validation soak (7 trading days post-Phase D)

### E1 — Monitor Railway logs (SC-103)

For 7 consecutive trading days, check Railway logs once per day for any V1-related errors. Grep patterns:
- `intraday_rules`
- `ai_day_scanner`, `ai_swing_scanner`, `ai_best_setups`
- `signal_engine`
- `monitor.py`, `worker.py`
- `Streamlit`

Zero hits = SC-103 pass. Any hit = open a follow-up bug; do not close the spec.

### E2 — CLAUDE.md outside-agent audit (SC-105)

Run a 20-prompt audit asking an outside agent: "what are the protected files in this repo? how do I test locally?"

Score: ≥19/20 correctly identify the V2 protected-files list and the V2 dev workflow = SC-105 pass.

---

## Rollback plan

Each phase is committed separately on `main`. If Phase B breaks production:
- `git revert` the offending batch commit.
- Redeploy worker on Railway.
- Re-examine the pre-deletion grep audit for the missed importer.

For Phase C (extraction): the change is mechanical but spans multiple files. Keep the extraction PR small enough to revert in one operation if a downstream consumer breaks unexpectedly.

For Phase D (CLAUDE.md / Spec 46 / tickets): purely documentation; no rollback needed beyond `git revert`.

---

## Done definition

- [ ] All six FR amendments applied to spec.md (Phase A1)
- [ ] Operator confirmed Railway env flags (Phase A2)
- [ ] Phase A5 trading-session validation passed
- [ ] Tier 1 deletions merged, tests green (B1)
- [ ] Tier 2 deletions merged, tests + React build green (B2)
- [ ] iOS rebuild submitted (B3)
- [ ] `alert_types.py` + `regime_gate.py` extracted and tested (C1–C3)
- [ ] V2-hot importer cuts merged (C4)
- [ ] Tier 3 deletions merged, tests green (C5)
- [ ] `intraday_rules.py` deleted, SC-104 grep clean (C6)
- [ ] `intel.py` trimmed (C7)
- [ ] New CLAUDE.md merged (D1)
- [ ] Spec 46 supersedence notice merged (D2)
- [ ] FR-417 decision recorded + applied at live URL (D3)
- [ ] Tickets archived (D4)
- [ ] V1 test files deleted (D5)
- [ ] Post-cleanup LOC measured, ≥15% reduction confirmed (D6)
- [ ] 7-trading-day validation soak passed (E1)
- [ ] 20-prompt CLAUDE.md audit ≥19/20 (E2)
