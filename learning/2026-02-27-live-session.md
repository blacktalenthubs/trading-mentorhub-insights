# Live Session Learnings — 2026-02-27

## Market Context
- SPY below 5/20/50 day MAs — choppy, uncertain environment
- SPY dropped from ~$692 to ~$681, bounced back to $690+
- META similar: dropped to ~$650, double-bottom, recovered to $657+

## What Worked
- MA bounce alerts fired and were accurate
- Session low double-bottom rule (just shipped) correctly identifies the META $650 pattern in backtest
- Trade plans (Scanner) correctly identified SPY $681.65 and META $650 as entry levels
- Session low reference line on backtest chart makes the pattern visually obvious

## Gaps Identified

### 1. Scanner-to-Alert Disconnect
The Scanner identified SPY entry at $681.65 (first test of support, 4:1 R:R). Price hit it perfectly. But no intraday alert fired at that level — only PDL reclaim at $684.35, a worse entry.

**Root cause:** Two independent systems. Scanner generates plans, alerts fire rules. Neither reads the other.
**Ticket:** `tickets/planned-level-touch-alert.md`

### 2. Market Regime Blindness
In choppy/non-trending markets (SPY below all MAs), BUY signals are less reliable due to lack of follow-through. The system only knows "bearish" but doesn't distinguish "trending down" from "choppy."

**Root cause:** SPY filter is binary (above/below 20MA). No MA alignment or volatility analysis.
**Ticket:** `tickets/market-regime-detection.md`

## Key Takeaway
The system generates good levels but the real-time execution layer (alerts) doesn't leverage the pre-market analysis layer (Scanner). Bridging these two systems is the highest-impact improvement.
