# Earnings Tracker — Phased Plan

**Date:** 2026-05-30
**Status:** Approved for implementation (MVP scope)
**Owner:** User + Claude
**Depends on:** existing watchlist (per-user `watchlist` table), existing APScheduler worker, existing notifier (Telegram + push)

---

## Overview

Today, when a user holds NVDA in their watchlist, the app has no idea NVDA reports earnings in 3 days. The user discovers it themselves — usually by getting blindsided by a 4% pre-earnings drift or an after-hours gap. We collect intraday volume, slope, MA stack, PDH, and PWH on every alert, but we don't collect the single biggest scheduled catalyst on the calendar.

This adds the missing piece: a per-symbol earnings calendar refreshed nightly, a Watchlist → Earnings tab that sorts the user's symbols by days-until-earnings, and a T-7 notification so the pre-earnings drift window doesn't catch anyone off guard. Historical surprise data gets stored so a future spec can feed it to the AI scanner ("setup looks clean, but NVDA reports in 4 days — half size or skip").

## Problem statement

Three real failure modes today:

1. **Blindsided trades** — user takes a clean PDH-break long on TSLA at 9:35am, holds intraday, gets stopped after lunch when TSLA fades on earnings-day-eve risk-off. The setup was structurally fine; the calendar context was missing.
2. **Missed pre-earnings drift** — most large caps trend into earnings starting ~2 weeks out. Without a calendar surface, users don't know to start watching SHOP on day T-14 instead of day T-2.
3. **AI scanner has no earnings context** — the GPT prompt today knows volume + slope + level structure but doesn't know if earnings is tomorrow. That's the difference between "trade it" and "skip it" on many setups.

## Acceptance criteria

After MVP ships:

- A user with NVDA, AVGO, ORCL in their watchlist can open Watchlist → Earnings and see all three rows sorted by next earnings date, with days-until + BMO/AMC + EPS estimate + last-quarter surprise % visible without clicking anything.
- 7 calendar days before any watchlist symbol's earnings, the user receives one Telegram message + one push notification: *"NVDA reports in 7 days (Wed Jun 12 AMC). Pre-earnings drift window opens."* — fires once per (symbol, earnings cycle).
- A symbol with no upcoming earnings within 90 days shows "—" instead of a fake date.
- A symbol that just reported shows its actual EPS vs estimate (beat/miss %) for at least 30 days after.
- If the nightly refresh job fails or returns partial data, the next night picks up cleanly. Stale data shows a "last refreshed" timestamp so the user knows when something's off.

## Out of scope (MVP)

- T-14 / T-1 / day-of / post-earnings notifications (T-7 only for now)
- Revenue beat/miss tracking (EPS only first)
- AI scanner enrichment with earnings context (future spec — data lands in DB now, prompt change later)
- Earnings-day price reaction history (future)
- International tickers (US-listed only for MVP)
- User override / hide earnings for specific symbols
- Backfill historical surprises for symbols user added long ago (only forward-fill from MVP launch)

---

## Architecture

```
┌─────────────────┐
│ Finnhub API     │  /calendar/earnings   /stock/earnings
└────────┬────────┘
         │ 60 req/min free tier
         │ once nightly @ 04:00 ET
┌────────▼────────────────────┐
│ APScheduler cron            │  jobs/refresh_earnings.py
│  - read watchlist symbols   │  joins existing scheduler
│  - fetch + upsert           │  (same one running swing scan)
│  - check T-7 + notify       │
└────────┬────────────────────┘
         │
   ┌─────▼─────┐         ┌──────────────────┐
   │ earnings  │◄────────┤ /earnings/upcoming│  GET
   └───────────┘         │   (FastAPI)       │
   ┌───────────┐         └──────────────────┘
   │ earnings_ │                  ▲
   │ history   │                  │
   └───────────┘                  │
   ┌────────────────────┐         │
   │ earnings_          │         │
   │ notifications_sent │         │
   └────────────────────┘         │
                                   │
                          ┌────────┴─────────┐
                          │ Watchlist page    │
                          │   ↳ Earnings tab  │
                          │ (React, TanStack) │
                          └──────────────────┘
```

**Why Finnhub free tier and not yfinance:** yfinance hits the same Railway IP rate-limiting we saw with the swing scanner. Finnhub's free tier (60 req/min) handles 150 watchlist symbols × 2 calls = 300 requests in ~5 minutes once a day. Reliable. If we outgrow the free tier later, drop in Financial Modeling Prep (~$14/mo) — same shape.

**Why nightly and not real-time:** earnings calendar changes maybe once per quarter per symbol (when companies confirm). Hourly polling would waste 23× the API budget for unchanged data. Nightly catches every confirmation in time for the T-7 notification window.

