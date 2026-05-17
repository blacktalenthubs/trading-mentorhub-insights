# Dynamic Stop/Target Optimization

## Status: BACKLOG

## Problem
Current stop and target levels are calculated with fixed formulas (ATR-based or support/resistance). These don't adapt to intraday volatility changes or the specific stock's historical behavior at key levels.

## Goal
AI optimizes stop-loss and profit-target placement per trade based on the stock's volatility profile, historical behavior at similar levels, and current market conditions.

## Context
- Current stop/target calculation in `analytics/intraday_rules.py`
- Uses ATR, prior day high/low, support/resistance levels
- Historical price data available via yfinance
- Could analyze how stock typically reacts at MAs, round numbers, etc.

## Scope
- Per-alert dynamic stop/target adjustment
- Based on stock's historical volatility profile
- Factor in time of day (wider stops in first 30 min)
- Show suggested vs default levels in Scanner detail
- Track performance of AI-adjusted vs default levels

## Dependencies
- Historical intraday data access
- AI Trade Narrator (shared API integration)
