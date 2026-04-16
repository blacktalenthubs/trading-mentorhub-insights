# Spec 46 — Stable State Reference (2026-04-16)

**Status:** Active baseline. Do NOT modify without a concrete, repeatable bug.
**Git anchor:** tag `known-good-2026-04-16` → commit `17d60a1`
**Purpose:** The canonical description of production behavior as of 2026-04-16.
Every future proposed change to the AI signal stack must diff against this
document. If the proposed change doesn't clearly fix a named bug, it doesn't
ship.

---

## 0. How to use this spec

1. **Before ANY change to `analytics/ai_day_scanner.py`, `ai_swing_scanner.py`,
   `ai_best_setups.py`, or `intraday_data.py`:** read the relevant section
   below. State in the change proposal which specific behavior is changing
   and why.
2. **Restore to this baseline at any time:**
   ```bash
   git reset --hard known-good-2026-04-16
   git push --force origin main
   # Restart Railway worker.
   ```
3. **Backup branches** — experimental stacks preserved:
   - `backup-2026-04-16-experiments` — Spec 44/45, Amendments 7-9, etc.
   - `backup-2026-04-15-state` — yesterday's state (Amendment 6, Spec 42/43)

---

## 1. AI Signal Stack — `analytics/ai_day_scanner.py`

### 1.1 Models

| Scanner | Model | File:line |
|---|---|---|
| Day scan entry (LONG/SHORT/RESISTANCE) | `CLAUDE_MODEL_SONNET` (`claude-sonnet-4-20250514`) | ai_day_scanner.py:896 |
| Day scan exit management | `CLAUDE_MODEL` (default `claude-haiku-4-5-20251001`) | ai_day_scanner.py:1704 |
| Swing scan | `CLAUDE_MODEL_SONNET` | ai_swing_scanner.py |
| Best setups | `CLAUDE_MODEL_SONNET` | ai_best_setups.py |

### 1.2 Day-scan prompt structure (`build_day_trade_prompt`)

Order of sections:
1. WHAT TO LOOK FOR (support bounce LONG, resistance rejection SHORT, mid-range WAIT)
2. KEY LEVEL PRIORITY (daily MAs dominant, PDH/PDL, session hi/lo, VWAP)
3. PHILOSOPHY — "prefer firing LOW over WAIT at key levels"
4. CONVICTION LADDER (3+ confirmations = HIGH, 2 = MEDIUM, 1 = LOW)
5. KEY LEVELS THAT ALWAYS WARRANT FIRING (MA test, PDH/PDL, VWAP reclaim, session hi/lo, weekly/monthly levels)
6. FLIPPED LEVEL RULE (broken resistance becomes support on retest → LONG)
7. CONTEXT-AWARE FRAMING (pullbacks vs mid-range)
8. SHORT RULES (tight; PDH/MA/weekly/monthly rejection, RSI ≥ 70 confluence)
9. OUTPUT FORMAT: `SETUP:`, `Direction:`, `Entry:`, `Stop:`, `T1:`, `T2:`, `Conviction:`, `Reason:`

### 1.3 Direction policies

- **SPY:** allowed LONG / SHORT / RESISTANCE / WAIT.
- **SPY SHORT** requires MEDIUM or HIGH conviction (LOW is suppressed).
- **Non-SPY SHORT** is downgraded to RESISTANCE notice (informational only; no trade alert fired).
- **RESISTANCE** is a notice, not a trade — it includes an entry level but no buy/sell action.

### 1.4 Staleness gate (progress-to-T1)

`STALE_THRESHOLD = 0.5` at `analytics/ai_day_scanner.py:913+`.
- LONG stale if `(current - entry) / (T1 - entry) > 0.5` → direction → WAIT.
- Reason replaced with: `"Setup {N}% to T1 — move already played..."`.
- Runs AFTER SHORT→RESISTANCE policy so non-SPY SHORTs become informational
  even if staleness also applies.

### 1.5 Current price resolution

At `scan_day_trade`:
- Calls `fetch_latest_price(symbol)` (Alpaca latest-trade endpoint, sub-second stale).
- Falls back to `bars_5m[-1]["close"]` if Alpaca returns None.
- Prompt's `[INTRADAY LEVELS]` block tells AI to use LIVE price for
  "where are we now," 5-min bar for structure/levels.

