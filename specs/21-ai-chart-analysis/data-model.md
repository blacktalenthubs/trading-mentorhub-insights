# Data Model: AI Chart Analysis

## Entities

### User (modified)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| auto_analysis_enabled | Boolean | False | Enable AI analysis on alert delivery |

### ChartAnalysis (new table)
| Field | Type | Notes |
|-------|------|-------|
| id | Integer PK | Auto-increment |
| user_id | Integer FK → users | Who requested the analysis |
| symbol | String(20) | Ticker analyzed |
| timeframe | String(10) | "1m", "5m", "1H", "D", "W", etc. |
| direction | String(10) | "LONG", "SHORT", "NO_TRADE" |
| entry_price | Float | Suggested entry (nullable for NO_TRADE) |
| stop_price | Float | Stop loss (nullable for NO_TRADE) |
| target_1 | Float | First target (nullable) |
| target_2 | Float | Second target (nullable) |
| rr_ratio | Float | Risk/reward ratio |
| confidence | String(10) | "HIGH", "MEDIUM", "LOW" |
| confluence_score | Integer | 0-10 multi-timeframe alignment |
| reasoning | Text | Full AI reasoning text |
| higher_tf_summary | Text | What higher timeframes show |
| historical_ref | Text | Win rate reference if available |
| actual_outcome | String(20) | "WIN", "LOSS", "SCRATCH", "PENDING", NULL |
| outcome_pnl | Float | Actual P&L when resolved (nullable) |
| created_at | Timestamp | When analysis was created |

**Unique constraint**: None (users can analyze same symbol multiple times)
**Index**: (user_id, created_at DESC) for journal queries

### UserAnalysisPrefs (uses existing user_alert_category_prefs pattern)
| Field | Type | Notes |
|-------|------|-------|
| user_id | Integer FK | References users.id |
| category_id | String | Alert category for auto-analysis toggle |
| auto_analysis | Boolean | Whether to auto-analyze alerts of this category |

## State Transitions

### ChartAnalysis.actual_outcome
```
NULL → "PENDING" (user marks as "Took It")
"PENDING" → "WIN" (target hit or manual close in profit)
"PENDING" → "LOSS" (stop hit or manual close at loss)
"PENDING" → "SCRATCH" (closed at breakeven)
NULL → stays NULL (user never took the trade)
```

## Confluence Score Breakdown
| Component | Weight | Description |
|-----------|--------|-------------|
| Trend alignment | 0-4 | All TFs same direction = 4, one conflict = 2, opposing = 0 |
| Level proximity | 0-3 | No conflicting levels on higher TF = 3, near resistance on higher = 0 |
| Momentum alignment | 0-3 | RSI + MA slopes all agree = 3, divergence = 0 |
| **Total** | **0-10** | |
