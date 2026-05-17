# Contract — `analytics/regime_gate.py`

**Status**: Phase 1 design artifact for Spec 49. New module created in Phase C T-C2.
**Replaces**: the SPY-regime-gate section of `analytics/intraday_rules.py` (line 7642+).
**Source-of-truth callers**: see [data-model.md "Module 2"](../data-model.md#module-2--analyticsregime_gatepy).

## Public surface

| Symbol | Kind | Required? | Notes |
|--------|------|-----------|-------|
| `compute_spy_gate` | `function` | Yes | `(spy_bars: pd.DataFrame, spy_vwap: pd.Series) -> dict[str, Any]` returning `{gate: Literal["allow","mute"], vwap_dominance: float, above_ema: bool, hourly_break: bool, reason: str}`. Verbatim copy from `intraday_rules.py:7642`. |

## Dependency closure (private helpers that must travel with `compute_spy_gate`)

Read `intraday_rules.py:7642` and the helper calls inside the function body. Each helper:
- Keep its name and signature unchanged.
- Move it verbatim into `regime_gate.py`.
- Do NOT re-implement.

Likely candidates (verify at extraction time by reading the function body):
- A VWAP-dominance helper (e.g., `_vwap_dominance(bars, vwap) -> float`)
- An "above EMA" helper (e.g., `_above_ema_window(bars, length) -> bool`)
- An "hourly break" helper (e.g., `_detect_hourly_break(bars) -> bool`)

## Allowed imports

```python
from __future__ import annotations
from typing import Any, Literal

import pandas as pd
```

No internal `analytics.*` imports. If a helper transitively depends on a utility in `intraday_rules.py`'s wider toolbelt, choose at extraction time:
- Pull the utility into `regime_gate.py` too (preferred for ≤1–2 helpers).
- Factor it into a tiny shared `analytics/_bar_utils.py` if it has multiple consumers.

## Forbidden

- ❌ Importing anything from `analytics.intraday_rules` (file is being deleted).
- ❌ Adding any non-SPY regime functions — they're either V1 rule-engine (dead) or future work belonging to other specs.
- ❌ Coupling to the V1 polling loop — `compute_spy_gate` is a pure function and stays that way.

## Tests required at module create time

`tests/test_regime_gate.py` (NEW — replaces the scattered `compute_spy_gate` cases in `test_intraday_rules.py`):

- `test_compute_spy_gate_keys()` — returns a dict with exactly the documented keys.
- `test_gate_mute_on_bearish_regime()` — synthetic SPY bars + VWAP where SPY is below VWAP / below EMA / hourly break is `True` → `gate == "mute"`.
- `test_gate_allow_on_bullish_regime()` — synthetic SPY bars where conditions are inverse → `gate == "allow"`.
- For each possible `reason` value: one true-positive case, one true-negative case.

## Cut-over coordination

`compute_spy_gate` is currently called lazily from `monitor.py:214`. After Phase B2, `monitor.py` is deleted. The `triage-agent` currently has its own inline SPY gate logic (not importing from `intraday_rules`). Phase C should optionally migrate `triage-agent/live.py` to consume `compute_spy_gate` from this module — but the migration is **out of scope for Spec 49** unless trivial. Document the migration as a follow-up ticket if `triage-agent`'s inline gate diverges from the canonical one.

## Acceptance gate

The module ships when:
1. `python3 -c "from analytics.regime_gate import compute_spy_gate"` succeeds.
2. All `test_regime_gate.py` tests pass.
3. `compute_spy_gate`'s behavior produces identical outputs to the pre-extraction version on the same input bars (snapshot regression test recommended).
