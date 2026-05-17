# Phase 0 Research — Spec 49 V1 Cleanup

**Date**: 2026-05-16
**Method**: Read-only audit by research agent. Greps over `api/app/`, `triage-agent/`, `analytics/`, `alerting/`, `tests/`, `web/src/`. No edits.
**Purpose**: Resolve every unknown in [plan.md](./plan.md)'s Technical Context and Constitution Check before Phase 1 design. Surfaces the six FR amendments the plan calls out as Constitution Check failures.

---

## 1. Baseline LOC (resolves FR-402)

`cloc` is **not installed** on this machine. Fallback: `find ... | xargs wc -l` over `*.py *.ts *.tsx *.js *.jsx`, pruning `node_modules`, `.git`, `.venv`, `__pycache__`, `web/dist`, `web/ios`.

| Language | Files | LOC |
|---|---|---|
| Python (`*.py`) | 485 | 188,124 |
| TypeScript (`*.ts`) | 28 | 4,573 |
| TSX (`*.tsx`) | 125 | 35,617 |
| JS (`*.js`) | 8 | 90 |
| JSX | 0 | 0 |
| **Grand total** | **646** | **228,404** |

**SC-101 target**: ≥15% reduction = **≥ 34,261 LOC removed**. Reachable from Tier 3 + test housekeeping alone (`test_intraday_rules.py` is 7,700 LOC; `analytics/ai_day_scanner.py` is 2,383 LOC; `intraday_rules.py` itself is 9,438 LOC and most of it goes after extraction).

**Implementation note**: install `cloc` (`brew install cloc`) before Phase D so the post-cleanup measurement uses a standard tool; the baseline above is the apples-to-apples reference.

---

## 2. Live symbols in `analytics/intraday_rules.py` (resolves FR-407 / FR-408 surface)

File: `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/analytics/intraday_rules.py` — 9,438 LOC. Top-level `AlertType` enum at line 175, `AlertSignal` dataclass at 320, SPY gate at 7642.

**SPY-regime-gate function actually named** `compute_spy_gate(spy_bars, spy_vwap)` (line 7642). Returns `{gate, vwap_dominance, above_ema, hourly_break, reason}`. **Not** `spy_regime_gate` as Spec 49 FR-407/408 names it. There is a separate v1-only rule `check_spy_short_entry` (line 4880) used internally and an unrelated `check_spy_regime` in `analytics/swing_rules.py` (Tier 3 dead) — both DEAD under V2.

→ **FR amendment A1**: rename FR-407/408 references from `spy_regime_gate` to `compute_spy_gate`.

**Importers in V2 paths (`api/app/`, `triage-agent/`)**:

| Importer | Symbols | Verdict |
|---|---|---|
| `api/app/background/monitor.py:32` | `AlertSignal, AlertType, evaluate_rules` | mixed — `evaluate_rules` is V1 rule-engine (gated by `RULE_ENGINE_ENABLED` at `main.py:255`); monitor.py itself is being deleted with V1 |
| `api/app/background/monitor.py:214` | `compute_spy_gate` (lazy) | **LIVE** — but monitor itself goes; check downstream consumers |
| `api/app/routers/ai_coach.py:134` | `AlertSignal, AlertType` | **LIVE** |
| `api/app/routers/settings.py:397` | `AlertSignal, AlertType` | **LIVE** |
| `api/app/routers/tv_webhook.py:41` | `AlertType` | **LIVE (critical V2 path)** |
| `api/app/routers/tv_webhook.py:378` | `_targets_for_long, _targets_for_short` | **LIVE (critical V2 path) — but private underscored** |

**Triage-agent imports of `intraday_rules`**: zero. `grep -r "from analytics.intraday_rules" triage-agent/` returns no rows.

**V1-only consumers (DEAD path, deleted with their modules)**:
- `analytics/swing_rules.py:34` (whole module is Tier 3)
- `analytics/position_advisor.py:78` calls `detect_hourly_consolidation_break` (Tier 3)
- `analytics/tv_signal_adapter.py:33` — KEEP (live V2). After extraction, update import to `analytics.alert_types`.

→ **FR amendment A2**: Spec FR-407 must explicitly preserve `_targets_for_long` and `_targets_for_short` and promote them to public names in the new `analytics/alert_types.py`. Leaving them underscore-prefixed in a renamed file masks an external dependency; renaming them to `targets_for_long` / `targets_for_short` makes the V2 contract honest.

**Net live surface in `intraday_rules.py`** (to be carved into new modules):

