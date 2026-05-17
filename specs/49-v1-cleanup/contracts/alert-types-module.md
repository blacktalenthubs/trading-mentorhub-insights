# Contract — `analytics/alert_types.py`

**Status**: Phase 1 design artifact for Spec 49. New module created in Phase C T-C1.
**Replaces**: the live type-vocabulary header of `analytics/intraday_rules.py`.
**Source-of-truth callers**: see [data-model.md "Module 1"](../data-model.md#module-1--analyticsalert_typespy).

## Public surface

| Symbol | Kind | Required? | Notes |
|--------|------|-----------|-------|
| `AlertType` | `enum.Enum` (str-valued) | Yes | Verbatim copy from `intraday_rules.py:175`. ~60 members spanning MA bounces, S/R holds, breakouts, VWAP events, HTF taxonomy. Do not rename members — Pine JSON payloads encode the string values. |
| `AlertSignal` | `@dataclass` | Yes | Verbatim copy from `intraday_rules.py:320`. Fields used by `tv_webhook.py`, `ai_coach.py`, `settings.py`, `notifier.py`, `alert_store.py`. |
| `targets_for_long` | `function` | Yes | Promoted from `_targets_for_long`. Public name. Signature `(entry, stop, atr) → dict`. Called from `tv_webhook.py:378`. |
| `targets_for_short` | `function` | Yes | Promoted from `_targets_for_short`. Mirror. |

## Allowed imports (the dependency closure)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
```

No `analytics.*` imports. No third-party imports beyond stdlib.

## Forbidden

- ❌ Re-importing anything from `analytics.intraday_rules` (the file is being deleted).
- ❌ Adding any `check_*` rule function — those are V1 rule-engine and stay deleted.
- ❌ Adding scoring functions — V1.
- ❌ Adding scheduling or polling logic — belongs in `monitor.py` (deleted) or future `triage-agent` work.

## Tests required at module create time

`tests/test_alert_types.py` (NEW — replaces relevant cases from `test_intraday_rules.py`):

- `test_alert_type_enum_str_values()` — every member's `value` is a non-empty string.
- `test_alert_type_member_count()` — matches Pine's emitted taxonomy count (read from `pine_scripts/active/ALERTS.md` — current count: ~60).
- `test_alert_signal_dataclass_roundtrip()` — `dataclasses.asdict(AlertSignal(...))` round-trips a representative instance.
- `test_targets_for_long_monotone()` — `t1 > entry`, `runner > t1`, `rr_t1 > 0`, `rr_runner > rr_t1`.
- `test_targets_for_short_monotone()` — mirror.

## Acceptance gate

The module ships when:
1. `python3 -c "from analytics.alert_types import AlertType, AlertSignal, targets_for_long, targets_for_short"` succeeds.
2. All five tests above pass.
3. Spec 49 importer rewrite checklist (data-model.md) is applied to every V2 consumer.
4. `grep -r "from analytics.intraday_rules import" .` returns zero rows (SC-104).
