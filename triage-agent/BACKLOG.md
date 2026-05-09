# Triage Agent — Backlog

Captured 2026-05-09. Things we know we want but aren't shipping today.

## P0 — As soon as the agent runs in prod for a week

- [ ] **More Pine alerts on watchlist symbols** — proximity, volume-spike, additional index ETFs (XLK, IWM, XLF, XLE). Dense Pine signal = better sector confluence detection. Zero incremental cost (already pay for TradingView).

## P1 — Close the "agent only sees what Pine fires" gap

Sector confluence today is **level-based** (only catches peers when they trip a Pine setup). A peer can move 1% in the same direction without tripping. To close:

- [ ] **Path B: Batched yfinance peek per alert.** Single yf.download() call grabs 5-min bars for the alert's sector peers; agent computes "are peers up >X% in last 15min?" Adds ~$5–10/mo + 1–2s latency. ~50 lines of code in `triage.py`.
- [ ] **Path C: Cached regime refresh.** Background goroutine polls index ETFs + sector members every 30s; agent reads from in-memory cache. Eliminates per-alert latency. Only worth it if Path B latency becomes a problem.

## P2 — Single master switch (clean kill switch)

Two static bypasses exist where AI calls don't go through `_resolve_api_key()`:
- [ ] **`analytics/ai_conviction.py:96`** — uses raw `ANTHROPIC_API_KEY` constant. Today: gated by `AI_CONVICTION_ENABLED=false` default. Risk: if anyone flips that flag, master kill switch doesn't actually hold.
- [ ] **`scripts/telegram_bot.py:451`** — same pattern. User-triggered (only fires on bot message), so lower urgency. Belt-and-suspenders fix: route through `_resolve_api_key()`. ~5 line change total across both files.

## P3 — Format / UX

- [ ] **VWAP** — currently dropped from message. If we want it back: add `vwap` column to `alerts`, modify `tv_webhook.py` to write it from Pine payload, agent reads. ~10 lines of code + 1 SQL migration.
- [ ] **Conviction score** — agent currently emits HIGH/NORMAL/MUTE. If a numeric score is desired (like Pine's "MEDIUM/35"), compute one from sector_aligned + index_aligned + volume_ratio + cvd_diverging. ~30 lines.
- [ ] **Trade button callback acks** — currently agent's buttons match notifier's `callback_data` format, so existing handler in `scripts/telegram_bot.py` should still work. Verify end-to-end after first day live.

## P4 — Other agents (from the original ideas list)

- [ ] **Confluence Agent** — deeper version of triage that watches multiple indicators across timeframes for the same symbol and waits for them to align before notifying.
- [ ] **Pre-Market Briefing Agent** — runs at 8:30am ET; walks watchlist; reads overnight news; produces a "things to watch today" Telegram digest.
- [ ] **Trade Journal Agent** — when a Pine signal fires AND user takes the trade (Took It button), capture chart state + indicator values + market conditions. Later: ask the agent natural-language questions about the journal.
- [ ] **Pine Code Review Agent** — paste a Pine script; agent uses TradingView MCP `pine_check`/`pine_smart_compile` tools + lookahead/repaint heuristics to give a review.

## P5 — Operational

- [ ] **Daily summary digest** — end-of-day Telegram message: "today: 7 HIGH, 18 NORMAL, 4 MUTE; cost $0.27; top 3 by sector confluence: X, Y, Z".
- [ ] **Per-week accuracy review** — compare agent's HIGH calls against actual price moves the next 1h/4h/1d. Surface what worked, what didn't.
- [ ] **Live mode metrics** — heartbeat to Grafana / Railway logs; alert if no heartbeat for >10min.

## Non-goals (decided NOT to do)

- ❌ **Volume-based muting** — low volume can be the *most* meaningful signal at support before a spike. Decided 2026-05-09 after user explicit feedback.
- ❌ **Time-window-only dedup** — IONQ at $46.32 → $49.25 case showed time-window dedup would suppress real new breakouts. Switched to (eventually) price-proximity-aware dedup.
- ❌ **Modifying Pine to remove Stage line** — instead drop it at the Telegram-format layer (which we did, agent owns the message format).
