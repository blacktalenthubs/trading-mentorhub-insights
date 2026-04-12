# Data Model: Beginner Guidance

## Entities

### User (modified)
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| beginner_mode | Boolean | True | New column — ON for new users |

### GlossaryTerm (static, not DB)
| Field | Type | Example |
|-------|------|---------|
| term | string | "EMA" |
| definition | string | "Exponential Moving Average — a line on the chart showing the average price, weighted toward recent prices" |
| context | string | "When price bounces off an EMA, buyers are defending that average price level" |

### AlertDescription (static, not DB)
| Field | Type | Example |
|-------|------|---------|
| alert_type | string | "ma_bounce_20" |
| technical_name | string | "MA Bounce 20" |
| beginner_desc | string | "Price dropped to a key average price line and bounced back up — a common buy signal" |
| category | string | "bounce" |

### ScoreLabel (static, not DB)
| Score Range | Label | Color |
|-------------|-------|-------|
| 80-100 | Strong setup | Green |
| 60-79 | Decent setup | Yellow |
| 40-59 | Risky | Orange |
| 0-39 | Low probability | Gray |
