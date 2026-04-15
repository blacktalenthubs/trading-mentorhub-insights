# Spec 40 — Task Breakdown (Phase 1 Backend)

**Spec:** `spec.md` | **Plan:** `plan.md`
**Status:** Tasks (post-plan, pre-implement)
**Target:** Phase 1 only — backend endpoint + validation + tests

---

## Legend

- 🧪 = Test task (write first per TDD)
- 🔨 = Implementation task
- 📝 = Documentation / wiring
- ⏱ = Estimate in minutes

---

## T1 — Pydantic schemas & R:R math

### T1.1 🧪 Write R:R unit tests ⏱ 15
`tests/test_ai_best_setups.py::TestRRMath`

Cases:
- `test_rr_long_normal` — entry 100, stop 98, t1 105 → R:R = 2.5
- `test_rr_short_normal` — entry 100, stop 102, t1 95 → R:R = 2.5
- `test_rr_long_min_risk_edge` — entry 100, stop 99.99, t1 101 → R:R ≈ 100
- `test_rr_zero_risk_raises` — entry==stop → raises `ValueError`
- `test_rr_long_t1_below_entry` → raises `ValueError` (bad geometry caller's problem)

### T1.2 🔨 Implement `_compute_rr()` helper ⏱ 10
`analytics/ai_best_setups.py`
```python
def _compute_rr(entry: float, stop: float, t1: float, is_long: bool) -> float:
    risk = abs(entry - stop)
    if risk <= 0: raise ValueError("zero risk")
    reward = abs(t1 - entry)
    return reward / risk
```

### T1.3 🔨 Create Pydantic response schemas ⏱ 15
`api/app/schemas/ai.py`

- `BestSetupPick` (all fields from spec §8)
- `SkippedSymbol` (symbol, reason)
- `BestSetupsResponse` (generated_at, watchlist_size, setups_found, picks[], skipped[])

---

## T2 — Validation layer

### T2.1 🧪 Write validation unit tests ⏱ 30
`tests/test_ai_best_setups.py::TestValidatePick`

Cases:
- `test_valid_long` → (True, None)
- `test_valid_short_spy` → (True, None)
- `test_short_rejected_non_spy` → (False, "SHORT only allowed on SPY")
- `test_long_bad_geometry_stop_above_entry` → False
- `test_long_bad_geometry_t1_below_entry` → False
- `test_short_bad_geometry_t1_above_entry` → False
- `test_rr_below_15_rejected` → False
- `test_stale_long_past_halfway` — entry 100, t1 110, current 106 → stale (60% to T1)
- `test_stale_short_past_halfway` → stale
- `test_not_stale_just_entered` — entry 100, t1 110, current 101 → OK
- `test_missing_fields_rejected` → False with "missing entry/stop/t1"
- `test_outlier_entry_rejected` — entry 50% away from current price → False

### T2.2 🔨 Implement `_validate_pick()` ⏱ 25
`analytics/ai_best_setups.py` — full validation logic per plan §Validation Rules.

Includes outlier check: reject if `|entry - current_price| / current_price > 0.05` (5% away = hallucinated).

---

## T3 — Prompt builder

### T3.1 🧪 Write prompt tests ⏱ 20
`tests/test_ai_best_setups.py::TestPromptBuilder`

Cases:
- `test_prompt_includes_all_symbols` — 3 symbols in → all 3 present in output
- `test_prompt_caps_at_25_symbols` — 30 symbols in → only 25 in prompt + warning
- `test_prompt_includes_mas` — for each symbol, 20/50/100/200 MA values present
- `test_prompt_includes_weekly_monthly` — prior_week_high/low + prior_month_high/low
- `test_prompt_includes_rsi` — rsi14 value present
- `test_prompt_includes_5m_bars` — last 10 bars OHLCV present
- `test_prompt_handles_missing_level_data` — symbol without MAs → skipped fields, no crash

### T3.2 🔨 Implement `_build_batch_prompt()` ⏱ 30
`analytics/ai_best_setups.py`

Inputs: `list[dict]` per symbol (current_price, prior_day dict, bars_5m).
Output: prompt string with system instructions + structured data per symbol.

Use the prompt template from plan §Sonnet Prompt.

---

## T4 — Response parser

### T4.1 🧪 Write parser tests ⏱ 20
`tests/test_ai_best_setups.py::TestResponseParser`

Cases:
- `test_parse_valid_json_array` — 3 picks → 3 dicts returned
- `test_parse_empty_array` → `[]`
- `test_parse_malformed_json` → `[]` + logged
- `test_parse_wrapped_in_markdown` — `\`\`\`json\n[...]\n\`\`\`` → parsed correctly
- `test_parse_extra_prose_around_json` — "Here are the setups: [...]" → parsed
- `test_parse_partial_corrupt_item_skipped` — 3 picks, 2nd missing "symbol" → returns 2 valid

### T4.2 🔨 Implement `_parse_ai_response()` ⏱ 20
`analytics/ai_best_setups.py`

Strategy: find first `[` and last `]`, attempt `json.loads` on substring. Per-item try/except so one bad pick doesn't kill the whole response.

---

## T5 — Data fetching per symbol

### T5.1 🔨 Implement `_fetch_symbol_data(symbol)` ⏱ 20
`analytics/ai_best_setups.py`

Returns `dict | None`:
```python
{
  "symbol": str,
  "current_price": float,
  "prior_day": dict,       # from fetch_prior_day
  "bars_5m": list[dict],   # last 10 bars
}
```

Reuses `fetch_prior_day`, `fetch_intraday` / `fetch_intraday_crypto`. Returns None if data unavailable (logged warning).

### T5.2 🔨 Parallel fetch for all watchlist symbols ⏱ 15
Use `ThreadPoolExecutor(max_workers=5)` to fetch symbols concurrently. Cap total wait at 15 sec; skip slow symbols.

---

## T6 — Anthropic call

### T6.1 🔨 Implement `_call_sonnet(prompt)` ⏱ 15
`analytics/ai_best_setups.py`

```python
def _call_sonnet(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CLAUDE_MODEL_SONNET,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        timeout=30.0,
    )
    return response.content[0].text.strip()
```

Logs: elapsed time, input+output tokens, cost estimate.

### T6.2 🧪 Mock Anthropic in integration test ⏱ 20
`tests/test_ai_best_setups.py::TestIntegration`

Monkeypatch `anthropic.Anthropic` to return canned JSON. Verify downstream parse + validate + rank.

---

## T7 — Main orchestrator

### T7.1 🔨 Implement `generate_best_setups()` ⏱ 30
`analytics/ai_best_setups.py` — ties everything together per plan architecture.

```python
def generate_best_setups(user_id: int, sync_session_factory) -> BestSetupsResult:
    # 1. Load watchlist
    # 2. Parallel fetch per symbol
    # 3. Build batch prompt
    # 4. Sonnet call
    # 5. Parse response
    # 6. Validate each pick
    # 7. Sort by R:R desc
    # 8. Return result
```

### T7.2 🧪 Integration test ⏱ 25
`tests/test_ai_best_setups.py::TestEndToEnd`

Mock data + Sonnet. Cases:
- Empty watchlist → `setups_found=0`, no AI call
- All symbols pass validation → ranked by R:R
- Mixed valid/invalid → only valid in picks, rest in skipped
- Sonnet timeout → return empty result with error flag

---

## T8 — Cache layer

### T8.1 🧪 Cache unit tests ⏱ 15
`tests/test_ai_best_setups.py::TestCache`

- `test_cache_miss_returns_none`
- `test_cache_hit_within_ttl`
- `test_cache_expired_returns_none`
- `test_cache_keyed_per_user`
- `test_cache_keyed_per_watchlist_hash`

### T8.2 🔨 Implement in-memory cache ⏱ 15
Module-level dict with TTL. Functions `_cache_get`, `_cache_set`, `_hash_watchlist`.

---

## T9 — API endpoint

### T9.1 🔨 Add tier limit ⏱ 5
`api/app/tier.py`

```python
"best_setups_per_day": 1    # free
"best_setups_per_day": 20   # pro
"best_setups_per_day": None # premium
```

### T9.2 🔨 Create `/api/v1/ai/best-setups` endpoint ⏱ 30
`api/app/routers/ai_coach.py` (create if absent, else modify)

Full endpoint per plan. Register router in `api/app/main.py` if not wired.

### T9.3 🧪 Endpoint integration test ⏱ 25
`tests/test_ai_best_setups_endpoint.py`

Cases:
- `test_unauthorized_returns_401`
- `test_free_tier_first_call_succeeds`
- `test_free_tier_second_call_blocked`
- `test_pro_tier_20_calls_allowed`
- `test_cache_hit_no_ai_call` — 2nd call within 15 min → mock verified not called
- `test_watchlist_change_busts_cache`

---

## T10 — Kill switch & observability

### T10.1 🔨 Add `BEST_SETUPS_ENABLED` env flag ⏱ 10
Default `true`. At endpoint entry:
```python
if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0"):
    raise HTTPException(503, "Feature disabled")
```

### T10.2 🔨 Cost + latency logging ⏱ 10
Log on every generation:
```
INFO best_setups: user=X watchlist=N picks=M skipped=K elapsed=Ts tokens=in/out cost=$Y
```

---

## Task summary

| # | Task | Type | Est | Depends on |
|---|---|---|---|---|
| T1.1 | R:R tests | 🧪 | 15 | — |
| T1.2 | `_compute_rr` | 🔨 | 10 | T1.1 |
| T1.3 | Pydantic schemas | 🔨 | 15 | — |
| T2.1 | Validation tests | 🧪 | 30 | T1.2 |
| T2.2 | `_validate_pick` | 🔨 | 25 | T2.1 |
| T3.1 | Prompt tests | 🧪 | 20 | — |
| T3.2 | `_build_batch_prompt` | 🔨 | 30 | T3.1 |
| T4.1 | Parser tests | 🧪 | 20 | — |
| T4.2 | `_parse_ai_response` | 🔨 | 20 | T4.1 |
| T5.1 | `_fetch_symbol_data` | 🔨 | 20 | — |
| T5.2 | Parallel fetch | 🔨 | 15 | T5.1 |
| T6.1 | `_call_sonnet` | 🔨 | 15 | — |
| T6.2 | Sonnet mock test | 🧪 | 20 | T6.1 |
| T7.1 | `generate_best_setups` | 🔨 | 30 | T2.2, T3.2, T4.2, T5.2, T6.1 |
| T7.2 | Integration test | 🧪 | 25 | T7.1 |
| T8.1 | Cache tests | 🧪 | 15 | — |
| T8.2 | Cache impl | 🔨 | 15 | T8.1 |
| T9.1 | Tier limit | 🔨 | 5 | — |
| T9.2 | Endpoint | 🔨 | 30 | T7.1, T8.2, T9.1 |
| T9.3 | Endpoint tests | 🧪 | 25 | T9.2 |
| T10.1 | Kill switch | 🔨 | 10 | T9.2 |
| T10.2 | Logging | 🔨 | 10 | T7.1 |

**Total estimate: ~7 hours** (includes tests, tests drive implementation)

---

## Suggested implementation order (TDD)

1. **Scaffold** (T1.3, T9.1, T10.1) — tiny config + schemas
2. **Pure logic with tests first** (T1.1→T1.2, T2.1→T2.2, T3.1→T3.2, T4.1→T4.2, T8.1→T8.2)
3. **Data layer** (T5.1, T5.2)
4. **AI call + mock test** (T6.1, T6.2)
5. **Orchestrator + test** (T7.1, T7.2)
6. **Endpoint + test** (T9.2, T9.3)
7. **Observability** (T10.2)

---

## Definition of Done (Phase 1)

- [ ] All T1-T10 tasks complete
- [ ] `pytest tests/test_ai_best_setups*.py` green
- [ ] `curl -H "Auth: Bearer <admin>" /api/v1/ai/best-setups` returns ranked JSON
- [ ] No Anthropic calls on cache hit (log-verified)
- [ ] Free tier user hits 1/day cap, gets 429
- [ ] Feature kill switch works (env flag)

Ready for `/speckit.implement`.
