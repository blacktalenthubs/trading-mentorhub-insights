# Learning: Swing Trade Tracker

## What Exists Today

### RSI Computation
- `compute_rsi_wilder(closes: pd.Series, period=14) -> float | None` in `analytics/intraday_data.py`
- Returns a **single float** (last bar's RSI), not a series
- Called in `fetch_prior_day()` on 1y daily bars → stored as `prior_day["rsi14"]`
- Called in `get_spy_context()` on SPY 1y daily bars → stored as `spy_context["spy_rsi14"]`
- **Gap:** For crossover detection (RSI crossing 30/35/65/70), we need at least the last 2 RSI values. Current function only returns the latest.

### Daily MAs/EMAs Available
From `fetch_prior_day()` on 1y daily bars:
- **MAs:** MA20, MA50, MA100, MA200
- **EMAs:** EMA20, EMA50
- **Missing:** EMA5, EMA10 (needed for Burns-style 5/20 crossover and 10 EMA break)

From `get_spy_context()`:
- **MAs:** MA5, MA20, MA50, MA100, MA200
- **EMAs:** EMA20, EMA50
- **Missing:** SPY EMA5 (not critical — we only need SPY > EMA20 as regime gate)

### RSI Usage in Rules (Confidence Modifier Only)
In `evaluate_rules()` lines 2820-2854:
- SPY RSI < 35 → upgrade BUY confidence (medium→high)
- SPY RSI > 70 → demote BUY confidence (high→medium)
- Symbol RSI < 35 → demote BUY confidence + "crash risk" note
- Symbol RSI > 70 → "overbought" note only (no confidence change)
- **No standalone RSI alert types exist** — RSI never fires its own `AlertSignal`

### Alert Storage
- `alerts` table: `id, symbol, alert_type, direction, price, entry, stop, target_1, target_2, confidence, message, narrative, score, session_date, created_at`
- Dedup: `was_alert_fired(symbol, alert_type, session_date)` — same signal won't fire twice per session
- `active_entries` table tracks open positions for stop/target monitoring
- All 31 AlertTypes are intraday — no `swing_*` types

### Monitor Thread
- `monitor_thread.py`: daemon thread, runs `poll_cycle()` every 3 minutes during market hours
- Checks `is_market_hours()` (weekday 9:30-16:00 ET) before each poll
- **No EOD hook exists** — after market close, it just sleeps
- An EOD trigger would need a transition detector: "market was open → now closed → run EOD once"

### Market Hours
- `analytics/market_hours.py` has `is_market_hours()`, `get_session_phase()`, `is_premarket()`, `allow_new_entries()`
- No after-hours or EOD detection functions
- Need to add: `is_after_close()` or detect the open→closed transition

### Notification
- `notify(signal: AlertSignal)` sends Telegram + email, signal-type-agnostic
- Score gate: BUY signals with score < 50 are suppressed from notification
- Swing alerts can use the exact same pipeline — just add new AlertType enum values

### Page Conventions
- Every page: `ui_theme.setup_page("key")` → `ui_theme.page_header(title, subtitle)`
- `ui_theme.empty_state()` for no-data states
- Dark theme colors in `ui_theme.COLORS` dict
- Next available slot: page 10

---

## What Needs to Be Built

### 1. `compute_rsi_series()` — New Function
The existing `compute_rsi_wilder()` returns only the last RSI value. We need the last N values to detect crossovers (yesterday's RSI vs today's RSI).

**Approach:** Add a new function that returns the last N RSI values as a list:
```python
def compute_rsi_series(closes: pd.Series, period: int = 14, lookback: int = 2) -> list[float]:
```
Internally uses the same Wilder's EWM calculation but returns `rsi_series.iloc[-lookback:]` instead of `rsi_series.iloc[-1]`. The existing `compute_rsi_wilder()` remains untouched (backward compat).

### 2. Daily EMA5 and EMA10 — Add to `fetch_prior_day()`
The `hist` DataFrame already has 1y daily bars. Just add:
```python
hist["EMA5"]  = hist["Close"].ewm(span=5, adjust=False).mean()
hist["EMA10"] = hist["Close"].ewm(span=10, adjust=False).mean()
```
And include `ema5`, `ema10` in the returned dict. Also need the **previous day's** EMA5/EMA10 for crossover detection (today EMA5 > EMA20, yesterday EMA5 < EMA20).

**Approach:** Return `ema5`, `ema5_prev`, `ema10`, `ema10_prev` so crossover checks are trivial.

### 3. Swing AlertTypes — New Enum Values
```python
# RSI zone alerts
SWING_RSI_APPROACHING_OVERSOLD  = "swing_rsi_approaching_oversold"   # RSI crosses below 35
SWING_RSI_OVERSOLD              = "swing_rsi_oversold"               # RSI crosses below 30
SWING_RSI_APPROACHING_OVERBOUGHT = "swing_rsi_approaching_overbought" # RSI crosses above 65
SWING_RSI_OVERBOUGHT            = "swing_rsi_overbought"             # RSI crosses above 70

# Burns-style setups
SWING_EMA_CROSSOVER_5_20        = "swing_ema_crossover_5_20"         # Daily EMA5/20 bullish cross
SWING_200MA_RECLAIM             = "swing_200ma_reclaim"              # Close back over 200 MA + 10 EMA
SWING_PULLBACK_20EMA            = "swing_pullback_20ema"             # Pullback to rising 20 EMA

# Trade management
SWING_TARGET_HIT                = "swing_target_hit"                  # RSI reached 70
SWING_STOPPED_OUT               = "swing_stopped_out"                # MA condition violated
```

### 4. `swing_trades` DB Table
```sql
CREATE TABLE IF NOT EXISTS swing_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    alert_type    TEXT NOT NULL,
    direction     TEXT NOT NULL DEFAULT 'BUY',
    entry_price   REAL NOT NULL,
    stop_type     TEXT NOT NULL,          -- 'ema_cross_under_5_20', 'close_below_200ma', 'close_below_20ema'
    target_type   TEXT NOT NULL DEFAULT 'rsi_70',
    current_rsi   REAL,
    status        TEXT NOT NULL DEFAULT 'active',  -- 'active', 'target_hit', 'stopped', 'closed'
    pnl_pct       REAL,
    session_date  TEXT NOT NULL,          -- entry date
    closed_date   TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, session_date, alert_type)
);
```

### 5. EOD Trigger in `monitor_thread.py`
Add a state flag and EOD detection:
```python
_eod_ran_today = None  # tracks which session_date we last ran EOD for

def _monitor_loop():
    ...
    while True:
        time.sleep(interval_sec)
        if is_market_hours():
            poll_cycle(dry_run=False)
        else:
            _maybe_run_eod()  # checks if EOD already ran today, runs swing scan if not
```

The `_maybe_run_eod()` function:
- Checks `_eod_ran_today != today_session()`
- If not yet run: calls `swing_scan_eod()` then sets `_eod_ran_today = today_session()`
- Only runs on weekdays after 4:00 PM ET

### 6. `analytics/swing_rules.py` — New Module
Swing rule functions following the existing pattern:
- `check_spy_regime(spy_context) -> bool` — SPY close > EMA20
- `check_rsi_zones(symbol, rsi_today, rsi_yesterday) -> AlertSignal | None`
- `check_ema_crossover_5_20(symbol, prior_day) -> AlertSignal | None`
- `check_200ma_reclaim(symbol, prior_day) -> AlertSignal | None`
- `check_pullback_20ema(symbol, prior_day) -> AlertSignal | None`
- `evaluate_swing_rules(symbol, prior_day, spy_context, fired_today) -> list[AlertSignal]`
- `check_active_swing_trades(session) -> list[AlertSignal]` — monitor open positions for exit signals

### 7. `alerting/swing_scanner.py` — EOD Orchestrator
```python
def swing_scan_eod() -> list[AlertSignal]:
    # 1. Check SPY regime gate
    # 2. For each watchlist symbol: fetch_prior_day(), evaluate_swing_rules()
    # 3. Check active swing trades for exits
    # 4. Categorize all symbols (buy_zone, strongest, building_base, etc.)
    # 5. Store results, notify, return signals
```

### 8. `pages/10_Swing_Trades.py` — New Page
Sections:
- **Regime Status:** SPY vs 20 EMA banner (green=trending, red=not trending)
- **Active Swing Trades:** table with entry, current price, stop condition, RSI, P&L
- **Today's Swing Signals:** cards (same style as Alerts page)
- **RSI Heatmap:** watchlist symbols colored by RSI zone
- **Watchlist Categories:** Burns-style buckets (Buy Zone, Strongest, Building Base, etc.)
- **History:** past swing trades with P&L

---

## Key Design Decisions

### Separate from intraday system
Swing rules live in their own module (`swing_rules.py`), have their own orchestrator (`swing_scanner.py`), their own DB table (`swing_trades`), and their own page. They share:
- `fetch_prior_day()` / `get_spy_context()` for data
- `AlertSignal` dataclass
- `notify()` for Telegram/email
- `alert_store.record_alert()` for persistence
- `ui_theme` for page styling

### RSI crossover detection
Need **yesterday's RSI vs today's RSI** — not a rolling window. Two RSI values suffice:
- `rsi_today > 65 and rsi_yesterday <= 65` → approaching overbought
- `rsi_today > 70 and rsi_yesterday <= 70` → overbought (exit signal)
- `rsi_today < 35 and rsi_yesterday >= 35` → approaching oversold
- `rsi_today < 30 and rsi_yesterday >= 30` → oversold (buy watchlist)

### Dynamic exits
Burns doesn't use fixed price stops. His stops are:
- "Bearish 5/20 EMA cross under" → checked daily, not a price level
- "Close under 200 MA" → checked daily

This means active swing trades must be re-evaluated every EOD against current MA/EMA values. The `stop_type` field in `swing_trades` stores which condition to check.

### Score for swing signals
Swing signals scored on:
- SPY regime strength (above 20 EMA by how much?)
- RSI position (oversold bounce = higher score)
- MA confluence (multiple MAs supporting = higher score)
- Volume confirmation (above-average volume day)
- Relative strength vs SPY

---

## Risk / Edge Cases

1. **Weekend/holiday gap:** EOD scan must handle market holidays — `is_market_hours()` already guards weekdays, but stock market holidays (MLK day, etc.) are NOT checked. The EOD scan should only fire if we got fresh daily bars from yfinance.

2. **RSI whipsaw:** RSI can oscillate around 35/65 for days, firing repeated alerts. Dedup via `was_alert_fired(symbol, alert_type, session_date)` prevents same-day dupes, but daily crossback (35→36→34) across days would re-fire. Consider a 3-day cooldown for RSI zone alerts.

3. **EMA crossover whipsaw:** Same issue — EMA5/20 can cross and uncross within days. The `swing_trades` table tracking + dedup should handle this, but worth noting.

4. **yfinance rate limits:** EOD scan fetches 1y daily bars for every watchlist symbol. This is the same data `fetch_prior_day()` already fetches during intraday polling. If the last intraday poll was recent, we could cache/reuse. `@st.cache_data(ttl=300)` exists on `get_spy_context()` but NOT on `fetch_prior_day()`.

5. **Streamlit Cloud cold starts:** The daemon thread may not get a chance to run EOD if the app goes to sleep. Consider a manual "Run EOD Scan" button on the swing page as a fallback.
