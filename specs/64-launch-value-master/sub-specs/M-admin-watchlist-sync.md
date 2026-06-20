# Sub-spec M — Admin Master-Watchlist Sync (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Trust (no missed alerts) · **Priority:** P1 · **Status:** Draft

## Overview
One admin action that guarantees **no user misses an alert on a name they're watching.** It rolls every user's watchlist into a single **master watchlist** and pushes that union to TradingView via the MCP job — so the scanner charts (and therefore can alert on) **every symbol any user tracks**.

## Problem
Alerts only fire for symbols the TradingView scanner is actually charting. Today the TV-monitored universe is curated/static — it does **not** reflect what users add to their personal watchlists. So when a user adds, say, RGTI to their list, **no alert ever fires for it** unless an admin happens to already have it on the scanner. The user silently misses every setup on their own watchlist. Nothing connects **user watchlists → the TV-monitored universe.**

## Target state
- An admin **"Sync watchlists"** action that computes the **deduped union of all active users' watchlist symbols** and pushes it to the TradingView master watchlist via the MCP bridge.
- The scanner/alerts then cover **every** user-tracked symbol; the existing alert pipeline routes each fired alert to the users whose watchlist contains that symbol (unchanged).
- Admin sees **what changed** (added/removed) and **sync health** (last run, symbol count, per-symbol failures).

## Acceptance criteria
- **M-1:** The master watchlist equals the **deduped union** of all active users' watchlists at sync time.
- **M-2:** After a sync, a symbol that only **one** user tracks **is present in the TradingView watchlist** (verifiable via the MCP `watchlist_get`).
- **M-3:** End-to-end — a user adds a symbol → admin syncs → an alert that fires on that symbol **routes to that user**, no miss.
- **M-4:** The admin sees the **diff** (symbols added / removed this run) + **last-synced time & count**; a partial failure (symbols TV rejected) is **surfaced, not silent**.

## Scope
**Build:**
- **Union query** — `SELECT DISTINCT symbol` across watchlist items for **active** users (exclude disabled/expired accounts).
- **Master-watchlist record** — persist the current synced set + metadata (`last_synced_at`, `symbol_count`, per-symbol status).
- **MCP push** — diff the union vs the current TV watchlist; `watchlist_add` the new, optionally remove orphans (symbols no user tracks anymore), through the existing **tv_sync** MCP bridge.
- **Admin UI** — a "Sync watchlists" button + a panel: union count, last-sync time, the add/remove diff, any per-symbol failures.
- **Trigger** — admin-manual at launch; a scheduled nightly/intraday sync is the fast-follow.

**Out of scope:**
- Per-user TradingView layouts (this is one shared master watchlist).
- Real-time per-add sync — batch/admin-triggered is enough for launch.
- The alert→user **routing** logic (it already keys off per-user watchlists; this spec only guarantees the symbol is *charted* so an alert can fire at all).

## Architecture (HLD)
- **Source of truth:** `watchlist_items` → distinct symbols for active users.
- **Master record:** a `master_watchlist` table (or singleton config) holding the synced set + `last_synced_at`, `symbol_count`, per-symbol sync-status.
- **MCP bridge:** the existing tv_sync path — `mcp__tradingview__watchlist_get` (read current) → `watchlist_add` (push new). Diff = `union − current` (add) and `current − union` (remove-orphans, behind a flag so an admin-pinned symbol is never dropped).
- **Endpoint:** `POST /admin/watchlist/sync` (admin-gated) → union → diff → MCP push **in a thread** (slow + rate-limited, like the earnings refresh) → returns the diff + status. `GET /admin/watchlist/sync` returns last-sync metadata for the panel.
- **Routing (unchanged):** the alert pipeline already filters fired alerts to users whose watchlist includes the symbol.

## Risks / decisions
- **TV watchlist size limits** — a large union (hundreds of symbols across many users) may exceed the scanner's practical capacity. **Decision:** cap + prioritize (symbols on ≥N users' lists, or focus-list/conviction names first); surface what was dropped — **no silent truncation**.
- **Orphan removal** — dropping a symbol no user tracks could remove an admin-pinned name. **Decision:** removal is opt-in and preserves an admin "always-keep" set.
- **Headless MCP auth** — the MCP→TV bridge needs an authenticated TV session, so the sync must run where that session lives (the local tv_sync bridge), **not** a headless cron, until that's solved.

## Notes
Closes a real trust gap: the platform promises alerts on *your* watchlist, but only delivers if the symbol is on the TV scanner. This makes the promise true. Reuses the tv_sync MCP bridge + the existing per-user routing; the new pieces are the union query, the master record, and the admin panel.
