# AI Support/Resistance Prediction

## Status: BACKLOG

## Problem
Current support/resistance detection uses simple pivot points and prior day high/low. Misses institutional levels, volume profile nodes, and multi-timeframe confluence zones.

## Goal
AI identifies high-probability support/resistance zones by analyzing volume clusters, historical price reactions, and multi-timeframe pivots. More accurate levels improve entry/stop/target placement.

## Context
- Current S/R in `analytics/intraday_rules.py` uses prior day high/low, MAs
- Chart levels table exists for manual level input
- Historical daily data available via yfinance
- Volume profile could identify high-volume nodes

## Scope
- Daily pre-market S/R level generation per watchlist symbol
- Multi-timeframe analysis (daily, weekly, monthly pivots)
- Volume-weighted level strength scoring
- Display on Charts page and integrate into alert calculations
- Replace or augment manual chart_levels entries

## Dependencies
- Historical multi-timeframe data
- AI Trade Narrator (shared API integration)
