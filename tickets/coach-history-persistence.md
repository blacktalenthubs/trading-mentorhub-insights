# Coach History Lost on Worker Redeployment

**Priority**: Medium
**Created**: 2026-04-10

## Problem
AI Coach conversation history disappears when the Railway worker redeploys. The `coach_messages` table and API endpoints exist, but the frontend may not be loading history reliably on reconnect after a deploy.

## Investigate
1. Is the `coach_messages` table actually being created on deploy? (check migration in main.py)
2. Are messages being saved via the POST endpoint? (check network tab)
3. Is the GET endpoint loading history on mount? (check useCoachStream hook)
4. Could be a timing issue — frontend reconnects before the new worker is ready

## Expected
Coach messages persist across deploys, page reloads, and tab switches. User should see their previous conversation when they return.

## Files
- `api/app/models/coach.py` — CoachMessage model
- `api/app/routers/coach_history.py` — GET/POST/DELETE endpoints
- `web/src/hooks/useCoachStream.ts` — frontend persistence logic
- `api/app/main.py` — table migration
