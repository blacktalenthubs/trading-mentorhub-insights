# Feature Specification: Telegram AI Commands

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (via /speckit.specify)
**Priority**: High — fastest path from question to trade plan

## Problem

Users want AI chart analysis without opening the web app. They're already in Telegram (where alerts arrive). Currently they must:
1. Open browser → go to tradingwithai.ai → log in
2. Navigate to Trading page → select symbol
3. Open AI Coach tab → type question → wait for response

That's 30+ seconds for a simple question: "Should I buy SPY here?"

## Solution

Type `/spy` in Telegram → get AI analysis in 3 seconds. Same quality as the AI Coach but delivered where the user already is.

## User Experience

```
User types:  /spy
Bot replies:

📊 SPY $679.34

CHART READ: SPY pulled back to 50MA support at $673 after
PDH rejection. Session low holding.

ACTION:
Direction: LONG
Entry: $673.50 — 50MA support
Stop: $671.80 (session low)
T1: $677.08 (PDH)
T2: $681.00

Conviction: MEDIUM
```

```
User types:  /eth
Bot replies:

📊 ETH-USD $2249.84

CHART READ: Consolidation between VWAP ($2245) and PDH ($2253).
No clear direction. Volume dry.

ACTION:
Direction: WAIT
Watch: $2239 (session low) for long, $2253 (PDH) for breakout

Wait for break below $2239 or reclaim above $2253 with volume.
```

## Supported Commands

| Command | What It Does |
|---------|-------------|
| `/spy` | AI analysis of SPY |
| `/eth` | AI analysis of ETH-USD |
| `/btc` | AI analysis of BTC-USD |
| `/aapl` | AI analysis of AAPL |
| `/tsla` | AI analysis of TSLA |
| `/[any symbol]` | AI analysis of that symbol |
| `/scan` | Run AI scan on entire watchlist now |
| `/levels [symbol]` | Show key levels only (PDH/PDL/VWAP/MAs) — no AI call |

## Functional Requirements

### FR-1: Symbol Command Handler
- Register handler for any text message starting with `/` followed by a ticker symbol
- Map common shortcuts: `eth` → `ETH-USD`, `btc` → `BTC-USD`
- If symbol not recognized, reply: "Symbol not found. Try /spy, /eth, /btc, /aapl"
- Acceptance: User types `/spy` → gets AI analysis within 5 seconds

### FR-2: AI Analysis via Telegram
- Fetch same data as AI Coach: 5m bars, 1H bars, prior_day, key levels
- Use same simplified prompt (from ai_day_scanner)
- Call Claude Haiku (fast, <3s response)
- Format response for Telegram (HTML, clean layout)
- Acceptance: Response quality matches AI Coach output

### FR-3: Response Format
```html
<b>📊 {SYMBOL} ${price}</b>

{chart_read}

<b>ACTION:</b>
Direction: {LONG / RESISTANCE / WAIT}
Entry: ${entry} — {level name}
Stop: ${stop} | T1: ${t1} | T2: ${t2}
Conviction: {HIGH / MEDIUM / LOW}
```

### FR-4: Rate Limiting
- Free tier: 5 commands/day
- Pro tier: 50 commands/day
- Premium: unlimited
- Reply with remaining count: "4 queries remaining today"
- Acceptance: Rate limits enforced per user

### FR-5: /scan Command
- Triggers immediate AI scan of user's entire watchlist
- Returns summary: "Scanning 5 symbols... ETH: LONG at VWAP, BTC: WAIT, SPY: closed"
- Acceptance: User can force a scan without waiting for the 5-min cycle

### FR-6: /levels Command
- No AI call — just fetches and displays key levels
- Fast (no Claude API needed, <1s response)
```
📊 SPY Key Levels
PDH: $681.16  PDL: $673.77
VWAP: $678.50
50MA: $673.27  100MA: $676.39  200MA: $660.58
Session Hi: $681.93  Session Lo: $675.12
RSI: 55.2
```
- Acceptance: Instant response with all key levels

## Technical Implementation

### Existing Infrastructure
- Telegram bot already running (webhook mode on Railway)
- Commands registered: `/start`, `/exit`, `/trades`
- Callback handlers for Took/Skip/Exit buttons
- Bot token, webhook URL already configured

### New Code
```python
# In telegram_bot.py or new file

async def symbol_command(update, context):
    """Handle /spy, /eth, /btc, etc."""
    symbol = update.message.text.strip("/").upper()
    
    # Map shortcuts
    SYMBOL_MAP = {
        "ETH": "ETH-USD", "BTC": "BTC-USD",
        "SOL": "SOL-USD",
    }
    symbol = SYMBOL_MAP.get(symbol, symbol)
    
    # Rate limit check
    user_id = get_user_from_telegram(update.effective_chat.id)
    if not check_rate_limit(user_id):
        await update.message.reply_text("Daily limit reached. Upgrade for more.")
        return
    
    # Fetch data
    bars_5m = fetch_intraday(symbol)
    prior_day = fetch_prior_day(symbol)
    
    # Build prompt (same as AI day scanner)
    prompt = build_day_trade_prompt(symbol, bars_5m, bars_1h, prior_day)
    
    # Call Claude
    response = call_claude(prompt)
    
    # Format for Telegram
    msg = format_telegram_analysis(symbol, response)
    await update.message.reply_html(msg)
```

### Registration
```python
# In telegram_bot.py build_app()
app.add_handler(MessageHandler(
    filters.TEXT & filters.Regex(r"^/[a-zA-Z]+$"),
    symbol_command
))
# Or register specific symbols:
for sym in ["spy", "eth", "btc", "aapl", "tsla", "nvda", "meta", "pltr", "qqq"]:
    app.add_handler(CommandHandler(sym, symbol_command))
app.add_handler(CommandHandler("scan", scan_command))
app.add_handler(CommandHandler("levels", levels_command))
```

## Cost Model

| Command | Model | Tokens | Cost |
|---------|-------|--------|------|
| `/spy` | Haiku | ~2000 | $0.001 |
| `/scan` (5 symbols) | Haiku | ~10000 | $0.005 |
| `/levels` | None | 0 | Free |

At 50 commands/day (Pro): ~$0.05/day. Negligible.

## Edge Cases

- **Market closed**: Still works — shows latest available data with note "Market closed"
- **Invalid symbol**: Reply "Symbol not found"
- **API timeout**: Reply "Analysis timed out, try again"
- **User not registered**: Reply "Link your account at tradingwithai.ai/settings"
- **Multiple users in group chat**: Commands work in DM only (bot ignores group commands for privacy)

## Success Criteria

- [ ] `/spy` returns AI analysis within 5 seconds
- [ ] Response format matches Coach output (CHART READ + ACTION)
- [ ] Rate limits enforced per tier
- [ ] `/levels` returns key levels without AI call (<1s)
- [ ] `/scan` triggers full watchlist scan
- [ ] Works for all symbols on user's watchlist
- [ ] Crypto shortcuts work (eth → ETH-USD)

## Scope

### In Scope
- Symbol commands (/spy, /eth, /btc, /aapl, etc.)
- AI analysis via Claude Haiku
- /scan command (trigger watchlist scan)
- /levels command (key levels without AI)
- Rate limiting per tier
- Telegram HTML formatting

### Out of Scope
- Image/chart generation in Telegram
- Voice commands
- Multi-message conversations (use AI Coach on web for that)
- Custom alerts setup via Telegram
- Portfolio management via Telegram