- → `analytics/alert_types.py`: `AlertType` enum, `AlertSignal` dataclass, `targets_for_long`, `targets_for_short` (promoted from `_targets_*`).
- → `analytics/regime_gate.py`: `compute_spy_gate` + its direct dependencies (vwap_dominance helper, hourly_break helper, ema check — read the function body and extract its dependency closure).
- **Not preserved**: `evaluate_rules` and the ≈60 `check_*` rule functions, scoring v1/v2, EMA bounce variants. All dead when `RULE_ENGINE_ENABLED=false`.

---

## 3. Hidden V2 imports of Tier 3 doomed modules (resolves FR-411 expectations + drives Phase B sequencing)

Searched `api/app/`, `triage-agent/`, `web/src/` for real import statements.

| Module (target of FR-405 deletion) | V2 importers | Status |
|---|---|---|
| `ai_day_scanner` | `api/app/main.py:319,329,339,357`; `routers/auth.py:325`; `routers/admin.py:239` | **HOT** — scheduler block + admin/auth helpers must be cut FIRST |
| `ai_swing_scanner` | `api/app/main.py:412` | **HOT** — scheduler |
| `ai_best_setups` | `api/app/routers/ai_coach.py:88` | **HOT** — cut call site first |
| `ai_conviction` | none | safe |
| `signal_engine` | `routers/backtest.py:23`; `services/scanner.py:20` | **HOT** — both routers being deleted, but the deletes have to land BEFORE `signal_engine` |
| `swing_rules` | `routers/swing.py:34` (`check_spy_regime`) | **HOT** — depends on swing UI status |
| `spy_patterns` | none | safe |
| `cluster_narrator` | `background/monitor.py:654` (lazy) | hot but lazy — gated by `RULE_ENGINE_ENABLED` |
| `regime_narrator` | `background/monitor.py:205` (lazy) | hot but lazy — same gating |
| `eod_review` | none in import-statements (string matches in `tier.py` are dict keys, not imports) | safe |
| `journal_insights` | none | safe |
| **`htf_bias`** | `background/monitor.py:24`; `routers/tv_webhook.py:368` | **HOT — V2 critical path** |
| `confluence` | `from analytics.confluence` returned 0 rows; verify the `confluence_score(...)` import in `monitor.py:27` resolves elsewhere | likely safe; verify before delete |
| **`trade_coach`** | `routers/intel.py:163,322` | **HOT (via intel.py)** |
| `trade_matcher` | none | safe |
| **`intel_hub`** | `routers/intel.py` (11 imports) | **HOT (via intel.py)** |
| `swing_scanner` (lives in `alerting/`, not `analytics/`) | `routers/swing.py:76,93,104,112` | **HOT** — depends on swing UI status |
| `swing_refresher` | none | safe |
| `paper_trader` | none | safe |
| `narrator` | `background/monitor.py:642` (`ai_narrator`) | hot but lazy |
| **`options_trade_store`** | `routers/real_trades.py:394,417,428,436,446,453` | **HOT** — depends on options UI status |
| `real_trade_store` | none | safe |

### Surprises that force spec amendments

1. **`htf_bias.py` is V2-live** (`tv_webhook.py:368` + `monitor.py:24`). Cannot delete as Tier 3. → **FR amendment A3**: remove from Tier 3; retain. After `monitor.py` is deleted (V1 path), `htf_bias` still has `tv_webhook` as a live consumer.
2. **`intel_hub.py` (69 KB) is reachable from production React** via 11 import sites in `intel.py`, and `intel.py` itself serves 13 endpoints to the React app (see §6). → **FR amendment A4**: remove from Tier 3; retain. Trim 9 unused `intel.py` routes instead (see §6).
3. **`trade_coach.py` is reachable from production React** via `intel.py:163,322`. → **FR amendment A5**: remove from Tier 3; retain.
4. **`options_trade_store.py` is reachable** via 6 import sites in `routers/real_trades.py`. → **FR amendment A6**: confirm with owner whether the options-trading UI is shipped before deletion.
5. **`ai_day_scanner` / `ai_swing_scanner`** are gated by `AI_SCAN_ENABLED` in `main.py:293`. Safe to delete only once that flag is confirmed off AND the scheduler block at `main.py:319,329,339,357` is cut. → **Phase B sequencing** in quickstart.md.
6. **`narrator`, `cluster_narrator`, `regime_narrator`** all live inside `monitor.py` import paths (which itself depends on `RULE_ENGINE_ENABLED`). Deletable when V1 `monitor.py` is. → **Phase B sequencing**.

---

## 4. `alerting/notifier.py` and `alerting/alert_store.py` dependency audit (resolves FR-406 confidence)

Files at `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/alerting/notifier.py` and `alerting/alert_store.py`. The spec narrative occasionally says "analytics/" — the actual location is `alerting/`. No change to FR-406 substance.

`alerting/alert_store.py` imports:

