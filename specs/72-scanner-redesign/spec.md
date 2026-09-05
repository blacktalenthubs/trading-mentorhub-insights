# Scanner — day-trade signal engine

**Status:** live · **Type:** day-trade scanner · **Owner:** vbolofinde
**Last updated:** 2026-09-05 (PRs #1118, #1119, #1120, #1122)

This is the current state of the scanner, not a change log. It describes what the
system does today; the history is at the bottom.

---

## The principle

**Buy support in an uptrend; short resistance in a downtrend. Never trade a level
you can't prove was acting as support or resistance today.**

The proof is where the day OPENED relative to the level. That single test is what
separates a real reclaim from a stock ramping up into an average from below.

---

## The two rules

### Long — open-above reclaim (`check_ma_reclaim`)

```
day_open   >  L      the day opened ABOVE it, so L was support
session_low ≤ L      price wicked down and tagged it
last_close >  L      price closed back above it
(close − L) / L ≤ 1.5%   staleness guard — not already run away
```

Entry = the reclaim close · Stop = `L × 0.995` (then risk-capped by `_cap_risk`)
Targets from `_targets_for_long` (structural ladder with an ATR floor).

### Short — liquidity grab (`check_ma_rejection`)

The mirror, and the pattern has a name: price sweeps **through** the level, takes the
stops resting above it, and closes back below. The push was made and lost.

```
day_open    <  L     the day opened BELOW it, so L was resistance
session_high >  L    price traded THROUGH it — a touch is not a grab
last_close  <  L     price closed back below it
(L − close) / L ≤ 1.5%   same staleness guard
```

Entry = the close · Stop = `L × 1.005` · Targets from `_targets_for_short`.

`check_pdh_rejection` is the same pattern on yesterday's high, on the current bar:
high **above** the PDH, close below it, and the bar's open at or below it — so the
level sits above the body and the excursion through it is a wick, not a body. An open
above the PDH means price was already through the level and is losing it: a breakdown,
not a grab.

Chart-validated 2026-09-04: LRCX 100 EMA qualifies as a reclaim; MRVL 21 EMA (opened
below → cross-up) is correctly rejected.

---

## What fires — 25 enabled rules

### Longs (14) — any symbol in `SCANNER_UNIVERSE`

| Rule | Level | Open gate |
|---|---|---|
| `ma_reclaim_8` / `21` / `50` / `100` / `200` | daily SMA | **yes** — per level |
| `ema_reclaim_8` / `21` / `50` / `100` / `200` | daily EMA | **yes** — per level |
| `prior_day_low_reclaim` | PDL | no — structural level |
| `prior_day_high_breakout` | PDH | no (skipped only if it *gapped above* PDH; crypto exempt) |
| `pdh_retest_hold` | PDH as support | no — structural level |
| `multi_day_double_bottom` | daily swing-low zone | no — structural level |

The open gate is an **MA test only**. A prior-day high or low is a fixed structural
level and doesn't need the question asked — so a stock that opens under its moving
averages still produces level signals.

### Shorts (7) — `SHORT_UNIVERSE = {SPY, QQQ, SMH, ETH-USD}` only

`pdh_rejection`, `ma_rejection_8` / `21` / `50`, `ema_rejection_8` / `21` / `50`.

Indexes plus ETH — ETH trades 24/7, so it is the one short that can be validated on a
weekend. A short on any other symbol is recorded as `short_not_index` and never sent.

They read as what they are: **"21 EMA Liquidity Grab"**, **"PDH liquidity grab"**.

### Exits (4) — recorded, never delivered

`stop_loss_hit`, `target_1_hit`, `target_2_hit`, `auto_stop_out` stay enabled so the
trade lifecycle and P&L tracking keep recording, but delivery stamps them
`exits_not_delivered`. **Entries only** (user, 2026-09).

---

## Universe

`SCANNER_UNIVERSE` — 39 symbols, hardcoded in `monitor.py`. Not the per-user
watchlist: a fixed, controlled set while the redesign is validated.

```
SNXX SNDK MUU MRVL DELL MU LITE VRT META MRNA COHR QQQ JPM HOOD GOOGL MSFT PLTR
SPCX NOW LLY SPOT ANET NBIS SHOP CRWD NVDA AMZN APP RKLB TSLA XLI SPY AVGO CRCL
MSTR AAPL SMH  +  BTC-USD ETH-USD
```

`is_market_hours_for_symbol()` filters per poll: equities 09:30–16:00 ET, crypto 24/7.
On a weekend that leaves BTC-USD and ETH-USD — two symbols, not thirty-nine.

---

## Delivery

**Global.** No per-user alert-type toggles, category preferences or min-score gate.
The universe and the rule set are hardcoded, so what fires delivers. Those Settings
rows still exist and still drive the TradingView webhook path — this is the scanner
path only.

Poll runs every 3 minutes (`alert_monitor`, APScheduler in `api/app/main.py`), plus
once immediately at startup.

### Gates a signal clears, in order

1. **Level dedup** — same direction within 0.2% of a recent alert's entry
2. **Confluence merge** — same-level entries within 0.2% collapse into one
3. **Direction/type lock** — same type on the same symbol, 10 minutes
4. **Entries only** — shorts must be index; exits never send
5. **1 alert / symbol / type / day**
6. **Burst cooldown** — 30 minutes per symbol after any entry
7. **Zone cluster** — 30 minutes per symbol/direction/price bucket

There is **no higher-timeframe trend gate**. It was removed — see History.

### Every suppression is recorded

An alert that fires but doesn't send still writes its row, stamped with why:

| `suppressed_reason` | Meaning |
|---|---|
| `confluence_collapsed:<winner>` | merged into another entry at the same level |
| `dedup_type_day` | this type already fired on this symbol today |
| `dedup_cooldown` | inside the 30-minute burst window |
| `dedup_zone` | same price zone as a recent alert |
| `short_not_index` | a short outside `SHORT_UNIVERSE` |
| `exits_not_delivered` | a stop or target hit |
| `not_an_entry` | NOTICE or any non-entry direction |

The feed's clean view shows `suppressed_reason IS NULL` — what actually sent. "Show
collapsed" reveals the rest, labelled ("merged into 50 SMA Reclaim").

A collapsed sibling records its row and nothing else: no `ActiveEntry` (the winner
owns the entry — a duplicate would fire the stop/target lifecycle twice), no AI
narrative, and it bypasses the level-dedup that would otherwise drop it before
recording.

---

## How an alert reads

One name everywhere — feed, Telegram and push all resolve the rule key through the
same mirrored formatter (`_pretty_setup` in `alerting/notifier.py`, `formatSetup` in
`web/src/lib/alertFormat.ts`):

```
Title:  SPY LONG · 50 SMA Reclaim
Body:   Entry $769.20 · Stop $766.10 · T1 $774.00 · Confluence: 21 SMA + 50 EMA
```

A merged alert names its factors in the message; `Alert.confluence_label` carries the
compact form (`21 SMA + 50 EMA`) that `AlertCard` renders as "• Confluence: …". Above
50 characters it degrades to `×4 at $769.20` rather than truncating mid-word.

Every one of the 21 entry types carries a plain-English description, so its feed card
explains itself — the MA ladder by rule in `describe_alert_type()` / `setupBlurb()`,
the named types by table entry.

---

## The feed

`isScannerEntry()` admits exactly the 21 entry types — the ladder
(`^(ma|ema)_(reclaim|rejection)_\d+$`) plus the four named longs and `pdh_rejection`.
A test asserts every admitted type is in `ENABLED_RULES`, so nothing aspirational can
reach the feed before it can fire.

`style_for()` resolves all of them to `day_trade`, including the 200s — the scanner's
entire set lands in the **Day** feed; nothing from it reaches Swing.

The in-app notification fires only for delivered alerts (`suppressed_reason IS NULL`).

---

## Files

| File | Role |
|---|---|
| `analytics/intraday_rules.py` | `check_ma_reclaim`, `check_ma_rejection`, `evaluate_rules` |
| `analytics/intraday_data.py` | `prior_day` levels incl. MA 8/21/20/50/100/200 + EMAs |
| `alert_config.py` | `ENABLED_RULES`, `SHORT_UNIVERSE`, thresholds |
| `api/app/background/monitor.py` | `SCANNER_UNIVERSE`, poll loop, confluence merge, delivery |
| `alerting/notifier.py` | Telegram + `_pretty_setup` |
| `api/app/models/alert_type_config.py` | `style_for`, `describe_alert_type` |
| `web/src/lib/alertFormat.ts` | `isScannerEntry`, names, blurbs |
| `web/src/pages/TradingPageV2.tsx` | Day/Swing feed, suppression labels |
| `analytics/htf_bias.py` | confluence score only — the gate helpers are deprecated |

## Tests

- `tests/test_ma_reclaim.py` (6) — the open-above rule
- `tests/test_scanner_delivery.py` (18) — the rejection mirror, confluence merge and its
  audit rows, label sizing, naming parity, SMA 8/21 wiring, the feed contract, shorts
  index-only, exits recorded-not-delivered, no HTF gate

`test_intraday_rules.py`: 635 pass, 4 fail — the same 4 SPY-regime failures as on
`main`, pre-existing and unrelated.

## Deploy

1. Push to main — Railway deploys the worker, Streamlit Cloud the dashboard.
2. **Restart the Railway worker.** It caches `alert_config` / `intraday_rules` in
   memory; nothing takes effect until it does.
3. No Settings change needed — delivery reads no per-user toggles.
4. Weekend crypto (BTC/ETH, 24/7) is the live validation target.

---

## History

**Phase 1 — signal quality (#1118).** Replaced the bounce rules, which fired on any
touch of an MA with no open test and couldn't tell support from resistance being ramped
into (MRVL / LITE-21 / STX false fires), with the open-above reclaim. Added the
hardcoded universe, the confluence merge, 1/type/day, and entries-only delivery.

**Phase 2 — delivery (#1119).** Phase 1 shipped to nobody: `isFeedSignal()` admitted
only `ai_*` / `tv_*` types, so every scanner alert was filtered out of the feed, the
alert log and the in-app notification; and the per-user preference gate muted the new
reclaims for anyone who had toggled the now-deprecated bounce types. Made delivery
global, made suppressions visible, fixed the push payload, wired the SMA 8/21 reclaims
that had shipped as enums with nothing behind them.

**Current set (#1120).** Trimmed to entries only. Removed the **HTF bias gate**: it
blocked every long whenever the 4h was BEAR and the 1h had not yet turned BULL — the
shape of a washout, so it suppressed the first reclaim off a flush, the setup this
scanner exists to catch. It was also a coarse trend proxy for what the open-above rule
now answers structurally per setup, and it suppressed *before* the alert row was
written, so what it ate left no trace. Added the index shorts. Retired the nine
weekly/monthly rules (they only ever became NOTICEs with entry/stop/targets stripped —
nothing tradeable), the un-gated `ema_rejection_short` catch-all, and the remaining
short/resistance rules outside the agreed set.

## Open

- The universe is hardcoded. Widening it back toward the per-user watchlist is a later
  decision, once the set is validated.
- `_entry_count` (max 2 entries per symbol per session) is computed in `monitor.py` and
  never used.
- `check_prior_day_low_reclaim` takes a `today_open` parameter it never reads — it looks
  like an open gate in the signature and is not one.
