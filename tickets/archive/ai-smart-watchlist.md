# Smart Watchlist Recommendations

## Status: BACKLOG

## Problem
Users manually curate their watchlist. They may miss stocks setting up for high-probability trades, or hold onto symbols that are no longer actionable.

## Goal
AI scans a broader universe and recommends additions/removals to the watchlist based on technical setup quality, recent momentum, and upcoming catalysts.

## Context
- Current watchlist is user-managed (add/remove in Scanner sidebar)
- Alert rules already define what makes a good setup
- Could scan S&P 500, NASDAQ 100, or sector leaders
- Recommendations based on proximity to key MAs, volume trends, pattern setups

## Scope
- Daily scan of broader universe (top 200-500 liquid stocks)
- Rank by "setup readiness" score
- Show recommendations in Scanner or dedicated tab
- User accepts/rejects suggestions

## Dependencies
- Expanded data fetching (beyond current watchlist)
- AI Trade Narrator (shared API integration)