```python
from datetime import date
from analytics.intraday_rules import AlertSignal, AlertType
from db import get_db
```

No Tier 3 modules. **CLEAN.** After Phase C extraction, update import to `from analytics.alert_types import AlertSignal, AlertType`.

`alerting/notifier.py` top imports:

```python
import logging, os, smtplib, threading
from datetime import datetime
from email.mime.text import MIMEText
from urllib.parse import quote
from analytics.intraday_rules import AlertSignal, AlertType
from alert_config import (...)
```

No Tier 3 modules. **CLEAN.** Same import update post-extraction.

---

## 5. `analytics/chart_analyzer.py` dependency audit (resolves Spec 51 prep)

File: `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/analytics/chart_analyzer.py` — 861 LOC. Imports (lines 10–17):

```python
from __future__ import annotations
import logging, re, time
from typing import Generator
import pandas as pd
```

Pure stdlib + pandas. **Zero internal coupling.** FR-406 preservation is safe. Spec 51 foundation is intact.

---

## 6. `api/app/routers/intel.py` status — owner-confirm path resolved

`intel.py` is 864 LOC, registered at `api/app/main.py:854` under `/api/v1/intel`. 22 routes total. React app consumes 13 via `web/src/`:

| Endpoint | Frontend call site |
|---|---|
| `/intel/win-rates` | `web/src/api/hooks.ts:948` |
| `/intel/acked-win-rates` | `hooks.ts:956` |
| `/intel/fundamentals/{sym}` | `hooks.ts:964` |
| `/intel/daily/{sym}` | `hooks.ts:973` |
| `/intel/weekly/{sym}` | `hooks.ts:982` |
| `/intel/mtf/{sym}` | `hooks.ts:991` |
| `/intel/game-plan` | `hooks.ts:1051` |
| `/intel/trade-journal` | `hooks.ts:1078` |
| `/intel/analysis-history`, `/intel/analysis/{id}/outcome` | `components/ai/AnalysisHistory.tsx:25,36` |
| `/intel/coach` (POST stream) | `hooks/useCoachStream.ts:117` |
| `/intel/public-track-record` | `pages/LandingPage.tsx:29` |
| `/intel/analyze-chart` (POST) | `pages/AICoPilotPage.tsx:207` |

The 9 routes NOT reachable from React (candidates for trim, pending Telegram-bot/worker confirmation): `/scanner-context`, `/decision-quality`, `/pre-trade-check`, `/position-check`, `/classify-pattern/{sym}`, `/premarket`, `/eod-recap`, `/trade-replay/{alert_id}`, `/journal`.

**Recommendation**: `intel.py` is **NOT deletable**. Keep it. Trim the 9 unreferenced routes after verifying neither `scripts/telegram_bot.py` nor any worker process calls them. Their removal flows naturally with the V1 cleanup; the kept routes preserve the React AI Co-Pilot, Landing track-record stat, and Analysis History.

`/intel/analyze-chart` depends on `analytics/chart_analyzer.py` (Spec 51 foundation) and survives any trim. This is one of the seams Spec 51 builds on.

---

## 7. Railway env-flag confirmation procedure (resolves FR-401)

Canonical doc: `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/plan/tradingwithai-shutdown.md`, lines 24–25:

> `RULE_ENGINE_ENABLED=false` — Stops V1 rule polling (gap fills, MA bounce, target hits via yfinance). TV alerts still fire.
> `AI_SCAN_ENABLED=false` — Stops AI day scan, swing scan, auto-trade monitor, trade_replay, weekly_review.

Operator procedure:

1. **Dashboard**: Railway project → `worker` service → **Variables** tab → confirm both `RULE_ENGINE_ENABLED=false` and `AI_SCAN_ENABLED=false`. URL pattern: `https://railway.app/project/<project-id>/service/<service-id>/variables`.
2. **CLI** (no scripted helper in repo): `railway variables --service worker | grep -E 'RULE_ENGINE_ENABLED|AI_SCAN_ENABLED'`.
3. **Runtime proof** — search `worker` logs for the two startup messages from `api/app/main.py`:
   - `"Rule engine DISABLED (RULE_ENGINE_ENABLED=false)."` (main.py:276)
   - `"AI scans DISABLED (AI_SCAN_ENABLED=false) — rule-based alerts only"` (main.py:427)
4. **Env file**: no `.env` is checked into the repo. Railway is the source of truth. Local dev defaults to `true` via `os.environ.get(..., "true")`.
5. **Trading-session validation** (FR-401): tail the Telegram channel + `alerts` DB table for one RTH session. Zero rows where `alert_type` belongs to the V1 enum set = clear to begin Phase B.

---

