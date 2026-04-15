# Spec 40 — Implementation Plan

**Spec:** `spec.md`
**Status:** Plan (post-specify, pre-tasks)
**Created:** 2026-04-15

---

## Architecture

```
┌──────────────────────────────────────────────┐
│ Frontend (TradingPageV2 AI Coach tab)         │
│  - [ Best Setups Today ] preset button        │
│  - Chat regex: "best setups", "top picks"     │
└──────────────────┬───────────────────────────┘
                   │ GET /api/v1/ai/best-setups
                   ▼
┌──────────────────────────────────────────────┐
│ api/app/routers/ai_coach.py                   │
│  - Auth check (existing dependency)            │
│  - Tier gate (best_setups_per_day)            │
│  - Cache lookup (15-min TTL, user+watchlist)  │
│  - On miss: call analytics.ai_best_setups     │
└──────────────────┬───────────────────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│ analytics/ai_best_setups.py                   │
│  1. Load watchlist symbols (SQL)               │
│  2. For each symbol (parallel):                │
│     a. fetch current price (Alpaca)            │
│     b. fetch_prior_day(symbol)                 │
│     c. fetch_intraday last 20×5-min bars      │
│  3. Build batch Sonnet prompt                  │
│  4. Parse JSON array response                  │
│  5. Validate each pick:                        │
│     - R:R >= 1.5                               │
│     - directional sanity                       │
│     - staleness check                          │
│     - SPY-only SHORT policy                    │
│  6. Sort by R:R desc                           │
│  7. Return result + skipped list               │
└───────────────────────────────────────────────┘
```

---

## Files to Add / Modify

