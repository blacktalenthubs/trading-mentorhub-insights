# API Contracts: Beginner Guidance

## PUT /api/v1/settings/beginner-mode

Toggle beginner mode on/off.

**Request:**
```json
{ "enabled": true }
```

**Response (200):**
```json
{ "beginner_mode": true }
```

---

## GET /api/v1/settings/glossary

Returns all glossary terms for tooltip display.

**Response (200):**
```json
{
  "terms": [
    {
      "term": "EMA",
      "definition": "Exponential Moving Average — a line showing average price, weighted toward recent data",
      "context": "When price bounces off an EMA, buyers are defending that level"
    },
    {
      "term": "VWAP",
      "definition": "Volume Weighted Average Price — the average price weighted by trading volume for the day",
      "context": "Traders use VWAP as a fair value line. Above = bullish, below = bearish"
    }
  ]
}
```

---

## POST /api/v1/intel/what-should-i-do

Returns a beginner-friendly actionable recommendation.

**Request:** (empty body, uses auth token)

**Response (200, SSE stream):**
```
data: {"type": "text", "content": "Right now, SPY at $655 is the best setup..."}
data: {"type": "text", "content": " It's testing a support level..."}
data: {"type": "done", "usage": {"queries_remaining": 18}}
```

---

## Auth Response (modified)

All auth endpoints (`/login`, `/register`, `/me`) now include:

```json
{
  "access_token": "...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "tier": "pro",
    "trial_active": true,
    "beginner_mode": true
  }
}
```
