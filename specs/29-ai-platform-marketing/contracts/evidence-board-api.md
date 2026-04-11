# API Contract: Evidence Board

## GET /api/v1/intel/evidence-board

**Auth**: None (public endpoint)
**Purpose**: Returns resolved trades with full evidence chain for public proof page

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| days | int | 30 | Lookback window (max 90) |
| symbol | string | null | Filter by symbol (e.g. "ETH-USD") |
| setup_type | string | null | Filter by setup type (e.g. "pdl_hold") |
| outcome | string | "all" | Filter: "all", "win", "loss" |
| limit | int | 20 | Max results (max 50) |

### Response 200

```json
{
  "trades": [
    {
      "id": 4692,
      "symbol": "ETH-USD",
      "setup_type": "ai_day_long",
      "setup_label": "PDL HOLD/RECLAIM",
      "direction": "BUY",
      "entry": 2176.50,
      "stop": 2165.00,
      "target_1": 2210.00,
      "target_2": 2245.00,
      "conviction": "HIGH",
      "score": 85,
      "message": "PDL hold — 3 bars closed above $2,176",
      "outcome": "win",
      "pnl_r": 1.5,
      "pnl_pct": 1.54,
      "replay_text": "PDL hold confirmed with 3-bar close above $2,176. Volume supported the bounce. T1 hit at $2,210 within 75 minutes.",
      "alert_time": "2026-04-10T14:30:00Z",
      "outcome_time": "2026-04-10T15:45:00Z"
    }
  ],
  "summary": {
    "total": 18,
    "wins": 13,
    "losses": 5,
    "win_rate": 72.2,
    "avg_pnl_r": 0.85
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| id | int | Alert ID (used for shareable URL) |
| symbol | string | Ticker symbol |
| setup_type | string | Alert type from DB |
| setup_label | string | Human-readable setup name |
| direction | string | "BUY" or "SHORT" |
| entry | float | Entry price level |
| stop | float | Stop loss level |
| target_1 | float | First target |
| target_2 | float | Second target |
| conviction | string | "HIGH", "MEDIUM", or "LOW" |
| score | int | Conviction score (0-100) |
| message | string | Setup description |
| outcome | string | "win", "loss", or "open" |
| pnl_r | float | P&L in risk multiples |
| pnl_pct | float | P&L percentage |
| replay_text | string | AI-generated trade analysis |
| alert_time | string | ISO timestamp when alert fired |
| outcome_time | string | ISO timestamp when outcome resolved |

### Notes
- Only returns trades where user clicked "Took" AND outcome is resolved
- No user-identifiable data in response (anonymized)
- Sorted by alert_time descending (most recent first)
