# Data Model: User Alert Preferences

## New Table: `user_alert_category_prefs`

Per-user toggle for each alert category.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | Row ID |
| user_id | INTEGER | NOT NULL, FK → users(id) | User who set preference |
| category_id | TEXT | NOT NULL | Category key (e.g., "entry_signals") |
| enabled | INTEGER | DEFAULT 1 | 1 = enabled, 0 = disabled |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When created |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When last changed |

**Unique constraint**: `UNIQUE(user_id, category_id)`

**Default behavior**: If no row exists for a (user_id, category_id) pair, the category is treated as **enabled** (opt-out model).

## Modified Table: `user_notification_prefs`

Add one column:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| min_alert_score | INTEGER | 0 | Minimum score threshold (0-100). Alerts below this are not pushed to Telegram. Exit alerts bypass this filter. |

## Code-Level Entity: `ALERT_CATEGORIES`

Defined in `alert_config.py`, not in the database.

```python
ALERT_CATEGORIES: dict[str, dict] = {
    "entry_signals": {
        "name": "Entry Signals",
        "description": "BUY alerts at support levels",
        "alert_types": {AlertType.MA_BOUNCE_20, AlertType.MA_BOUNCE_50, ...},
    },
    "breakout_signals": { ... },
    "short_signals": { ... },
    "exit_alerts": { ... },
    "resistance_warnings": { ... },
    "support_warnings": { ... },
    "swing_trade": { ... },
    "informational": { ... },
}
```

## Reverse Lookup: `ALERT_TYPE_TO_CATEGORY`

Built once at module load from `ALERT_CATEGORIES`:

```python
ALERT_TYPE_TO_CATEGORY: dict[str, str] = {}
for cat_id, cat in ALERT_CATEGORIES.items():
    for at in cat["alert_types"]:
        ALERT_TYPE_TO_CATEGORY[at.value] = cat_id
```

## Exit Alert Types (Score Bypass)

```python
EXIT_ALERT_TYPES = {
    AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT,
    AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT,
    AlertType.TRAILING_STOP_HIT,
}
```
