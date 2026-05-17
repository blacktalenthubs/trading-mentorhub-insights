# Extracted Module Signatures — Spec 49 (Phase 1 Design)

**Purpose**: Defines the public surface of the two new modules created in Phase C (extraction from `analytics/intraday_rules.py`). For a cleanup spec, this stands in for the conventional "data model" — the new file boundaries are the structural design output.

**Source of live symbols**: [research.md §2](./research.md#2-live-symbols-in-analyticsintraday_rulespy-resolves-fr-407--fr-408-surface).

---

## Module 1 — `analytics/alert_types.py`

**Replaces**: the live header of `analytics/intraday_rules.py` (lines 1–~500 effectively — the type vocabulary).
**Purpose**: Canonical enum + dataclass + target-computation helpers consumed by the V2 path. The single place every V2 consumer imports the alert type system.

### Public exports

| Symbol | Kind | Signature | Live consumers |
|--------|------|-----------|----------------|
| `AlertType` | `enum.Enum` | str-valued enum; ~60 members covering MA bounces, S/R holds, breakouts, VWAP events, HTF taxonomy. Source: `intraday_rules.py:175`. Preserved verbatim. | `tv_webhook.py:41`, `tv_signal_adapter.py:33`, `ai_coach.py:134`, `settings.py:397`, `alerting/notifier.py`, `alerting/alert_store.py` |
| `AlertSignal` | `@dataclass` | Fields: `symbol: str, kind: AlertType, side: Literal["LONG","SHORT","NOTICE"], price: float, fired_at: datetime, meta: dict[str, Any]`. (Verify exact field list at extraction time — `intraday_rules.py:320`.) | `tv_webhook.py`, `ai_coach.py`, `settings.py`, `notifier.py`, `alert_store.py` |
| `targets_for_long` | function | `(entry: float, stop: float, atr: float) -> dict[str, float]` returning `{t1, runner, rr_t1, rr_runner}`. **Promoted from `_targets_for_long`** per FR amendment A2. | `tv_webhook.py:378` |
| `targets_for_short` | function | `(entry: float, stop: float, atr: float) -> dict[str, float]` mirror of above. **Promoted from `_targets_for_short`** per FR amendment A2. | `tv_webhook.py:378` |

### Allowed imports (the dependency closure)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
```

No internal `analytics.*` imports. No third-party imports beyond Python stdlib. If extraction surfaces a stdlib helper used inline (e.g., a constants module), include it explicitly here before extraction.

### Test surface

`tests/test_alert_types.py` (NEW — replaces `test_intraday_rules.py`'s top-of-file `AlertType` + `AlertSignal` tests):
- `AlertType` is an enum; every member is str-valued; cardinality matches Pine's emitted taxonomy.
- `AlertSignal` round-trips via `dataclasses.asdict`.
- `targets_for_long`: t1 above entry, runner above t1, R/R values positive.
- `targets_for_short`: mirror.

---

## Module 2 — `analytics/regime_gate.py`

**Replaces**: the SPY-regime gate at `intraday_rules.py:7642` plus its direct helpers.
**Purpose**: One callable used by the triage agent (post-extraction) to determine whether SHORT alerts on non-index symbols should be muted given the current SPY regime.

### Public exports

| Symbol | Kind | Signature | Live consumers |
|--------|------|-----------|----------------|
| `compute_spy_gate` | function | `(spy_bars: pd.DataFrame, spy_vwap: pd.Series) -> dict[str, Any]` returning `{gate: Literal["allow","mute"], vwap_dominance: float, above_ema: bool, hourly_break: bool, reason: str}`. Source: `intraday_rules.py:7642`. Function body is preserved; helpers it calls travel with it. | `monitor.py:214` (lazy — being deleted with V1); **future**: `triage-agent/live.py` once monitor.py is gone (today `triage-agent` does not import this; gate logic lives elsewhere there. Coordinate the cut-over in Phase C.) |

### Dependency closure (must travel with `compute_spy_gate`)

Read `intraday_rules.py:7642–~7800` and the helper calls inside `compute_spy_gate`'s body. Likely includes (verify at extraction time):

- A VWAP-dominance helper (e.g., `_vwap_dominance(bars, vwap) -> float`)
- An "above EMA" helper (e.g., `_above_ema_window(bars, length) -> bool`)
- An "hourly break" helper (e.g., `_detect_hourly_break(bars) -> bool`)

Each helper: keep its name and signature unchanged; move it verbatim into `regime_gate.py`. Do NOT re-implement.

### Allowed imports

```python
from __future__ import annotations
from typing import Any, Literal

import pandas as pd
```

Stdlib + pandas. No internal `analytics.*` imports. If a helper transitively depends on something in `intraday_rules.py`'s utility belt, decide at extraction: pull that helper into `regime_gate.py` too, OR factor it into a tiny shared `analytics/_bar_utils.py` if it has multiple consumers.

### Test surface

`tests/test_regime_gate.py` (NEW — replaces the `compute_spy_gate` tests currently scattered in `test_intraday_rules.py`):
- `compute_spy_gate` returns the documented keys.
- `gate == "mute"` when SPY VWAP-dominance > threshold AND below EMA AND hourly_break.
- `gate == "allow"` in the inverse regimes.
- Two canonical test cases per `reason` value (one true-positive, one true-negative).

---

## What does NOT carry forward

Everything else in `intraday_rules.py` — ~60 `check_*` rule functions, V1 scoring (`score_v1`, `score_v2`), EMA bounce variants, `evaluate_rules` orchestrator, candle-pattern detectors — is deleted with the file at end of Phase C. None has V2 consumers per [research.md §2](./research.md#2-live-symbols-in-analyticsintraday_rulespy-resolves-fr-407--fr-408-surface).

---

## Importer rewrite checklist (Phase C T-C3)

Every place that imports from `analytics.intraday_rules` must repoint:

| Importer | Old | New |
|----------|-----|-----|
| `api/app/routers/tv_webhook.py:41` | `from analytics.intraday_rules import AlertType` | `from analytics.alert_types import AlertType` |
| `api/app/routers/tv_webhook.py:378` | `from analytics.intraday_rules import _targets_for_long, _targets_for_short` (calls these inline) | `from analytics.alert_types import targets_for_long, targets_for_short` + rename call sites |
| `api/app/routers/ai_coach.py:134` | `from analytics.intraday_rules import AlertSignal, AlertType` | `from analytics.alert_types import AlertSignal, AlertType` |
| `api/app/routers/settings.py:397` | `from analytics.intraday_rules import AlertSignal, AlertType` | `from analytics.alert_types import AlertSignal, AlertType` |
| `analytics/tv_signal_adapter.py:33` | `from analytics.intraday_rules import AlertSignal, AlertType` | `from analytics.alert_types import AlertSignal, AlertType` |
| `alerting/notifier.py` | `from analytics.intraday_rules import AlertSignal, AlertType` | `from analytics.alert_types import AlertSignal, AlertType` |
| `alerting/alert_store.py` | `from analytics.intraday_rules import AlertSignal, AlertType` | `from analytics.alert_types import AlertSignal, AlertType` |

For `compute_spy_gate`:
- `monitor.py:214` will be deleted with V1; no rewrite needed.
- If `triage-agent/live.py` adopts `compute_spy_gate` (its own SPY gate logic is currently inline per the earlier audit), add: `from analytics.regime_gate import compute_spy_gate`. Coordinate this cut-over inside Phase C.

After the rewrite, **`grep -r "from analytics.intraday_rules" .` must return zero rows** before `intraday_rules.py` is deleted (SC-104).

---

## Why this matters for the spec

This module-boundary design is the single concrete commitment the spec makes about V2's surface. After extraction:

- V2 consumers depend on two small, focused modules with documented public surfaces — not a 9,438-LOC dumping ground.
- The CLAUDE.md "Protected Files" list (FR-413) names `analytics/alert_types.py` and `analytics/regime_gate.py` instead of `intraday_rules.py`. Outside agents see a clean surface, not a 9k-line file full of mostly dead code.
- Spec 51 (Chart Critique) and Spec 52 (Pattern Education Live) can both consume `AlertType` cleanly without dragging in the V1 rule-engine body.
