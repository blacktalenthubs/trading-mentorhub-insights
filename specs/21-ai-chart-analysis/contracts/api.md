# API Contracts: AI Chart Analysis

## POST /api/v1/intel/analyze-chart

Analyze a chart and return a structured trade plan. Streams via SSE.

**Request:**
```json
{
  "symbol": "SPY",
  "timeframe": "1H",
  "ohlcv_bars": [
    {"timestamp": "2026-04-07T10:00:00", "open": 520.0, "high": 521.5, "low": 519.8, "close": 521.2, "volume": 1500000}
  ]
}
```

- `symbol` (required): Ticker to analyze
- `timeframe` (required): "1m", "5m", "15m", "30m", "1H", "4H", "D", "W"
- `ohlcv_bars` (optional): Frontend chart bars. If omitted, server fetches them.

**Response (200, SSE stream):**
```
event: plan
data: {"direction": "LONG", "entry": 521.50, "stop": 519.80, "target_1": 524.00, "target_2": 527.00, "rr_ratio": 1.47, "confidence": "HIGH", "confluence_score": 8, "timeframe_fit": "2-4 hours", "key_levels": ["519.80 (50EMA support)", "524.00 (prior day high)", "527.00 (weekly resistance)"], "historical_ref": "This 50EMA bounce on SPY has 73% win rate over 90 days (22/30)"}

event: reasoning
data: {"text": "SPY hourly shows a clean pullback to the rising 50EMA at $519.80..."}

event: higher_tf
data: {"text": "Daily: uptrend above all MAs, RSI 58. Weekly: bullish, above 10/20 WMA."}

event: done
data: {"analysis_id": 1234, "remaining": 18}
```

**Error responses:**
- 429: Usage limit exceeded (`{"detail": "AI analysis limit reached. Resets at midnight ET.", "remaining": 0}`)
- 400: Invalid timeframe or symbol

---

## GET /api/v1/intel/analysis-history

Get user's saved chart analyses (journal integration).

**Query params:**
- `symbol` (optional): Filter by symbol
- `days` (optional, default 30): Lookback period
- `limit` (optional, default 20): Max results

**Response (200):**
```json
{
  "analyses": [
    {
      "id": 1234,
      "symbol": "SPY",
      "timeframe": "1H",
      "direction": "LONG",
      "entry": 521.50,
      "stop": 519.80,
      "target_1": 524.00,
      "target_2": 527.00,
      "rr_ratio": 1.47,
      "confidence": "HIGH",
      "confluence_score": 8,
      "reasoning": "SPY hourly shows a clean pullback...",
      "actual_outcome": "WIN",
      "outcome_pnl": 2.50,
      "created_at": "2026-04-07T10:15:00Z"
    }
  ]
}
```

---

## PUT /api/v1/intel/analysis/{analysis_id}/outcome

Record the actual outcome of a saved analysis.

**Request:**
```json
{
  "outcome": "WIN",
  "pnl": 2.50
}
```

- `outcome`: "WIN", "LOSS", "SCRATCH"
- `pnl` (optional): Realized P&L per share

**Response (200):**
```json
{
  "id": 1234,
  "actual_outcome": "WIN",
  "outcome_pnl": 2.50
}
```

---

## PUT /api/v1/settings/auto-analysis

Toggle auto-analysis on alerts.

**Request:**
```json
{
  "enabled": true
}
```

**Response (200):**
```json
{
  "auto_analysis_enabled": true
}
```

---

## GET /api/v1/intel/mtf/{symbol} (fixed)

Get multi-timeframe context for a symbol. Fixes existing broken endpoint.

**Response (200):**
```json
{
  "symbol": "SPY",
  "daily": {
    "setup_type": "PULLBACK_TO_MA",
    "score": 75,
    "score_label": "B",
    "entry": 521.50,
    "stop": 517.80,
    "target_1": 528.00,
    "ma_sequence": "bull",
    "edge": "Pullback to rising 20EMA with RSI at 45"
  },
  "weekly": {
    "setup_type": "TREND_CONTINUATION",
    "score": 80,
    "score_label": "A",
    "entry": 520.00,
    "stop": 510.00,
    "target_1": 540.00,
    "edge": "Above all WMAs, bullish weekly candle"
  },
  "alignment": "bullish",
  "confluence_score": 8
}
```
