# End-of-Day AI Review

## Status: BACKLOG

## Problem
After market close, users manually review each alert to understand what worked and what didn't. This is time-consuming and prone to hindsight bias.

## Goal
AI generates a daily trading session review: what setups fired, which hit targets vs stopped out, pattern recognition across the day's action, and actionable lessons for tomorrow.

## Context
- Session summary data already exists (`get_session_summary`)
- Alert history with outcomes (T1 hit, T2 hit, stopped out) tracked
- SPY regime data available
- Could correlate win/loss with time of day, volume, score grade

## Scope
- Triggered manually or automatically after 4:15 PM ET
- Generates markdown report saved to reports/
- Optionally sent via Telegram/email
- Uses Claude API with full session context

## Dependencies
- AI Trade Narrator (for shared prompt patterns and API integration)
