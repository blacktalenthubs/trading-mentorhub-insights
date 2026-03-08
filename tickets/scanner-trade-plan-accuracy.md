# Scanner Trade Plan Accuracy — Stale Prices After Market Close

## Problem

The Scanner page shows **yesterday's closing price** instead of today's actual price after market close. On 2026-03-06 at 5:54 PM ET, the Scanner displayed SPY at $681.31 (yesterday's close) while the actual close was $672.38. SPY never went above $673.40 today.

Because all derived levels (Entry, Stop, Target, Support, Resistance) are calculated from this stale price, the entire Trade Plans table is off by one day after hours.

## Root Cause

### 1. `analyze_symbol()` drops today's completed bar after close

`analytics/signal_engine.py` ~line 285:

```python
today = pd.Timestamp.now().normalize()
last_bar_date = hist.index[-1].normalize()
if last_bar_date >= today and len(hist) >= 3:
    hist = hist.iloc[:-1]  # drops today's bar
```

This condition is meant to drop the **partial intraday bar during market hours** but `last_bar_date >= today` is also true **after market close** when today's bar is complete. Result: today's $672.38 bar is dropped, yesterday's $681.31 becomes `last_close`.

### 2. Intraday price overlay only runs during market hours

`pages/1_Scanner.py` ~line 374:

```python
if _market_open:  # FALSE after 4:00 PM
    for r in results:
        _live = _cached_intraday(r.symbol)
        if not _live.empty:
            r.last_close = _live["Close"].iloc[-1]
```

After close, the live price overlay never kicks in, so stale prices persist.

### 3. Even during market hours, Entry/Stop/Target use yesterday's candle

The partial-bar drop means `analyze_symbol()` always calculates plans from **yesterday's daily candle**. Only the "Price" column gets patched with live data via the intraday overlay. Entry, Stop, Target, Support, Resistance remain stale all day.

## Impact

- Trade Plans table shows wrong prices → misleading to users
- Entry/Stop/Target levels based on yesterday's structure, not today's
- "BUY ZONE" status may be wrong (SPY shows BUY ZONE at $681 but actual price is $672)
- Undermines trust in the platform

## Proposed Fix

### Quick fix — use `is_market_hours()` to gate the bar drop

```python
from analytics.market_hours import is_market_hours
if last_bar_date >= today and len(hist) >= 3 and is_market_hours():
    hist = hist.iloc[:-1]
```

### Additional improvements

1. **Extend intraday overlay to after-hours** — `fetch_intraday()` returns completed 5-min bars after close; use them even when `_market_open` is False
2. **Add "Last Updated" timestamp** to Trade Plans table so users see data freshness
3. **Consider whether Trade Plans are still needed** — alerts from `intraday_rules.py` use live 5-min bars and are far more accurate. Trade Plans may add confusion without adding value.

## Broader Question: Do We Still Need Trade Plans?

The alerts system (`intraday_rules.py` + `monitor.py`) works off live 5-minute bars and has proven accurate. Trade Plans use daily bars and are inherently one-day stale for intraday levels. Options to consider:

- **Keep but fix**: Fix the staleness, add "as of" timestamps, make levels update intraday
- **Downgrade to reference only**: Show daily S/R levels as context, not actionable trade plans
- **Remove entirely**: Rely on the alerts system for actionable signals, simplify the Scanner

## Files Involved

| File | Role |
|------|------|
| `analytics/signal_engine.py` | `analyze_symbol()` — bar drop logic, level calculations |
| `pages/1_Scanner.py` | Scanner page — display, intraday overlay |
| `analytics/market_data.py` | `fetch_ohlc()` — yfinance daily data source |

## Related

- Alert system (`intraday_rules.py`) is unaffected — uses live 5-min bars
- Daily plans table (`daily_plans`) stores the stale values from `analyze_symbol()`
