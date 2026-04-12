# Research Notes: Swing Scanner Price Refresh

## Decision 1: Refresh Timing

**Decision**: Run premarket refresh at 9:00 AM ET as a new APScheduler job.

**Rationale**:
- Premarket brief already runs at 9:15 AM — placing refresh at 9:00 gives 15 minutes for prices to propagate before the brief
- 9:00 AM is early enough that premarket quotes are available for most equities
- Can reuse the existing APScheduler pattern in `main.py`

**Alternatives Considered**:
- Run at 8:00 AM: Too early, premarket data may be sparse
- Run at 9:15 AM alongside premarket brief: Risks delaying the brief if refresh takes long
- Run continuously every 5 min: Overkill, wastes resources

## Decision 2: Price Source for Refresh

**Decision**: Use `yfinance` premarket data for equities, Coinbase API for crypto.

**Rationale**:
- yfinance `Ticker.info["preMarketPrice"]` provides premarket quotes
- Fallback to `Ticker.fast_info["lastPrice"]` if premarket not available
- Crypto uses Coinbase (already implemented in spec 22)
- No new dependencies needed

**Alternatives Considered**:
- Polygon API: Better data but costs $29+/mo — overkill for 1x daily refresh
- Just use yesterday's close + gap %: Doesn't help with EMA recalculation

## Decision 3: Entry Format Change

**Decision**: Change swing rules to return condition-based entries alongside numeric prices.

**Rationale**:
- "Entry: near 20 EMA ($657)" is valid regardless of gap
- The numeric price is still provided but framed as the level, not the fixed entry
- Stops are already condition-based in the `stop_map` (e.g., "close_below_20ema")

**Alternatives Considered**:
- Keep fixed prices, just refresh them: Better than nothing but doesn't solve the conceptual problem
- Remove prices entirely: Too vague — traders want specific levels

## Decision 4: Gap Invalidation Threshold

**Decision**: 5% gap from the setup level (not just from prior close).

**Rationale**:
- A "pullback to 20 EMA" setup is invalid if price is 5%+ above the EMA
- Measuring from the setup level (EMA, support) is more meaningful than from close
- 5% accommodates normal overnight moves while catching large gaps

**Alternatives Considered**:
- 3% threshold: Too aggressive, would invalidate many valid setups after normal gap-ups
- 10% threshold: Too loose, would still show clearly stale setups

## Decision 5: Protected File Modification Approach

**Decision**: Create a new `alerting/swing_refresher.py` module. Minimize changes to `swing_scanner.py` and `swing_rules.py`.

**Rationale**:
- Constitution requires impact analysis for protected files
- New module handles refresh logic without modifying the scan/rule evaluation
- Only change to `swing_rules.py`: add `setup_level` and `setup_condition` fields to AlertSignal returns
- Only change to `swing_scanner.py`: store `setup_level` in the alert record

**Alternatives Considered**:
- Modify swing_scanner.py heavily: Higher risk, more constitution gates
- Build refresh into notifier.py: Wrong responsibility — notifier sends, doesn't analyze
