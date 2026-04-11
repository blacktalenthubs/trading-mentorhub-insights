# AI Scan Evaluation Framework — What the AI Should Detect

**Created**: 2026-04-11
**Context**: The AI scan runs every 15 min per symbol. When it evaluates a chart, it must identify WHERE price is relative to key levels and WHAT setup is forming.

## Core Question the AI Answers

> "Where is price right now, and is there a trade?"

## Level Detection — What the AI Must Identify

### Support Levels (BUY setups)

| Condition | What It Means | Action |
|-----------|--------------|--------|
| **AT session low** | Price testing today's low | BUY if holds (double bottom, bounce) |
| **AT prior day low (PDL)** | Price at yesterday's low | BUY — key institutional level |
| **AT VWAP** (from below) | Price reclaiming VWAP | BUY — momentum shift bullish |
| **AT VWAP** (pullback from above) | Price pulling back to VWAP and holding | BUY — continuation |
| **AT key MA** (20/50/100/200) | Price touching moving average support | BUY — MA bounce |
| **AT weekly low** | Price at prior week's low | BUY — higher timeframe support |
| **AT monthly low** | Price at prior month's low | BUY — major support |
| **AT fib level** (50%/61.8%) | Price at fibonacci retracement | BUY — mean reversion |
| **APPROACHING support** (within 0.5%) | Price moving toward support | WATCH — prepare for entry |

### Resistance Levels (RESISTANCE setups)

| Condition | What It Means | Action |
|-----------|--------------|--------|
| **AT session high** | Price testing today's high | RESISTANCE if rejected (double top) |
| **AT prior day high (PDH)** | Price at yesterday's high | RESISTANCE — key level |
| **BELOW VWAP** (lost it) | Price dropped below VWAP | RESISTANCE — bearish shift |
| **AT key MA** (from below) | Price rallying into MA resistance | RESISTANCE — MA rejection |
| **AT weekly high** | Price at prior week's high | RESISTANCE — higher timeframe |
| **APPROACHING resistance** (within 0.5%) | Price moving toward resistance | WATCH — tighten stops |

### Neutral / No Trade

| Condition | What It Means | Action |
|-----------|--------------|--------|
| **MID-RANGE** | Price between support and resistance | WAIT — no edge |
| **EXTENDED** (>1% from nearest level) | Price far from any key level | WAIT — don't chase |
| **CHOPPY** (tight range, no direction) | Low volume consolidation | WAIT — let it resolve |

## AI Output Format

```
CHART READ: [1 sentence — where price is relative to nearest key level]

POSITION: [AT SUPPORT / AT RESISTANCE / APPROACHING SUPPORT / APPROACHING RESISTANCE / MID-RANGE]

NEAREST LEVELS:
Support: $price (level name) — distance: X%
Resistance: $price (level name) — distance: X%

ACTION:
Direction: LONG / SHORT / WAIT
Entry: $price — level name
Stop: $price
T1: $price
T2: $price
Conviction: HIGH / MEDIUM / LOW
```

## Data the AI Receives (per scan)

```
[INTRADAY LEVELS]
Session High: $2250.44
Session Low: $2235.71
VWAP: $2241.08
Current Price: $2239.82

[KEY LEVELS — ETH-USD]
PDH(yesterday high): $2246.79
PDL(yesterday low): $2235.71
Prior Close: $2237.12
20MA: $2238.50
50MA: $2074.83
100MA: $2150.22
200MA: $2927.45
RSI14: 59.6
WeekHi: $2267.56
WeekLo: $2137.59

[5-MIN BARS — last 20 bars]
O=2240.50 H=2241.20 L=2239.10 C=2239.82 V=15000
...

[1-HOUR BARS — last 10 bars]
O=2235.00 H=2250.44 L=2230.15 C=2240.20 V=120000
...
```

## Decision Logic

```
1. Calculate distance from current price to each key level
2. Find nearest support (below price) and nearest resistance (above price)
3. If price is within 0.3% of a support level → AT SUPPORT → potential BUY
4. If price is within 0.3% of a resistance level → AT RESISTANCE → potential SHORT
5. If price is 0.3-0.8% from a level → APPROACHING → WATCH
6. If price is >0.8% from all levels → MID-RANGE → WAIT
7. Check confirmation: volume, RSI, bar structure
8. Output ACTION with specific entry at the key level
```

## Examples

### Example 1: AT PDL Support
```
CHART READ: ETH testing PDL support at $2235.71 after pullback from session high.

POSITION: AT SUPPORT

NEAREST LEVELS:
Support: $2235.71 (PDL) — distance: 0.1%
Resistance: $2246.79 (PDH) — distance: 0.4%

ACTION:
Direction: LONG
Entry: $2235.71 — Prior Day Low
Stop: $2233.50
T1: $2241.08 (VWAP)
T2: $2246.79 (PDH)
Conviction: HIGH
```

### Example 2: AT Session High Resistance
```
CHART READ: ETH rejected at session high $2250 twice, forming double top.

POSITION: AT RESISTANCE

NEAREST LEVELS:
Support: $2241.08 (VWAP) — distance: 0.3%
Resistance: $2250.44 (Session High) — distance: 0.05%

ACTION:
Direction: SHORT
Entry: $2250.44 — Session High (double top)
Stop: $2253.00
T1: $2241.08 (VWAP)
T2: $2235.71 (PDL)
Conviction: MEDIUM
```

### Example 3: MID-RANGE No Trade
```
CHART READ: ETH at $2242, between VWAP $2241 and PDH $2247. No clear setup.

POSITION: MID-RANGE

NEAREST LEVELS:
Support: $2241.08 (VWAP) — distance: 0.04%
Resistance: $2246.79 (PDH) — distance: 0.2%

ACTION:
Direction: WAIT
Watch: $2235.71 (PDL) for long entry or $2250 (session high) for short
```

## What Makes a Good AI Scan Alert

1. **Price is AT a key level** (within 0.3%) — not approaching, not mid-range
2. **There's confirmation** — volume, RSI extreme, bar structure (bounce candle, rejection wick)
3. **Clear R:R** — stop below support, target at next resistance (minimum 1:1.5)
4. **Not chasing** — entry is at the level, not after the move already happened

## What the AI Should NOT Do

1. Use current price as entry when it's not at a key level
2. Fire LONG when price is mid-range between levels
3. Fire when price already bounced 1%+ from the level (missed it)
4. Ignore VWAP — it's the most important intraday level
5. Confuse today's session low with PDL (yesterday's low)
6. Fire the same setup twice in the same session