### 1.6 Dedup

- **In-memory** `_day_fired` — dict of `{symbol: set((symbol, direction, level_bucket))}`.
- **Bucket:** `_level_bucket(price)` rounds to 2 significant figures
  (e.g. $2207 → $2200, $123 → $120).
- **DB seed on startup** — reads today's alerts table and repopulates
  `_day_fired` so restarts don't re-fire the same bucket.
- **One fire per (symbol, direction, bucket) per session.**
- **WAIT dedup** by fingerprint (reason text stripped/lowercased/first 80 chars).

### 1.7 UPDATE / WAIT delivery policy

- **Trade alerts** (`ai_day_long`, `ai_day_short`, `ai_resistance`, `ai_exit`):
  delivered to Telegram for every watching user whose tier cap isn't exceeded
  and who opted into that direction.
- **WAIT alerts** (`ai_scan_wait`): delivered ONLY for:
  - SPY / NVDA / ETH-USD (market barometers), OR
  - Users holding an open position on the symbol.
- Free tier: 3 WAIT Telegrams/day; Pro/Premium unlimited.
- Min 3-min cadence between WAIT Telegrams per symbol.
- DB row always written for dashboard feed regardless of Telegram gate.

---

## 2. Other AI Scanners

### 2.1 `analytics/ai_swing_scanner.py`

- **Cadence:** every 15 min during market hours (`api/app/main.py` lifespan).
- **Purpose:** 3-10 day swing LONG entries at daily/weekly structural levels.
- **LONG-only** — SHORT suppressed.
- **Proximity gate:** price within 1.5% of entry level.
- **Reclaim gate:** price must be at/above entry.
- **Dedup:** bucket by 1% of entry price per (symbol, direction, conviction).
- **Tier caps:** Free 2/day, Pro/Premium unlimited.

### 2.2 `analytics/ai_best_setups.py`

- **Cadence:** on-demand via `GET /api/v1/ai/best-setups` endpoint.
- **Purpose:** AI Coach ranks top setups across user's watchlist.
- **Tier caps:** Free 1/day, Pro 20/day, Premium unlimited.

### 2.3 Game plan (`analytics/game_plan.py`)

- 9:05 AM ET weekdays.
- Pre-market game plan + top setups briefing.

---

## 3. Data sources — `analytics/intraday_data.py`

### 3.1 Fallback chains

- **Equities intraday 5m bars:** Alpaca `_fetch_alpaca_bars` → yfinance fallback.
- **Equities latest-trade:** Alpaca `fetch_latest_price` → None (caller falls back to bar close).
- **Crypto intraday:** Alpaca `_fetch_alpaca_crypto_bars` → Coinbase → yfinance.
- **Daily (prior-day) context for crypto:** Coinbase daily candles (primary) → yfinance fallback.
- **Daily for equities:** yfinance (Alpaca bars used only intraday).

### 3.2 Why this chain matters

- Alpaca is the **real-time truth** — sub-second fresh for both latest-trade and bars.
- yfinance intraday is 15-min delayed and subject to Yahoo rate limits.
- Coinbase crypto daily has no missing bars; yfinance drops crypto weekend bars.

---

## 4. Scheduler jobs — `api/app/main.py` lifespan

| Job | Cadence | Purpose |
|---|---|---|
| `alert_monitor` | 3 min | Rule-based alerts (if `RULE_ENGINE_ENABLED=true`) |
| `ai_day_scan` | 5 min | AI day scan (LONG/SHORT/RESISTANCE/WAIT + exit signals) |
| `auto_trade_monitor` | 1 min | Open auto-pilot trades: target/stop watch |
| `auto_trade_eod` | 16:05 ET weekdays | Close stragglers at EOD |
| `ai_swing_scan` | 15 min | Swing scanner |
| `game_plan` | 9:05 ET weekdays | Pre-market plan |
| `premarket_brief` | 9:15 ET weekdays | Data + AI pre-market brief |
| `eod_cleanup` | 16:30 ET weekdays | Close stale active entries |
| `daily_review` | 16:35 ET weekdays | EOD performance review |
| `trade_replay` | 16:40 ET weekdays | Auto-journal trade replays |
| `weekly_review` | 17:00 ET Fridays | Weekly coaching review |

