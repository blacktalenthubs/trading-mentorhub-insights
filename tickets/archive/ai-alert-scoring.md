# AI-Powered Alert Scoring (Confidence Calibration)

## Status: BACKLOG

## Problem
Current scoring is rule-based (fixed weights per factor). Some setups score high but fail repeatedly, while others score low but win consistently. The scoring doesn't learn from outcomes.

## Goal
AI analyzes historical alert outcomes to calibrate confidence scores. Over time, the system learns which factor combinations actually predict winners vs losers in different market regimes.

## Context
- Current scoring in `analytics/intraday_rules.py` uses fixed point system
- Alert outcomes (T1/T2 hit, stopped out) tracked in DB
- SPY regime, volume, MA positions all captured per alert
- Needs sufficient historical data to be meaningful

## Scope
- Weekly batch analysis of alert outcomes vs predicted scores
- Generates calibration report (which factors over/under-weighted)
- Optionally adjusts score weights based on findings
- Dashboard showing predicted vs actual win rates by grade

## Dependencies
- Sufficient alert history (suggest 2-4 weeks minimum)
- AI Trade Narrator (shared API integration)
