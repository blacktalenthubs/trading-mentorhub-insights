# Trade Journal AI Analyst

## Status: BACKLOG

## Problem
Users track real trades but don't systematically analyze patterns in their behavior — e.g., taking trades too early in the session, sizing too large on B-grade setups, or consistently missing exits at T1.

## Goal
AI analyzes the user's trade journal (real trades) and identifies behavioral patterns, strengths, weaknesses, and specific improvement recommendations.

## Context
- Real trades tracked in `real_trades` table with entry/exit prices, shares, P&L
- Alert context (score, grade, type) linked via alert_id
- Time of entry/exit captured
- Could correlate with market regime at time of trade

## Scope
- Weekly/monthly analysis of trade history
- Pattern detection (time-based, setup-based, size-based)
- Behavioral insights ("You tend to hold losers 2x longer than winners")
- Actionable recommendations
- Displayed in Real Trades page or dedicated report

## Dependencies
- Sufficient trade history
- AI Trade Narrator (shared API integration)