**Why a separate notifications-sent table and not a flag on `earnings`:** we want each earnings cycle to fire its own T-7 — if a symbol reports Q1 in Apr, Q2 in Jul, both should trigger. A boolean flag on `earnings` would be wrong by the next quarter. A keyed `(user_id, symbol, earnings_date)` row in `earnings_notifications_sent` is correct forever.

## Functional requirements

**FR-001 — Earnings calendar table**
Create `earnings` with columns: symbol (pk part), next_earnings_date, time_of_day (`BMO`|`AMC`|`DMH`|null), eps_estimate, revenue_estimate, confirmed (bool), fetched_at. One row per symbol — always upcoming, replaced when a new quarter is announced.

**FR-002 — Earnings history table**
Create `earnings_history` with columns: symbol + quarter_label (pk), eps_actual, eps_estimate, surprise_pct (computed), reported_at, fetched_at. Append-only — new quarters insert, existing skip on duplicate-key.

**FR-003 — Nightly refresh job**
APScheduler cron `refresh_earnings` runs 04:00 ET Mon–Sun. Pulls distinct symbols from `watchlist` (across all users), fetches Finnhub calendar + history, upserts both tables. Retries with exponential backoff on 429. Logs symbol count, insert count, errors. Idempotent — re-running gives the same result.

**FR-004 — T-7 notification trigger**
At the end of the refresh job, for each `(user_id, symbol, next_earnings_date)` where `next_earnings_date = today + 7 days` AND no row exists in `earnings_notifications_sent` for that key: send Telegram + push, insert the sent-marker. Message template: `"📅 {SYMBOL} reports in 7 days ({Day Mon DD} {BMO/AMC}). EPS est ${eps_est}. Pre-earnings drift window opens — watch for trend acceleration."`

**FR-005 — Upcoming endpoint**
`GET /earnings/upcoming` returns watchlist symbols for the authed user, sorted by `next_earnings_date` ASC NULLS LAST, joined with last historical quarter's surprise_pct. Response shape per row: `{symbol, next_date, days_until, time_of_day, eps_estimate, last_surprise_pct, last_quarter_label, confirmed, fetched_at}`.

**FR-006 — Earnings tab in Watchlist page**
New tab labeled "Earnings" inside the existing Watchlist page (not a new sidebar entry — preserves the 6-menu consolidation). Default sort: days-until ASC. Columns: Symbol · Days · Date · BMO/AMC · EPS Est · Last Q Surprise · Confirmed badge. Earnings within 7 days highlighted with an amber tint. Empty state when no watchlist symbol has data: "No upcoming earnings in the next 90 days for your watchlist."

**FR-007 — Stale-data indicator**
Surface "Refreshed Xh ago" at the top of the Earnings tab using the most recent `fetched_at` across the user's symbols. Visual warning (amber) if > 36 hours stale.

## Non-functional requirements

**NFR-001 — Free tier budget**
Refresh job must complete in ≤ 8 minutes for 200 symbols (within Finnhub free tier headroom).

**NFR-002 — No notification spam**
Same `(user_id, symbol, earnings_date)` must never fire twice. Enforced via unique constraint on `earnings_notifications_sent (user_id, symbol, earnings_date)`.

**NFR-003 — Idempotent job**
Running `refresh_earnings` twice on the same night produces identical DB state and zero duplicate notifications.

**NFR-004 — Graceful no-data**
A symbol that Finnhub has no calendar entry for (small caps, ETFs, crypto) MUST NOT block the rest of the run and MUST NOT crash the API. Stored as `next_date = null`.

**NFR-005 — API auth + tier**
Finnhub API key in env (`FINNHUB_API_KEY`). Free tier capped at 60 req/min — implement a token-bucket throttle in the fetcher, not raw `sleep(1)` per call.

## Build phases

**Phase 1 — schema + nightly job (no UI yet)**
- Add Alembic migration for `earnings`, `earnings_history`, `earnings_notifications_sent`.
- Add Finnhub fetcher module.
- Add `jobs/refresh_earnings.py` + register in APScheduler.
- Verify via psql: `SELECT * FROM earnings ORDER BY next_earnings_date LIMIT 20`.
- T-7 notification logic — test by manually setting one row's `next_earnings_date = today + 7 days` and re-running.

**Phase 2 — endpoint + tab**
- Add `/earnings/upcoming` FastAPI route.
- Add Watchlist → Earnings tab component + table.
- TanStack Query hook `useUpcomingEarnings`.
- Empty state, stale-data warning.

**Phase 3 — polish**
- Click a row → opens Trading page on that symbol.
- Export CSV.
- "Mark as reported" manual override if Finnhub data lags.

## Future (post-MVP)

- T-14 + T-1 + post-earnings cadence.
- Revenue beat/miss.
- AI scanner prompt enrichment with `days_until_earnings`, `last_4_surprises`.
- Earnings-day historical price reaction (move %, gap %, IV crush proxy).
- "Trade idea" generator: pre-earnings drift longs on consistent beaters.