---

## 5. Alert types & Telegram format

### 5.1 Alert types (column `alerts.alert_type`)

- `ai_day_long` — LONG entry at support.
- `ai_day_short` — SHORT entry at resistance (SPY-only after policy downgrade).
- `ai_resistance` — approaching overhead level; notice, not trade.
- `ai_scan_wait` — mid-range / no-setup context (AI UPDATE).
- `ai_exit_signal` — exit management on open positions.
- `ai_swing_long` — swing LONG at daily/weekly level.
- `ai_swing_target_hit`, `ai_swing_stopped_out` — swing lifecycle events.

### 5.2 Telegram format for LONG/SHORT (`alerting/notifier.py`)

```
AI SIGNAL — LONG SPY $700.91
Entry $700.91 · Stop $700.11 · T1 $701.30 · T2 $702.00
VWAP reclaim on closed bar above after testing. 1.5x volume. RSI 70
momentum. Higher-low structure from $700.49. Targeting session high.
```

- Bold header with symbol + price.
- Line 2: structured levels (Entry/Stop/T1/T2).
- Line 3+: reason (analyst note). Truncated for free tier.
- No Conviction or Setup labels in Telegram (removed `bb36886` 2026-04-15).
- Confluence badge (🟢 / 🟡) if multi-timeframe detected.

### 5.3 Telegram format for AI UPDATE

```
AI UPDATE — SPY $700.91
VWAP reclaim on closed bar above after testing. 1.5x volume. RSI 70
momentum. Higher-low structure from $700.49. Targeting session high.
```

- Bold header with symbol + price.
- Reason only — no entry/stop/target (not actionable).

---

## 6. Tier system — `api/app/tier.py`

### 6.1 Tier enum

```
FREE (0) → COMP (1) → PRO (2) → PREMIUM (3) → ADMIN (99)
```

### 6.2 Daily limits

| Feature | FREE | COMP | PRO | PREMIUM |
|---|---|---|---|---|
| `ai_queries_per_day` | 3 | 3 | 50 | ∞ |
| `ai_scan_alerts_per_day` | 3 | ∞ | ∞ | ∞ |
| `ai_wait_alerts_per_day` | 3 | ∞ | ∞ | ∞ |
| `ai_swing_alerts_per_day` | 2 | ∞ | ∞ | ∞ |
| `best_setups_per_day` | 1 | 1 | 20 | ∞ |
| `watchlist_max` | 5 | 25 | 10 | 25 |
| `alert_history_days` | 0 | ∞ | 30 | ∞ |

- **SPY / NVDA Telegram delivery** bypasses tier caps (loss-leader).
- **COMP tier** = family + friends: unlimited Telegram, limited dashboard AI.
- **Trial:** 3-day default.

---

## 7. Env vars that gate behavior

| Var | Default | Effect |
|---|---|---|
| `RULE_ENGINE_ENABLED` | `true` | Rule-based alert monitor on/off |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | unset | Alpaca data fetch (real-time) |
| `ALPACA_DISABLED` | `false` | Force yfinance-only |
| `ANTHROPIC_API_KEY` | unset | Claude API calls (required) |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Exit scanner model |
| `CLAUDE_MODEL_SONNET` | `claude-sonnet-4-20250514` | Day/swing/best-setups model |
| `DATABASE_URL` | unset → SQLite dev | Postgres connection (prod) |
| `TELEGRAM_BOT_TOKEN` | unset | Required for delivery |
| `TELEGRAM_CHAT_ID` | unset | Default admin chat |
| `SWING_SCAN_ENABLED` | `true` | Swing scanner on/off |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | unset | Admin auto-seed on boot |

---

## 8. Known behaviors (intentional, not bugs)

### 8.1 In-memory state wiped on worker restart