| File | Action | Purpose |
|---|---|---|
| `analytics/ai_best_setups.py` | NEW | Scanner logic, prompt, validation |
| `api/app/routers/ai_coach.py` | MODIFY (or NEW if doesn't exist) | Add `/best-setups` endpoint |
| `api/app/main.py` | MODIFY | Register ai_coach router if not already |
| `api/app/tier.py` | MODIFY | Add `best_setups_per_day` limit |
| `api/app/schemas/ai.py` | NEW | Pydantic response schemas |
| `web/src/api/hooks.ts` | MODIFY | Add `useBestSetups` hook |
| `web/src/components/BestSetupsCard.tsx` | NEW | Rendering component |
| `web/src/pages/TradingPageV2.tsx` | MODIFY | Preset button + chat integration |
| `tests/test_ai_best_setups.py` | NEW | Unit + integration tests |
| `specs/40-ai-coach-best-setups/tasks.md` | NEW | Task breakdown (next speckit step) |

---

## Key Functions

### `analytics/ai_best_setups.py`

```python
@dataclass
class BestSetup:
    symbol: str
    direction: str           # "LONG" | "SHORT"
    setup_type: str          # free-text AI label
    entry: float
    stop: float
    t1: float
    t2: float | None
    rr_ratio: float          # computed
    risk_per_share: float
    reward_per_share: float
    conviction: str          # "HIGH" | "MEDIUM" | "LOW"
    confluence: list[str]
    why_now: str
    current_price: float
    distance_to_entry_pct: float

@dataclass
class BestSetupsResult:
    generated_at: datetime
    watchlist_size: int
    setups_found: int
    picks: list[BestSetup]
    skipped: list[dict]      # {symbol, reason}


def generate_best_setups(user_id: int, sync_session_factory) -> BestSetupsResult:
    """Main entry point. Loads watchlist, calls AI, validates, returns ranked list."""
    ...


def _build_batch_prompt(symbols_data: list[dict]) -> str:
    """Build single Sonnet prompt with all symbols' data."""
    ...


def _parse_ai_response(text: str) -> list[dict]:
    """Parse JSON array from Sonnet; log+skip malformed entries."""
    ...


def _validate_pick(pick: dict, current_price: float) -> tuple[bool, str | None]:
    """Apply R:R, directional, staleness, SPY-SHORT rules. Returns (ok, skip_reason)."""
    ...


def _compute_rr(entry: float, stop: float, t1: float, is_long: bool) -> float:
    """Risk-to-reward ratio. Positive for both directions."""
    ...
```

### `api/app/routers/ai_coach.py`

```python
@router.get("/best-setups", response_model=BestSetupsResponse)
async def best_setups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return ranked best setups across user's watchlist. Cached 15 min."""
    # 1. Tier gate
    tier = get_user_tier(user)
    cap = get_limits(tier).get("best_setups_per_day")
    if cap is not None and _get_usage(user.id) >= cap:
        raise HTTPException(429, "Daily best-setups limit reached")

    # 2. Cache lookup
    watchlist_hash = await _hash_watchlist(user.id, db)
    cached = _cache_get(user.id, watchlist_hash)
    if cached:
        return cached

    # 3. Generate
    result = await asyncio.to_thread(
        generate_best_setups, user.id, sync_session_factory
    )

    # 4. Cache + count usage
    _cache_set(user.id, watchlist_hash, result, ttl=900)
    _db_increment_count(user.id, "best_setups", today())

    return result
```

---

## Sonnet Prompt (batch, one call per request)

```
You are a swing/day trade analyst ranking the best setups across a user's
watchlist for the upcoming session.

Your job: for each symbol, decide if there is a TRADEABLE setup right now
at a durable key level. Skip symbols with no clear setup. Rank the winners
by risk-to-reward.

You have FULL discretion on what qualifies. Read the data (MAs, PDH/PDL,
weekly/monthly levels, VWAP, RSI, recent 5-min bars) and identify the best
setup per symbol — if any. Label it in your own words.

STRONG SETUP CUES:
- Price at a durable key level (daily MA, weekly high/low, monthly pivot, PDH/PDL)
- Multi-level confluence (price at 2+ levels simultaneously)
- RSI extreme at support (<30) or resistance (>70)
- Flipped support/resistance (just-broken level being retested)
- Higher-low structure at support / lower-high at resistance

NOT A SETUP:
- Price mid-range with no structural level nearby
- Level more than 1% away from current price
- No confluence, no structure, thin volume

OUTPUT — strict JSON array, one object per qualifying setup:
[
  {
    "symbol": "<str>",
    "direction": "LONG" | "SHORT",
    "setup_type": "<free-text label, ~5-8 words>",
    "entry": <number>,
    "stop": <number>,
    "t1": <number>,
    "t2": <number or null>,
    "conviction": "HIGH" | "MEDIUM" | "LOW",
    "confluence": ["<level1>", "<level2>"],
    "why_now": "<1 sentence>"
  }
]

Return [] if no symbols have qualifying setups.

Order by your perceived risk-to-reward, best first.

[WATCHLIST DATA]
<per symbol: current price, PDH/PDL, MAs 20/50/100/200, EMAs, weekly hi/lo,
 monthly hi/lo, RSI14, last 10 × 5-min bars>
```

---

## Cache Implementation

```python
# In-memory with TTL — simple dict + expiry timestamps
_cache: dict[tuple[int, str], tuple[datetime, BestSetupsResult]] = {}

def _cache_get(user_id: int, wl_hash: str) -> BestSetupsResult | None:
    entry = _cache.get((user_id, wl_hash))
    if not entry: return None
    ts, result = entry
    if (datetime.now() - ts).total_seconds() > 900:  # 15 min
        del _cache[(user_id, wl_hash)]
        return None
    return result

def _cache_set(user_id: int, wl_hash: str, result: BestSetupsResult, ttl: int = 900):
    _cache[(user_id, wl_hash)] = (datetime.now(), result)
```

Notes:
- In-memory is fine — cache purely reduces AI cost, stale data is recoverable
- Worker restart clears cache — acceptable (next morning user re-clicks)
- If we ever scale to multi-worker, migrate to Redis

---

## Validation Rules (code-side)

```python
def _validate_pick(pick: dict, current_price: float, symbol: str) -> tuple[bool, str | None]:
    entry = pick.get("entry")
    stop = pick.get("stop")
    t1 = pick.get("t1")
    direction = pick.get("direction")

    # Sanity: required fields
    if not all(isinstance(v, (int, float)) for v in [entry, stop, t1]):
        return False, "missing entry/stop/t1"

    # Directional geometry
    if direction == "LONG":
        if not (stop < entry < t1):
            return False, f"bad geometry: LONG needs stop<entry<t1 (got {stop}/{entry}/{t1})"
    elif direction == "SHORT":
        if not (stop > entry > t1):
            return False, f"bad geometry: SHORT needs stop>entry>t1"
        # SPY-only SHORT policy
        if symbol.upper() != "SPY":
            return False, "SHORT only allowed on SPY"
    else:
        return False, f"unknown direction: {direction}"

    # R:R
    risk = abs(entry - stop)
    reward = abs(t1 - entry)
    if risk <= 0:
        return False, "zero risk"
    rr = reward / risk
    if rr < 1.5:
        return False, f"R:R {rr:.2f} below 1.5 minimum"

    # Staleness: reject if already >50% to T1
    if direction == "LONG":
        progress = (current_price - entry) / (t1 - entry) if t1 > entry else 0
    else:
        progress = (entry - current_price) / (entry - t1) if entry > t1 else 0
    if progress > 0.5:
        return False, f"stale: {int(progress*100)}% to T1 already"

    return True, None
```

---

## Phased Implementation

### Phase 1 — Backend core (~1 day)

**Tasks:**
1. Create `analytics/ai_best_setups.py` with scanner + prompt + validation
2. Add Pydantic schemas in `api/app/schemas/ai.py`
3. Add `/api/v1/ai/best-setups` endpoint in router
4. Add `best_setups_per_day` tier limits
5. Unit tests: R:R math, validation rules, JSON parse, tier gate

**Definition of done:** `curl /api/v1/ai/best-setups` (with admin JWT) returns ranked JSON.

### Phase 2 — Chat integration (~half day)

**Tasks:**
1. Preset button in AI Coach tab → calls endpoint, renders result inline
2. Natural language regex in chat input: `/best\s*setups?|top\s*picks?|ranked\s*watchlist/i`
3. BestSetupsCard component — renders picks with R:R/conviction/take button
4. Integration test: mock endpoint, verify UI renders correctly

**Definition of done:** click preset → see picks in <10s. Type "best setups" in chat → same result.

### Phase 3 — Dashboard widget (~1 day, defer if desired)

**Tasks:**
1. Morning widget on Dashboard (collapsed by default after 10:30 AM ET)
2. Auto-call endpoint at 9:25 AM ET (pre-market warm)
3. Take button wires into alerts.took flow

**Definition of done:** dashboard shows "Best Setups Today" card on morning load.

---

## Test Strategy

### Unit (`tests/test_ai_best_setups.py`)
- `test_compute_rr_long` / `test_compute_rr_short`
- `test_validate_pick_rejects_bad_geometry`
- `test_validate_pick_rejects_low_rr`
- `test_validate_pick_rejects_stale_trade`
- `test_validate_pick_spy_only_short`
- `test_parse_malformed_json_returns_empty`

### Integration (`tests/test_ai_best_setups_integration.py`)
- Mock Anthropic API (`responses` library or monkeypatch `anthropic.Anthropic`)
- Mock yfinance / Alpaca
- End-to-end: call `generate_best_setups` with mock responses, verify ranked output

### E2E (manual, during Phase 2 acceptance)
1. Log in as admin
2. Have 5 symbols on watchlist (mix of crypto + equity)
3. Click "Best Setups Today"
4. Verify: picks appear within 10 sec, ranked by R:R, no stale entries, no non-SPY SHORTs
5. Refresh within 15 min → instant cache hit, no new AI call in logs
6. Add a symbol → next call re-runs (cache busted)
7. Free user: call 2× in a day → second hits tier cap

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Sonnet returns malformed JSON | Parser tolerant — log+skip per-item failures, return valid picks |
| Sonnet hallucinates prices not in input data | Validate entry/stop/t1 are within ±5% of current price; reject outliers |
| Watchlist of 30+ symbols → token budget blown | Hard cap 25 symbols in prompt; warn UI side for oversize lists |
| Morning rush concurrent calls to same user → dupe spend | Cache key includes user_id; single-flight pattern on concurrent request |
| Cost runaway | `BEST_SETUPS_ENABLED` env kill switch; daily spend alert if tier abuse detected |
| Worker restart loses cache | Acceptable — re-runs, user doesn't notice |

---

## Open Questions (for tasks.md phase)

1. Should cache key include `session_date` so morning and EOD calls are distinct?
2. Log cost per call for monitoring? Yes — emit to `analytics.anthropic_cost` table if it exists.
3. If Sonnet times out (>30s), retry once or return partial? → **Return empty with error flag**, let user retry.
4. Admin endpoint to see all users' current best-setups cache for debugging?

---

## Ready for next step

Spec + plan complete. Next: `/speckit.tasks` to break Phase 1 into trackable units with test cases.
