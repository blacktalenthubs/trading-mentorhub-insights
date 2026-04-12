# Data Model: Swing Scanner Price Refresh

## Modified Entities

### alerts table (add columns)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| setup_level | REAL | NULL | Key price level for the setup (EMA value, support level) |
| setup_condition | TEXT | NULL | Human-readable condition ("pullback to 20 EMA", "hold above 200 MA") |
| refreshed_entry | REAL | NULL | Updated entry price after premarket refresh |
| refreshed_stop | REAL | NULL | Updated stop after refresh |
| refreshed_at | TIMESTAMP | NULL | When the refresh ran |
| gap_invalidated | INTEGER | 0 | 1 if gap >5% invalidated the setup |
| gap_pct | REAL | NULL | Overnight gap percentage from setup level |

### swing_trades table (add columns)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| setup_level | REAL | NULL | Mirrors alerts.setup_level for the trade |
| setup_condition | TEXT | NULL | Mirrors alerts.setup_condition |
| refreshed_entry | REAL | NULL | Updated entry after refresh |

## State Transitions

### Alert refresh lifecycle
```
FIRED (3:30 PM) → prices are prior_day close
    ↓
REFRESHED (9:00 AM) → prices updated to premarket
    ↓
VALID (gap < 5%) or INVALIDATED (gap >= 5%)
```

## Setup Level Mapping

Each swing rule maps to a setup level:

| Swing Rule | Setup Level | Condition |
|-----------|-------------|-----------|
| ema_crossover_5_20 | EMA20 value | EMA5 crosses above EMA20 |
| 200ma_reclaim | 200 MA value | Close reclaims above 200 MA |
| pullback_20ema | 20 EMA value | Pullback to rising 20 EMA |
| rsi_30_bounce | Low of bounce bar | RSI crosses above 30 |
| 200ma_hold | 200 MA value | Low holds above 200 MA |
| 50ma_hold | 50 MA value | Low holds above 50 MA |
| weekly_support | Prior week low | Close holds at weekly low |
| candle_patterns | Support level | Hammer/engulfing at support |
