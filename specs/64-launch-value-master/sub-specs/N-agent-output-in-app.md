# Sub-spec N — Agent Output In-App + Notifications to the App (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Trust + Retention (the app is the home, not Telegram) · **Priority:** P1 · **Status:** Draft (Phase 1 in progress 2026-06-20)

## Overview
Everything the AI agent produces — the per-alert **read** (narrative), the **morning brief**, the **EOD recap**, the **earnings** calendar — currently lands only in **Telegram**. The app shows the *numbers* (entry/exit) but not the *reasoning*, and push notifications are an afterthought. Make the **app the home for all agent output**, cleanly organized and collapsible per day, with **app (push) notifications as the default** — Telegram stays on during the transition, but the goal is the app for everything.

## Problem (current state)
1. **The agent's read is invisible in the app.** The signal feed shows entry/exit only. The narrative (why, conviction ⚪ NORMAL, sector/index/cluster context, "first of type in 60min, 2.7× vol…") is composed for Telegram and never exposed — the alert API didn't even return the `narrative` column.
2. **Briefs are Telegram-only.** The morning brief (tape, focus verdict, top-picks performance, tomorrow watch, recap) and the EOD recap have no in-app surface.
3. **Notifications are inconsistent.** Earnings + briefs go to Telegram, not as app push. The app should be the primary channel.
4. **Clutter risk.** Dumping all of this into one feed would be unreadable — it needs per-day, collapsible organization.

## Target state
- **Today → Briefing tab** — the agent's per-alert read, collapsible per alert, grouped per day. The default place a busy user comes for the *why*, not just the numbers. The **Signals** tab stays the quick entry/exit feed (unchanged).
- **Morning brief + EOD recap** viewable in the app as collapsible daily cards.
- **Earnings this week** surfaced in-app (already a Watchlist tab; also shown in the Briefing day-card).
- **App push notifications default** for alerts, earnings, and briefs; Telegram parallel/opt-in.
- Clean, collapsible, per-day UI — scannable, no wall-of-text.

## Scope — phased
- **Phase 1 (built 2026-06-20):** expose `narrative` on the alert API (`AlertResponse`); **Today → Briefing tab** rendering the per-alert agent read, collapsible. *(backend + frontend)*
- **Phase 2:** morning brief + EOD recap in the app — a backend store/endpoint for the briefs (currently composed Telegram-only) → collapsible daily cards in Briefing.
- **Phase 3:** notification defaults — push for alerts + earnings + briefs; a Settings toggle (app / Telegram / both), **default app-on**, Telegram opt-in.
- **Phase 4:** earnings folded into the Briefing day-card (the "Earnings this week" + pre-earnings drift note).

## Acceptance criteria
- **N-1:** every alert that carries an agent narrative shows that read in Today → Briefing, collapsible, without leaving the app.
- **N-2:** the morning brief + EOD recap are viewable in the app, not just Telegram.
- **N-3:** a new account receives alerts / earnings / briefs as **app push by default**; Telegram is opt-in/parallel.
- **N-4:** the Briefing is organized **per day, collapsible, scannable** — no clutter.

## Out of scope
- **What the agent computes.** The narrative/brief *content* is produced by the AI services (Sub-spec F) — this spec only **surfaces** existing output and routes notifications.
- The **signal feed** stays as the quick entry/exit view (unchanged) — Briefing is the complementary "read" surface.

## Notes
This is the **delivery/surfacing** layer for the agent. Related: **F** (AI services / token economy — produces the reads + briefs), **H** (triage agent), **I** (EOD self-reporting). The dual-channel (app + Telegram) is deliberate during the transition so nothing is lost while the app becomes the default.
