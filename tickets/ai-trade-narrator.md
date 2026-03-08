# AI Trade Narrator / Setup Explainer

## Status: ACTIVE

## Problem
Alerts fire with mechanical labels (e.g. "MA Bounce 20", "Buy Zone Approach") and raw numbers. During market hours, users need to make fast go/no-go decisions but must mentally synthesize price action, MAs, volume, SPY regime, and score into a thesis. This slows decision-making and increases errors.

## Goal
LLM reviews each alert's full context and writes a 2-3 sentence plain-English trade thesis explaining WHY this setup is worth taking (or not). Displayed in Scanner detail cards and included in Telegram notifications.

## Example Output
> "LRCX bouncing off 20MA ($216.47) with 1.8x avg volume — buyers stepping in. SPY bullish, above VWAP. Entry near confluence of MA20 + prior day low. Risk $2.08/share for 3.7:1 reward. A-grade setup."

## Context Available Per Alert
- Symbol, price, direction, alert_type, score/grade
- Entry, stop, T1, T2, risk/reward ratio
- Volume ratio vs 20-day avg
- MA positions (above/below 20/50/100/200)
- VWAP position
- SPY regime (bullish/bearish/neutral, trending/choppy)
- Prior day high/low, pattern (inside/outside/normal)
- Support status (AT SUPPORT, PULLBACK WATCH, BROKEN)
- Confidence level
- Time of day / session phase

## Scope
- Claude API call per alert signal
- Cache narratives per symbol+alert_type+session (don't re-call for same alert)
- Show in Scanner detail expander
- Include in Telegram notification body (appended after existing format)
- Graceful fallback if API fails (show alert without narrative)

## Out of Scope
- No training/fine-tuning — pure prompt engineering
- No historical analysis (that's EOD Review ticket)
- No watchlist recommendations
