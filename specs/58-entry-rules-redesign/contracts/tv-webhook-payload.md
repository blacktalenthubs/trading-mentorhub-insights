# Contract — Pine → `/tv-webhook` Payload

**Direction**: TradingView Pine `alert()` → FastAPI `POST /api/v1/tv-webhook`
**Format**: JSON body
**Stability**: Backward-compatible — new fields are additive. Webhook treats unknown fields as no-ops (existing behavior).

## Existing fields (unchanged — included for context)

| Field | Type | Example | Notes |
|---|---|---|---|
| `rule_name` | string | `"ma_bounce_long_v3"` | Maps to `alert_type` prefix in DB |
| `ma_tag` | string | `"ema21"` | Suffix for per-MA dedup (`tv_ma_bounce_long_v3_ema21`) |
| `symbol` | string | `"AAOI"` | Stock ticker |
| `direction` | string | `"BUY"` \| `"SHORT"` \| `"NOTICE"` \| `"EXIT"` | Routing direction |
| `price` | number | `181.49` | Current bar price |
| `entry` | number | `171.47` | Entry trigger price |
| `stop` | number | `166.66` | Structural stop |
| `target_1` | number | `177.96` | First target |
| `target_2` | number | `200.11` | Second target |
| `message` | string | `"EMA 21 bounce — ..."` | Free-text Pine pre-formats; webhook may augment |
| `near_pdh` / `near_pdl` | bool | `true` | Used for confluence-twin suppression |

## New fields (Spec 58)

### `uptrend_pass` *(bool, required for entry alerts)*

`true` if the uptrend gate passed (price above every key MA at fire time), `false` otherwise.

**Webhook behavior**: If `uptrend_pass=false` AND `direction="BUY"` AND `rule_name` is in the entry-rule set, the webhook **rejects** the alert (records with `suppressed_reason='uptrend_gate_failed'` for EOD review, no Telegram). This is the FR-001 enforcement point — also guards against Pine logic regressions.

### `overhead_mas` *(array of strings)*

Names of MAs currently above price. Empty array `[]` means clean uptrend.

```json
"overhead_mas": []                  // clean uptrend
"overhead_mas": ["EMA 100", "EMA 200", "SMA 200"]  // MSFT-style; FR-001 blocks
```

**Webhook behavior**: Logged for audit. Reflected in the EOD scorecard so the user can see *why* a borderline alert was blocked.

### `nearby_levels` *(array of objects, optional but recommended)*

All key levels the Pine script knows about at fire time. The webhook uses this for confluence detection.

```json
"nearby_levels": [
  { "kind": "ema8",      "value": 175.20, "label": "EMA 8" },
  { "kind": "ema21",     "value": 171.47, "label": "EMA 21" },
  { "kind": "ema50",     "value": 145.66, "label": "EMA 50" },
  { "kind": "sma50",     "value": 141.67, "label": "SMA 50" },
  { "kind": "ema100",    "value": 113.24, "label": "EMA 100" },
  { "kind": "sma100",    "value":  97.98, "label": "SMA 100" },
  { "kind": "ema200",    "value":  80.75, "label": "EMA 200" },
  { "kind": "sma200",    "value":  62.96, "label": "SMA 200" },
  { "kind": "pdh",       "value": 182.18, "label": "PDH" },
  { "kind": "pdl",       "value": 163.66, "label": "PDL" },
  { "kind": "pwh",       "value": 194.30, "label": "PWH" },
  { "kind": "pwl",       "value": 162.10, "label": "PWL" },
  { "kind": "pmh",       "value": 233.00, "label": "PMH" },
  { "kind": "pml",       "value": 152.00, "label": "PML" },
  { "kind": "mtd_avwap", "value": 180.28, "label": "MTD AVWAP" }
]
```

**Constraints**:
- `value > 0`
- `kind` is one of the enumerated kinds above (or any future kind — webhook treats unknowns as plain numeric levels)
- `label` is the human-readable string used in the confluence annotation

**Webhook behavior**: Pseudocode for the confluence check:

```python
CONFLUENCE_BAND_PCT = 1.0  # %

def find_confluences(entry_level: float, nearby_levels: list[dict]) -> list[dict]:
    """Return levels within band of entry_level, excluding the entry's own level."""
    out = []
    band = entry_level * (CONFLUENCE_BAND_PCT / 100.0)
    for lvl in nearby_levels:
        if abs(lvl["value"] - entry_level) <= band and lvl["value"] != entry_level:
            out.append(lvl)
    return out

def format_confluence_annotation(confluences: list[dict]) -> str:
    if not confluences:
        return ""
    parts = [f"{c['label']} (${c['value']:.2f})" for c in confluences]
    return "Confluence: " + ", ".join(parts)
```

