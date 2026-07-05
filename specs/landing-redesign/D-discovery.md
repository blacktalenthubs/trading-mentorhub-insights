# Sub-spec D — Find the Next Big Winner (Discovery)

Part of the Landing Redesign master spec.

## Goal
Make the momentum-discovery story explicit and concrete — the "how you'd have caught MU/SNDK early"
engine — which the current landing omits entirely.

## What it shows
Header: "How you'd have caught MU or SNDK early." Sub: "Momentum isn't luck — it's a search you can
run every day. Three layers, from this morning's breakout to the multi-year hold."
Three cards:
1. **Morning Focus** — each morning, names sitting on a **monthly breakout**: a locked multi-month
   base (MoBO) or a prior-month high about to reclaim (RC-H). "The MU-off-$96 setup, before it ran."
2. **Trade Ideas** — five screens: In-Play volume · Swing setups · Conviction leaders · Growth
   leaders · Early-Turn (Emerging). Ranked → start with a shortlist, not a blank chart.
3. **Long Term Finders** — the ETF technique: names across multiple thematic ETFs (the next
   RKLB/AST before the crowd), each with a plain-English dossier (Moonshot · Emerging Leader ·
   Compounder).

## Requirements
- **D1** Describe each surface accurately to the code: Morning Focus = `morning_leaders.py`
  (MoBO/RC-H); Trade Ideas = `screener.py` (5 boards); Long Term Finders = `etf_finders.py`.
- **D2** Frame these as **computed scans** (not "AI") — deterministic discovery.
- **D3** The MU/SNDK narrative is used as illustration, not a performance promise (no returns claim).
- **D4** Surface the Morning Focus engine prominently — today it is buried in-app.

## Acceptance
- A visitor can name at least one discovery surface after reading (SC6).
- No projected/return claim appears; illustrations are clearly historical/how-it-works.

## Reuse / build notes
- New section (no current equivalent). Reuse card grid + accent tints.
- Deep-links (for logged-in users) → Trade Ideas / Long Term Finders / Today's Focus.

## Effort: M
