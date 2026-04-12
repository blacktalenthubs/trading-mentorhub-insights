# API Contracts: Swing Price Refresh

No new API endpoints needed — this feature is a backend scheduler job + DB updates.

## Modified Responses

### GET /api/v1/alerts/today (existing)

Alert objects now include refresh fields:

```json
{
  "id": 1234,
  "symbol": "SPY",
  "alert_type": "swing_pullback_20ema",
  "price": 659.22,
  "entry": 659.22,
  "stop": 655.52,
  "target_1": 665.00,
  "setup_condition": "Pullback to rising 20 EMA",
  "setup_level": 657.81,
  "refreshed_entry": 673.50,
  "refreshed_stop": 668.00,
  "refreshed_at": "2026-04-08T09:00:15Z",
  "gap_invalidated": false,
  "gap_pct": 2.17
}
```

### Invalidated alert example:

```json
{
  "id": 1235,
  "symbol": "GOOGL",
  "alert_type": "swing_ema_crossover_5_20",
  "price": 305.46,
  "entry": 305.46,
  "setup_condition": "EMA5 crosses above EMA20",
  "setup_level": 297.18,
  "refreshed_entry": null,
  "refreshed_at": "2026-04-08T09:00:15Z",
  "gap_invalidated": true,
  "gap_pct": 6.8
}
```

## Frontend Display Logic

```
if alert.gap_invalidated:
    show dimmed with "Setup invalidated — {gap_pct}% gap"
elif alert.refreshed_entry:
    show refreshed_entry as primary, original entry as "(was $659)"
    show "Updated 9:00 AM" badge
else:
    show original entry (refresh hasn't run yet)
```
