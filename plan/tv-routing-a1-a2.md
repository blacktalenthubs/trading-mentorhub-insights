# Plan — TV Routing (A1 + A2): SPY 8/21 bias gate + SPY short whitelist

**Spec:** [`specs/41-tv-trading-system/v2-routing-notices-patterns.md`](../specs/41-tv-trading-system/v2-routing-notices-patterns.md) §A1, §A2
**Ship order:** Item #1
**Status:** In progress (2026-05-05)

---

## Problem

7 of 9 skipped alerts on 2026-05-05 were SHORTs that the user wouldn't
have taken regardless of quality (long-bias style, single-name shorts not
in repertoire). Need to gate non-SPY shorts when SPY is in long-bias
regime, and whitelist only `staged_pdh_rejection` / `staged_pdl_break` /
`vwap_reject_short` / `vwap_lose_short` for SPY shorts.

## Solution overview

```
                         ┌──────────────────┐
   TV webhook payload ──▶│ TVWebhookPayload │ (existing)
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ payload_to_     │ (existing adapter)
                         │ alert_signal    │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ _route_alert()  │  ◀── NEW (this plan)
                         │  + SPY 8/21     │
                         │    cache check  │
                         └────────┬─────────┘
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
                 ACTION (ok)           SUPPRESS or NOTICE
                       │                     │
                       ▼                     ▼
                 dispatch_signal      log + return early
                 (existing)           OR override direction
```

**Single insertion point** in `_dispatch_signal()` between the adapter
call and `_users_watching()`. Suppressed alerts never hit the DB or
Telegram.

## Files to modify

| File | Change | Why |
|------|--------|-----|
| `api/app/routers/tv_webhook.py` | Add `_spy_above_8_21()` cached helper + `_route_alert()` + integration in `_dispatch_signal` | Single-file change keeps the gate logic near the dispatch flow |
| `tests/test_tv_webhook.py` | Add `TestRoutingLogic` class with 6+ test cases | TDD coverage for both gates |

No DB schema changes. No model changes. No Pine changes.

## SPY 8/21 state source

**Approach:** in-process cache, refreshed via yfinance every 5 min.

```python
_SPY_STATE_TTL = 300  # seconds
_spy_state_cache = {"value": None, "expires_at": 0.0}

async def _spy_above_8_21() -> bool:
    """Return True if SPY's last close > both daily 8 EMA and 21 EMA."""
    now = time.time()
    if _spy_state_cache["expires_at"] > now:
        return _spy_state_cache["value"]
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_spy_state_sync)
    except Exception:
        logger.exception("SPY 8/21 fetch failed — failing open (long-bias=True)")
        return True  # fail-open: don't block legit alerts on yfinance flakes
    _spy_state_cache.update(value=result, expires_at=now + _SPY_STATE_TTL)
    return result

def _fetch_spy_state_sync() -> bool:
    import yfinance as yf
    spy = yf.Ticker("SPY")
    hist = spy.history(period="60d", interval="1d")
    if len(hist) < 22:
        return True  # insufficient data — fail-open
    closes = hist["Close"]
    ema8 = closes.ewm(span=8, adjust=False).mean().iloc[-1]
    ema21 = closes.ewm(span=21, adjust=False).mean().iloc[-1]
    last = closes.iloc[-1]
    return bool(last > ema8 and last > ema21)
```

**Fail-open rationale:** if yfinance is down, we shouldn't suppress
legitimate alerts. Default to "long-bias mode" which is the user's
typical regime anyway. The alternative (fail-closed) would silently
block actionable alerts when the data feed hiccups.

## Routing logic

```python
SPY_SHORT_WHITELIST = {
    "staged_pdh_rejection",
    "staged_pdl_break",
    "vwap_reject_short",
    "vwap_lose_short",       # added in C1 Pine work; fine to whitelist now
}

async def _route_alert(sig) -> tuple[bool, Optional[str]]:
    """Return (deliver, downgrade_to).
    
    deliver=False  → suppress entirely
    deliver=True, downgrade=None → ACTION as-is
    deliver=True, downgrade="NOTICE" → override sig.direction to NOTICE
    """
    direction = (sig.direction or "").upper()
    if direction in ("NOTICE", "BUY", "LONG"):
        return True, None  # longs + notices unchanged in v1
    
    if direction not in ("SHORT", "SELL"):
        return True, None  # unknown direction — pass through
    
    spy_long_bias = await _spy_above_8_21()
    if not spy_long_bias:
        return True, None  # SPY weak — all shorts restored
    
    rule = getattr(sig, "_tv_rule", "") or ""
    if sig.symbol != "SPY":
        return False, None  # A1: suppress non-SPY shorts when SPY strong
    
    if rule in SPY_SHORT_WHITELIST:
        return True, None  # A2: whitelist passes through
    return True, "NOTICE"  # A2: other SPY shorts → NOTICE
```

