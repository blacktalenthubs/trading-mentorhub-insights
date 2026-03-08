# AI Trade Coach — Conversational Trading Assistant

## Status: NOT STARTED

## Problem
Traders see signals and scores but still need to synthesize multiple data points
before making a decision. The current system tells you WHAT is happening — the
coach tells you what YOU should do about it, based on YOUR specific situation.

No competing platform offers a conversational AI with access to the user's own
trade history, open positions, win/loss patterns, and real-time signal data.

## Goal
A chat interface where users ask natural-language questions and get personalized,
context-aware trading guidance. The AI has full access to:
- Current signals and scores
- User's open positions and P&L
- Trade history (wins, losses, patterns)
- Watchlist and portfolio exposure
- Market regime (SPY trend, sector rotation)
- Time of day / session phase

## Example Interactions

### Pre-Trade Decision
> **User:** "Should I take this NVDA bounce?"
>
> **Coach:** "The 20MA bounce on NVDA scores 78 (A-grade). SPY is bullish and
> trending. However, you already have 2 open tech positions (AAPL, GOOGL) —
> adding NVDA puts 65% of your capital in tech. The setup is solid but consider
> half-size to manage sector concentration. Entry $142.50, stop $141.80, T1 $143.20."

### Post-Trade Review
> **User:** "Why did I lose on TSLA today?"
>
> **Coach:** "Your TSLA entry was a prior day low reclaim at $248.50, which is a
> valid setup. The loss came from two factors: (1) you entered during the opening
> range when the system flags caution, and (2) SPY was in CHOPPY regime — your
> win rate on bounce signals in CHOPPY markets is 35% vs 62% in TRENDING. Consider
> waiting for regime confirmation before taking bounce signals."

### Portfolio Overview
> **User:** "What's my best setup right now?"
>
> **Coach:** "PLTR has the highest score at 82 (A+) — MA bounce 50 with volume
> confirmation and SPY support. You have no open position in PLTR and your tech
> exposure is manageable. Risk: $0.85/share for 2.8:1 reward. This is your
> cleanest setup today."

### Behavioral Coaching
> **User:** "Am I overtrading?"
>
> **Coach:** "This week you've taken 12 trades vs your 8-trade weekly average.
> Win rate dropped from 58% to 41%. Your last 4 trades were all afternoon entries
> with scores below 65 — you tend to force trades after a morning loss. Consider
> stopping after 2 consecutive losses."

## Architecture

```
┌─────────────────────┐
│  Chat UI (Streamlit) │
│  or Telegram /coach  │
└──────────┬──────────┘
           │
     ┌─────▼──────┐
     │  Coach API  │  ← builds context prompt from DB
     └─────┬──────┘
           │
    ┌──────▼───────┐
    │ Claude API   │  ← system prompt + user context + question
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │   Response    │  ← streamed back to UI / Telegram
    └──────────────┘
```

### Context Assembly (per question)
The coach builds a system prompt with real-time context:

```python
context = {
    # Current market
    "signals": get_todays_signals(user_watchlist),
    "spy_regime": get_spy_regime(),
    "market_phase": get_session_phase(),

    # User portfolio
    "open_positions": get_open_trades(user_id),
    "sector_exposure": calculate_sector_exposure(user_id),
    "daily_pnl": get_daily_pnl(user_id),

    # User history
    "win_rate_7d": get_win_rate(user_id, days=7),
    "win_rate_30d": get_win_rate(user_id, days=30),
    "avg_trades_per_day": get_trade_frequency(user_id),
    "behavioral_flags": detect_patterns(user_id),

    # Signal-specific (if asking about a symbol)
    "signal_detail": get_signal_detail(symbol),
    "similar_past_trades": get_similar_trades(user_id, signal),
}
```

### System Prompt (core personality)
```
You are an experienced day-trading coach. You have access to the trader's
real-time signals, open positions, and trade history. Your job is to:

1. Give actionable, specific advice (not generic trading wisdom)
2. Reference actual numbers — scores, prices, win rates
3. Flag risks the trader might not see (exposure, regime, timing)
4. Be honest about low-probability setups — it's OK to say "skip this one"
5. Keep responses concise — traders are busy during market hours

Rules:
- Never guarantee outcomes. Use probability language ("historically", "your win rate")
- Always mention risk management (stop loss, position size)
- If you don't have enough data, say so rather than guessing
- Prioritize capital preservation over capturing every move
```

## Implementation Plan

### Phase 1: Streamlit Chat (MVP)
- New page: `pages/11_AI_Coach.py`
- Chat interface using `st.chat_message` / `st.chat_input`
- Context assembly from existing DB functions
- Claude API with streaming response
- Conversation history in session state (not persisted initially)

### Phase 2: Telegram Integration
- `/coach` command in Telegram bot
- Same context assembly, shorter responses (Telegram message limits)
- Follow-up support: reply to coach message to continue conversation

### Phase 3: Persistent Memory
- Store conversation history in DB per user
- Coach remembers past advice and outcomes
- "Last week I told you to avoid afternoon trades — you did, and win rate improved"

### Phase 4: Proactive Coaching
- Coach sends unprompted messages when it detects:
  - User about to overtrade (3+ losses in a row)
  - High-conviction setup matching user's best patterns
  - Portfolio risk exceeding thresholds
  - Behavioral pattern emerging (revenge trading, FOMO)

## Files to Create
| File | Purpose |
|------|---------|
| `pages/11_AI_Coach.py` | Streamlit chat page |
| `analytics/trade_coach.py` | Context assembly + prompt engineering |
| `tests/test_trade_coach.py` | Unit tests for context assembly |

## Files to Modify
| File | Change |
|------|--------|
| `db.py` | Add `coach_conversations` table, trade stats queries |
| `alerting/notifier.py` | Add `/coach` Telegram command handler (Phase 2) |

## Dependencies
- `anthropic` SDK (already installed)
- Existing DB functions: `get_open_trades`, `get_watchlist`, `get_todays_signals`
- New DB queries: win rate, trade frequency, sector exposure

## Rate Limiting / Cost Control
- Free tier: 3 questions/day
- Pro tier: 20 questions/day
- Elite tier: unlimited
- Cache context assembly (5-min TTL) — don't rebuild on every question
- Use `claude-haiku-4-5` for fast responses during market hours
- Use `claude-sonnet-4-6` for EOD deep analysis

## Out of Scope (Phase 1)
- No trade execution (coach advises, user decides)
- No options-specific coaching (future feature)
- No multi-user conversation sharing
- No voice interface