## 8. Test suite topology (resolves FR-412 + Constitution Check test-config gap)

49 entries under `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/tests/`:
44 `test_*.py` files + `conftest.py`, `__init__.py`, plus `perf/` and `smoke/` subdirs.

**No `pytest.ini`, `pyproject.toml`, or `setup.cfg`.** Sole config is `tests/conftest.py`:

```python
if "multitasking" not in sys.modules:
    sys.modules["multitasking"] = MagicMock()
```

This means there's no way to mark tests by tier; the runbook uses an explicit file list rather than `pytest -m`.

### Grouping by subsystem

**V1 rule-engine (DOOMED with Tier 3)** — DELETE:
- `test_intraday_rules.py` (≈7,700 LOC), `test_alert_dedup.py`, `test_breakout_confirmation.py`, `test_ema_resistance.py`, `test_phase2_volume_vwap.py`, `test_phase3_notice_demotion.py`, `test_phase3b_ema_8_21.py`, `test_phase4_replay.py`, `test_phase4_targets.py`, `test_score_v2.py`, `test_signal_engine_bar.py`, `test_reproject_plan.py`
- Keep a slim new `test_alert_types.py` covering only `AlertType`, `AlertSignal`, `targets_for_long/short` and a `test_regime_gate.py` covering `compute_spy_gate`.

**V1 AI-scanner (DOOMED with Tier 3)** — DELETE with caveats:
- `test_ai_day_scanner.py`, `test_ai_best_setups.py`, `test_swing_entries.py`, `test_swing_rules.py`, `test_swing_refresher.py`, `test_paper_trader.py`, `test_intel_hub.py`, `test_trade_coach.py`, `test_eod_review.py`, `test_htf_bias.py` (revisit per surprise #1 — `htf_bias` is retained), `test_mtf_analysis.py`, `test_narrator.py`, `test_premarket_brief.py`, `test_premarket_send.py`, `test_telegram_ai_commands.py`, `test_weekly_setup.py`, `test_copilot_education.py`, `test_auto_analysis.py`
- Caveat: keep `test_htf_bias.py` since `htf_bias.py` is retained per FR amendment A3.
- Caveat: keep `test_intel_hub.py` + `test_trade_coach.py` since both modules are retained per A4/A5.

**V2 path (MUST SURVIVE)** — KEEP:
- `test_tv_webhook.py`, `test_notifier.py`, `test_chart_analyzer.py`, `test_alert_routing.py`, `test_alert_preferences.py`, `test_per_user_notifications.py`, `test_per_user_scoping.py`

**Shared infra (MUST SURVIVE)** — KEEP:
- `test_postgres_wrapper.py`, `test_turso_migration.py`, `test_integration_no_id_tables.py`, `test_tier_enforcement.py`, `test_forgot_password.py`, `test_market_hours.py`, `test_crypto_timezone.py`, `test_coinbase_crypto.py`

Pure file-count cut ≈ 25 of 44 test files removed (down from the 28 originally estimated because A3/A4/A5 retentions also retain their tests). Combined with the 20+ `analytics/`+`alerting/` module deletions, **15% LOC reduction is achievable** (test files alone contribute ~25k LOC; `test_intraday_rules.py` is 7,700 lines).

---

## Decision-grade summary

| Finding | Action in spec | Action in plan |
|---------|----------------|----------------|
| `compute_spy_gate` not `spy_regime_gate` | FR amendment A1 (rename in FR-407/408) | Phase A T-A1 |
| `_targets_for_long/short` are V2-load-bearing | FR amendment A2 (preserve, promote to public) | Phase A T-A1 |
| `htf_bias.py` is V2-live | FR amendment A3 (remove from Tier 3) | Phase A T-A1; runbook reflects |
| `intel_hub.py` reachable from React | FR amendment A4 (retain; trim `intel.py` instead) | Phase A T-A1; runbook reflects |
| `trade_coach.py` reachable from React | FR amendment A5 (retain) | Phase A T-A1; runbook reflects |
| `options_trade_store.py` status uncertain | FR amendment A6 (owner-confirm before delete) | Phase A T-A4 |
| Tier 3 modules have hot import sites | No FR change — sequencing fix | Phase B detailed sequencing in quickstart.md |
| No `pytest.ini` | No FR change — use explicit file list | Runbook prescribes file list |
| `intel.py` 9 routes unreferenced from React | No FR change — implementation detail | Phase C T-C7 trims them |
| `cloc` not installed | No FR change | Install before Phase D so SC-101 measurement is standard |

The first six items MUST be applied to `spec.md` before `/speckit-tasks` runs. Recommend: `/speckit-clarify` on this spec with the six findings as questions, OR direct edit to `spec.md` with these changes.