## Integration into `_dispatch_signal`

Insert immediately after the `direction = (sig.direction or "").upper()`
line (line 192) but BEFORE structural target computation (line 197+):

```python
# Routing gate (A1 + A2) — applies to SHORT direction only.
deliver, downgrade = await _route_alert(sig)
if not deliver:
    logger.info(
        "TV routing: SUPPRESSED %s/%s rule=%s (long-bias mode, non-SPY short)",
        sig.symbol, sig.direction, getattr(sig, "_tv_rule", "?"),
    )
    return {"dispatched": False, "reason": "routing_suppressed_long_bias"}

if downgrade:
    logger.info(
        "TV routing: DOWNGRADED %s/%s rule=%s → %s",
        sig.symbol, sig.direction, getattr(sig, "_tv_rule", "?"), downgrade,
    )
    sig.direction = downgrade
    direction = downgrade  # update local var
```

## Test plan (TDD — write first)

`tests/test_tv_webhook.py::TestRoutingLogic`:

| Test | Setup | Expected |
|------|-------|----------|
| `test_long_passes_unchanged` | LONG signal, SPY anywhere | deliver=True, no downgrade |
| `test_notice_passes_unchanged` | NOTICE signal | deliver=True, no downgrade |
| `test_non_spy_short_suppressed_when_spy_strong` | NVDA SHORT, mocked SPY>8/21=True | deliver=False |
| `test_non_spy_short_allowed_when_spy_weak` | NVDA SHORT, mocked SPY<8/21=False | deliver=True |
| `test_spy_short_whitelisted_rule_actions` | SPY SHORT staged_pdh_rejection, SPY>8/21 | deliver=True, no downgrade |
| `test_spy_short_non_whitelisted_downgrades` | SPY SHORT random_rule, SPY>8/21 | deliver=True, downgrade="NOTICE" |
| `test_spy_state_cache_hit_avoids_yfinance` | call helper twice within TTL | yfinance called once |
| `test_spy_state_yfinance_failure_fails_open` | mock yfinance to raise | returns True (long-bias permissive) |

Mocking strategy: `monkeypatch _spy_above_8_21` directly for routing
tests; mock `_fetch_spy_state_sync` for cache tests.

## Edge cases / discretion calls

(Per user's "use discretion where data is thin" — these are calls I
made; revisit if real-world behavior shows otherwise.)

1. **Direction case sensitivity** — `"short"` vs `"SHORT"` — uppercase
   in the gate. Adapter already normalizes.
2. **Unknown directions** — if direction is something weird like
   `"FLAT"`, pass through. The adapter coerces unknowns to `"NOTICE"`
   already so this should be rare.
3. **Cache lifetime 5 min** — long enough to amortize yfinance hits
   across a webhook burst, short enough to catch a genuine SPY break
   below 8/21 within the same session.
4. **SPY itself is non-SPY** — handled: `sig.symbol != "SPY"` checks the
   string. SPY itself takes the SPY branch.
5. **SPY 8 vs 21 simultaneous check** — user said "SPY > 8/21" meaning
   above BOTH. Code uses AND, not OR.
6. **Failed routing should still log** — every suppress / downgrade
   gets a log line for after-the-fact debugging.

## What's deliberately NOT in this PR

- **A3 wide-stop filter** — sequenced after C1 (gap-and-go stops). Don't
  ship A3 yet; it would suppress MU-style alerts before C1 fixes their
  stops.
- **A5 stage label in body** — Telegram template change, separate item.
- **B1 NOTICE audit** — separate ship-order item.
- **Pine changes** (C1, C2, C4) — separate PRs, require TV chart
  re-paste. Plan docs come later.
- **`vwap_lose_short` rule** — whitelisted now (cheap), but the actual
  Pine event ships in C1's PR. Until then no SPY alert with that rule
  will fire — defensive whitelisting causes no harm.

## Validation steps after deploy

1. Confirm registration log fires once per container start
   (existing pattern).
2. Tail `railway logs --service worker --filter "TV routing"` after a
   trading session — should see:
   - `SUPPRESSED` lines on non-SPY SHORT alerts (when SPY > 8/21)
   - `DOWNGRADED` lines on SPY SHORT alerts not in whitelist
   - No log lines on LONG/NOTICE alerts (they bypass the gate)
3. Spot-check Telegram: count of skip-worthy SHORT alerts should drop
   to near-zero compared to 2026-05-05 baseline.
4. **Rollback**: if behavior is wrong, revert the single commit. No
   schema, no Pine, no infra changes — single rollback.