The annotation is appended to `sig.message` BEFORE the standard persist + notify pipeline runs. The single resulting `Alert` row carries the full confluent context in its message text — no second alert, ever (FR-013).

### `mtd_avwap` *(number, optional)*

Convenience field — the MTD AVWAP value. Already present in `nearby_levels` under `kind: "mtd_avwap"`. Webhook prefers the array entry; this is for backward-compat sanity (a future client may want this denormalized).

## Example: complete payload for AAOI Buy-1 (the 2026-05-22 trade)

```json
{
  "rule_name": "ma_bounce_long_v3",
  "ma_tag": "ema21",
  "symbol": "AAOI",
  "direction": "BUY",
  "price": 181.49,
  "entry": 171.47,
  "stop": 166.66,
  "target_1": 177.96,
  "target_2": 200.11,
  "message": "EMA 21 bounce — the day's low tagged it and the candle closed back above",
  "near_pdh": false,
  "near_pdl": false,

  "uptrend_pass": true,
  "overhead_mas": [],

  "nearby_levels": [
    { "kind": "ema21",     "value": 171.47, "label": "EMA 21" },
    { "kind": "ema50",     "value": 145.66, "label": "EMA 50" },
    { "kind": "sma50",     "value": 141.67, "label": "SMA 50" },
    { "kind": "ema100",    "value": 113.24, "label": "EMA 100" },
    { "kind": "ema200",    "value":  80.75, "label": "EMA 200" },
    { "kind": "pdh",       "value": 182.18, "label": "PDH" },
    { "kind": "pdl",       "value": 163.66, "label": "PDL" },
    { "kind": "mtd_avwap", "value": 180.28, "label": "MTD AVWAP" }
  ],

  "mtd_avwap": 180.28
}
```

**Webhook output** (the final Telegram message):

```
SWING LONG (MA bounce) — AAOI $181.49
Entry $171.47 · Stop $166.66 · T1 $177.96 · T2 $200.11
Setup: EMA 21 bounce — the day's low tagged it and the candle closed back above
Why: clean uptrend, zero overhead MAs
```

*(No confluence line on this specific bar — the MTD AVWAP at $180.28 is 5.1% away from the entry level $171.47, outside the 1% band. AAOI is in confluence with the **weekly** 21 EMA, but that's an HTF level Pine wouldn't include unless we add a `weekly_ema21` kind. Optional follow-up — see R6 in research.md.)*

## Example: AVGO Buy-1 with PDL confluence

```json
{
  "rule_name": "ma_bounce_long_v3",
  "ma_tag": "ema21",
  "symbol": "AVGO",
  "direction": "BUY",
  "price": 414.14,
  "entry": 413.02,
  "stop": 410.21,
  "target_1": 419.00,
  "target_2": 429.26,

  "uptrend_pass": true,
  "overhead_mas": [],

  "nearby_levels": [
    { "kind": "ema21",     "value": 413.02, "label": "EMA 21" },
    { "kind": "pdl",       "value": 410.50, "label": "PDL" },
    { "kind": "mtd_avwap", "value": 420.92, "label": "MTD AVWAP" }
  ]
}
```

**Webhook output**:

```
LONG (MA bounce) — AVGO $414.14
Entry $413.02 · Stop $410.21 · T1 $419.00 · T2 $429.26
Setup: EMA 21 bounce
Confluence: PDL ($410.50)
```

PDL at $410.50 is 0.61% from entry $413.02 → within 1% band → flagged. MTD AVWAP at $420.92 is 1.91% away → outside band → NOT flagged (correctly — it's the next *target*, not confluent support).

## Backward compatibility

| Scenario | Result |
|---|---|
| Pine sends old payload (no new fields) | Webhook treats as legacy — no confluence annotation. Alert still fires/blocks per existing rules. |
| Pine sends `nearby_levels` but no `uptrend_pass` | Webhook skips the gate check (assumes legacy script). Confluence annotation still works. |
| Pine sends `uptrend_pass=false` | Webhook blocks the alert with `suppressed_reason='uptrend_gate_failed'`. Single source of truth — the gate is also enforced in Pine itself; this is belt-and-suspenders. |
