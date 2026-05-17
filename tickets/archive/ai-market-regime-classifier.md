# AI Market Regime Classifier

## Status: BACKLOG

## Problem
Current SPY regime detection is binary (bullish/bearish + trending/choppy) based on simple MA/VWAP rules. Doesn't capture nuanced market conditions like sector rotation, volatility expansion, or distribution days.

## Goal
AI classifies the current market environment with more granularity, helping users understand when to be aggressive vs defensive. Feeds into alert scoring and narrative generation.

## Context
- Current regime detection in `analytics/intraday_rules.py` (`_spy_regime`)
- Uses SPY price vs MAs and VWAP
- Could incorporate VIX, breadth, sector ETFs, put/call ratio
- Regime classification affects all downstream alert quality

## Scope
- Enhanced regime classification (6-8 states vs current 4)
- Morning assessment and intraday updates
- Displayed on Home page dashboard
- Integrated into alert scoring multipliers

## Dependencies
- Additional data sources (VIX, breadth indicators)
- AI Trade Narrator (shared API integration)