- `_day_fired` dedup is seeded from DB on startup but held in memory.
- `_last_tg_direction`, `_last_tg_time`, `_last_wait_reason_fp` are in-memory.
- During rapid iteration (frequent deploys) dedup windows reset.
- **Accepted:** in normal production (few deploys/day) this is invisible.
  Intentionally chose simplicity over DB-backed persistence for hot paths.

### 8.2 Dedup buckets coarsen with price magnitude

- `_level_bucket(2207) = 2200` — all LONGs $2200-$2299 share one bucket.
- Once any LONG fires in that range, no other LONG fires there this session.
- **Accepted:** avoids over-firing in the same price zone. Trade-off: can
  miss a fresh setup 50 ticks away on the same side.

### 8.3 WAIT fingerprint dedup is per-session, memory-held

- Identical WAIT reason won't re-Telegram within the session.
- Worker restart loses fingerprint history; brief re-Telegram possible.
- DB fallback catches most duplicates via alerts-table query.

### 8.4 Staleness gate uses live price if available

- If Alpaca latest-trade returns None and bar close is stale, a "setup not
  yet played out" may be incorrectly marked stale.
- Live price is the freshest signal we have; fallback accepted.

### 8.5 SHORT suppression on non-SPY is by design

- Non-SPY SHORTs converted to RESISTANCE notice (informational).
- User doesn't get a "SHORT symbol" trade alert outside SPY.
- Rationale: SHORT edge is weaker intraday outside market proxy.

### 8.6 Swing scanner is LONG-only

- Same rationale — avoids noise on short-term swing SHORTs.

### 8.7 Staleness + dedup can compound

- Fire a LONG at $700, hit T1 at $701 → staleness gate converts subsequent
  scans to WAIT for the rest of the window.
- On a re-setup at $702 same day, staleness still applies until price resets.
- **Accepted:** avoids chasing; user waits for fresh setup.

---

## 9. Evaluation criteria for future changes

Before proposing ANY change, answer these:

1. **What specific bug did a user report?** If "could be better" — reject.
2. **Which section of this spec does the change modify?** State it.
3. **What observable behavior changes?** One sentence.
4. **What could break?** Name at least one plausible failure mode.
5. **How is it rolled back?** Env flag preferred; if code-only, confirm with
   the user before shipping.
6. **Does it change prompt text?** Budget ONE full trading session of
   observation before the next change. Prompt effects propagate non-linearly.
7. **Does it touch files listed in CLAUDE.md "Protected Files"?** Then the
   AI Signal Change Protocol applies: spec update → user review → explicit
   "approved" → code. No exceptions.

### 9.1 Red flags (auto-reject unless user explicitly overrides)

- "Let me also add X while I'm in here" — bundled changes.
- "Shipping one more quick fix before we validate the last one."
- Silent behavior changes without a log line.
- Changes to prompt wording + changes to gate logic in the same commit.
- Changes made without the user witnessing the bug live.

---

## 10. Observations logged from 2026-04-16 rollback

**Day summary** (SPY / NVDA session):
- 7 actionable alerts (4 LONG, 1 SHORT, 2 RESISTANCE).
- 153 unique UPDATEs — ~6/hr per symbol.
- Morning reversal calls caught cleanly (09:33-10:10 ET).
- Midday PDH battle narrated with volume + RSI + structure.
- Staleness gate correctly suppressed chasing after T1 hits.
- Live-price fix eliminated the 5-min bar staleness complaint.

**User verdict:** "UPDATEs were the real GOATs. AI was very authentic."

**Rule adopted:** no changes until a concrete, repeatable burn is observed.
Future work begins from this baseline.

---

## 11. Related specs (historical context, not current behavior)

These specs exist in `specs/` but their changes were reverted in the rollback:
- Spec 41 (day-scan prompt refactor) — Amendments 7-9 rolled back.
- Spec 42 (level proximity pre-filter) — rolled back.
- Spec 43 (simplified dedup + heartbeat cadence) — rolled back.
- Spec 44 (daily regime context) — never merged, lives on `backup-2026-04-16-experiments`.
- Spec 45 (UPDATE suppression material-change gate) — never merged, lives on backup branch.

Any of these may be revisited one at a time with full user approval and
one full session of observation between them.

---

**This spec is the line in the sand. Everything past here must prove its
worth against this baseline before it ships.**
