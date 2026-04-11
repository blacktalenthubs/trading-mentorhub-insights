# Data Model: AI Evidence Board

## No New Tables Required

The evidence board reads from existing tables. No schema changes needed.

## Data Sources (Read-Only)

### alerts table (existing)
| Field | Used For |
|-------|----------|
| id | Evidence card ID, shareable URL |
| symbol | Filter + display |
| alert_type | Setup type label |
| direction | BUY/SHORT badge |
| price | Price at alert time |
| entry | Entry level |
| stop | Stop level |
| target_1 | T1 level |
| target_2 | T2 level |
| confidence | Conviction badge |
| message | Setup description |
| score | Conviction score |
| session_date | Date filter |
| created_at | Alert timestamp |

### trade_journal table (existing)
| Field | Used For |
|-------|----------|
| alert_id | Join to alerts |
| outcome | WIN/LOSS/OPEN badge |
| pnl_r | P&L in R-multiples |
| replay_text | AI analysis text |
| session_date | Date filter |

### real_trades table (existing)
| Field | Used For |
|-------|----------|
| symbol | Join key |
| entry_price | Verified entry |
| exit_price | Verified exit (if closed) |
| pnl | Dollar P&L |
| status | open/closed |

## API Response Shape

```
GET /api/v1/intel/evidence-board?days=30&outcome=all

[
  {
    "id": 4692,
    "symbol": "ETH-USD",
    "setup_type": "PDL HOLD/RECLAIM",
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
    "replay_text": "PDL hold confirmed with volume...",
    "alert_time": "2026-04-10T14:30:00",
    "outcome_time": "2026-04-10T15:45:00"
  }
]
```
