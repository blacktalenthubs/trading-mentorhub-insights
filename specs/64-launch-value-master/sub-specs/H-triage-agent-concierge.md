# Sub-spec H — Triage Agent → AI Trading Concierge (P1)

**Parent:** #64 Launch Value Master · **Pillar:** The connective AI layer · **Priority:** P1 (it powers B, C, and F at once)

## Overview
We already own the single highest-leverage asset for the whole vision: a **Claude-based triage agent** (`triage-agent/triage.py`) that reads every alert, gathers rich market context, and decides **HIGH / NORMAL / MUTE** per user. It owns the 8:30 ET morning brief and Telegram delivery. **Its problem isn't capability — it's that its reasoning is invisible to the user.** This sub-spec evolves it from a silent classifier into the user's **AI desk-mate**: it curates the few names, explains every verdict in plain English, delivers a personalized brief + EOD review, answers questions, and watches risk.

## Problem (current state)
The triage agent today:
- Runs each alert through Claude → **HIGH / NORMAL / MUTE**, with a multi-step tool loop.
- Computes real context: **sector confluence, index alignment, market session, alert bias, proximity match**, prior-alert summary, and a **safety override**.
- Is **per-user** (`user_id`), **read-only** against the protected business logic.
- **Owns the morning brief** (top picks with composite score, EOD recap) and, via `AGENT_OWNS_TELEGRAM`, **owns Telegram delivery** (unified Pine + agent-context message).

But: it's a **classifier + brief**, not a concierge. The rich context it computes is **hidden**; it doesn't teach its verdicts, doesn't curate the discovery board, isn't conversational, has no EOD autopsy or portfolio/risk watch, and "MUTE" produces no teachable "why not."

## Target state
The triage agent becomes the **connective AI layer** the busy professional actually experiences:
- It **curates the few** (powers discovery, B), **explains every alert and verdict** in plain English (powers education, C), **delivers** a personalized brief + EOD review, **answers questions** (a token-metered service, F), and **watches risk** — all per-user, in their voice.

## Scope

**Surface its reasoning (powers C — education-in-flow):**
- The HIGH/NORMAL/MUTE verdict + the context behind it (sector confluence, index alignment, bias, proximity, safety override) becomes the user-facing **"why this fired · why it's HIGH · why it was muted."**
- Every **MUTE** becomes a teachable **"why not"** ("muted: counter-trend to a weak sector + index rolling over").

**Curate the discovery board (powers B):**
- Run the discovery candidates (volume surge, sector leaders, MTF confluence) through the agent so the **≤15-name board is agent-ranked with a one-line "why now,"** not a raw screener dump.

**Personalized daily bookends:**
- **Morning brief** → a per-user **game plan**: today's few names, market read, what to watch, in the user's risk profile.
- **EOD review** → an **autopsy**: what fired, what worked, what to learn (ties to C's autopsy + the real-outcome data).

**Conversational concierge (a token-metered service, F):**
- Let users ask **"what about MU?" / "should I take this?" / "what's my risk if I add NVDA?"** — reusing the agent's existing context tools (recent alerts, market session, proximity, sector/index alignment).

**Risk / portfolio watch:**
- Proactively flag **exposure, correlated positions, missing stops, over-concentration** — the discipline layer, automated.

**Personalization:**
- The user's **style, watchlist, risk tolerance, and history** shape verdicts, tone, and what surfaces.

## Acceptance criteria
- **H-1:** Every delivered alert carries the agent's verdict **and** its plain-English reasoning (powers C).
- **H-2:** Every muted alert is retained with a user-visible **"why not."**
- **H-3:** The discovery board (B) is agent-ranked, each name with a one-line "why now."
- **H-4:** A personalized **morning brief** and **EOD review** ship per user.
- **H-5:** A user can ask the agent about a specific name and get a contextual answer (token-metered).

## Out of scope
- Modifying the protected alert business logic (the agent stays read-only / advisory).
- Automated execution (the agent advises; the user acts — keep "you make the call").

## Notes
This is the **keystone**: the agent already has the context engine and the per-user model. Making its hidden reasoning **visible and conversational** delivers discovery (B), education (C), and the AI value menu (F) from one asset — the fastest path to the "surface the few, teach the why, do the chart-staring" vision. Promote to P1 alongside A and C.
