# AI Scanner Simplification — Let AI Be Intelligent

**Created**: 2026-04-11
**Problem**: We rebuilt rule-engine complexity inside the AI scanner. Code-calculated positions, thresholds (0.3%, 0.8%), approaching vs at vs mid-range — all defeating the purpose of using AI.

## Current State (Over-Engineered)

```
Code calculates position → tells AI what to think → AI follows instruction
```

- 12+ key levels checked with distance math
- Support vs resistance classification in code
- 0.3% AT threshold, 0.8% APPROACHING threshold
- Code tells AI "you MUST say LONG" or "you MUST say WAIT"
- AI is a puppet, not intelligent

## Desired State (Simple)

```
Give AI data → AI reads chart → AI decides → Record result
```

- Give: OHLCV bars (5m + 1H), key levels (PDL/PDH/MAs/VWAP/session high/low), RSI
- Ask: "Is there a day trade entry? If yes: entry, stop, target. If no: WAIT."
- AI uses its intelligence to read price action, volume, bar structure
- No code telling AI what to think

## What the Scanner Should Do

```python
def scan_symbol(symbol, api_key):
    # 1. Fetch data
    bars_5m = fetch_5m_bars(symbol)
    bars_1h = fetch_1h_bars(symbol)  
    prior_day = fetch_prior_day(symbol)
    
    # 2. Build context (data only, no analysis)
    prompt = f"""
    Here is {symbol} data. Is there a day trade entry?
    
    [5-MIN BARS] {bars_5m}
    [1-HOUR BARS] {bars_1h}
    [KEY LEVELS]
    PDH: ${pdh}  PDL: ${pdl}  VWAP: ${vwap}
    Session High: ${sh}  Session Low: ${sl}
    50MA: ${ma50}  100MA: ${ma100}  200MA: ${ma200}
    RSI: {rsi}
    
    Reply: LONG/RESISTANCE/WAIT with entry/stop/target.
    """
    
    # 3. Call AI — it decides
    response = call_claude(prompt)
    
    # 4. Parse and record
    result = parse(response)
    record_to_db(result)
    send_telegram(result)
```

## What the Prompt Should Say

```
You are a day trade analyst. Look at the data and tell me:
Is there a trade right now?

If price is at a support level and holding → LONG with entry/stop/target
If price is at a resistance level and rejecting → RESISTANCE  
If price is between levels or no clear setup → WAIT

Output:
SETUP: [what you see — e.g. "PDL bounce", "VWAP hold", "session low double bottom"]
Direction: LONG / RESISTANCE / WAIT
Entry: $price
Stop: $price (below the support level that defines the trade)
T1: $price (next resistance)
T2: $price (second resistance)
Conviction: HIGH / MEDIUM / LOW
Reason: 1 sentence

Rules:
- Entry must be a key level, not current price
- Stop must be structural (where thesis breaks)
- If no clear setup, say WAIT
- Maximum 60 words
```

## What We Remove from Code

| Remove | Why |
|--------|-----|
| `_add_level()` position detection | AI reads the chart |
| `_supports` / `_resistances` lists | AI knows what's support vs resistance |
| 0.3% / 0.8% thresholds | AI doesn't need arbitrary cutoffs |
| "POSITION — CALCULATED BY SYSTEM" | No — AI calculates its own position |
| "you MUST set Direction = LONG" | No — AI decides |
| `_at_support` / `_at_resistance` | AI determines this from bars |
| `_approaching_support` / `_approaching_resistance` | AI sees proximity from bars |

## What We Keep

| Keep | Why |
|------|-----|
| Key levels in context (PDH, PDL, MAs, VWAP) | AI needs the data |
| Session high/low | AI needs the data |
| OHLCV bars | AI reads these |
| RSI | AI uses for context |
| Dedup (same setup at same level per day) | Prevents spam |
| Telegram delivery | Notification |
| DB recording | Analytics |
| Market hours filter | Don't scan closed markets |

## Implementation

1. Simplify `build_day_trade_prompt()` — data only, no position analysis
2. Remove all `_add_level`, `_supports`, `_resistances`, threshold code
3. Keep the prompt concise — tell AI what setups to look for, give data, let it decide
4. Keep dedup, Telegram, DB recording unchanged
5. Write tests for the simplified flow
