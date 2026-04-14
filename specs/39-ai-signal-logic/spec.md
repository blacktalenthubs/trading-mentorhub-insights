# Spec 39 — AI Signal Logic (Reference)

**Status:** Living reference — captures current behavior as of 2026-04-14
**Related:** Spec 34 (day scanner), Spec 35 (auto paper trade), Spec 36 (user prefs),
Spec 37 (conviction ladder), Spec 38 (swing scanner)

Purpose: single document describing how AI LONG / SHORT / RESISTANCE / WAIT
alerts are generated, filtered, and delivered. Read this to understand why
a specific alert did or didn't fire, and to plan future refinements.

---

## 1. Pipelines

Two independent AI pipelines feed into the same alerts table + Telegram:

| Pipeline | Cadence | Timeframe | Model | Scope |
|---|---|---|---|---|
| **Day scanner** | every 5 min | 5-min + 1-hr bars, prior day | Sonnet 4 | User watchlist symbols |
| **Swing scanner** | every 15 min | daily + weekly bars | Sonnet 4 | User watchlist (market hours only) |

Both write to `alerts` table and (day scanner) `ai_auto_trades` table.

```
┌─────────────┐   per 5 min   ┌─────────────────┐
│ Scheduler    │──────────────▶│ day_scan_cycle   │
└─────────────┘               │ (Sonnet 4)       │
                              └────┬─────────────┘
                                   │
                            ┌──────┴──────┐
                            ▼             ▼
                      ┌──────────┐  ┌──────────┐
                      │ alerts   │  │ Telegram │──▶ user
                      │ table    │  │ (gated)  │
                      └──────────┘  └──────────┘
                            │
                      ┌─────┴────────┐
                      ▼              ▼
                ┌──────────┐  ┌──────────────┐
                │ Dashboard │  │ ai_auto_    │
                │ feed      │  │ trades      │
                └──────────┘  └──────────────┘
```

---

## 2. Day Scanner — Decision Tree

```
scan symbol at time T
  │
  ├─ fetch 5-min bars (last 20) + 1-hour bars (last 10) + prior_day (MAs, RSI, weekly/monthly pivots)
  ├─ build prompt with conviction ladder + all levels
  ├─ Sonnet 4 call (~2-3s)
  │
  ▼
AI returns: SETUP / Direction / Entry / Stop / T1 / T2 / Conviction / Reason
  │
  ├─ [Staleness gate]
  │    LONG: current > entry × 1.004  → WAIT
  │    SHORT: current < entry × 0.996 → WAIT
  │
  ├─ [SHORT policy]
  │    Non-SPY SHORT → RESISTANCE (notice only, no trade alert)
  │    SPY SHORT LOW → RESISTANCE (require MEDIUM+)
  │    SPY SHORT MEDIUM/HIGH → fire
  │
  ├─ [Dedup check] (symbol, direction, level_bucket) already fired today?
  │    → seeded from alerts table at cycle start (survives restart)
  │    → skip if already fired
  │
  └─ Fire LONG / SHORT / RESISTANCE / WAIT per delivery rules (§5)
```

---

## 3. Conviction Ladder (§7 prompt detail)

Conviction is scored by **confluence count** — how many confirmations stack,
not any single metric.

### LONG confirmations (count how many are true)
| # | Confirmation |
|---|---|
| a | Higher low structure on 5-min (last swing low above prior) |
| b | RSI showing strength (>45) or oversold reversal (<35 turning up) |
| c | Volume pickup on bounce bar (>0.7x avg) |
| d | Multi-level confluence (2+ levels: e.g. VWAP + 50MA, PDL + 100EMA) |
| e | Reclaim pattern (briefly broke level, back above) |

### SHORT confirmations (mirror)
| # | Confirmation |
|---|---|
| a | Lower high structure on 5-min |
| b | RSI weakness (<55) or overbought rollover (>65 turning down) |
| c | Volume on rejection bar (>0.7x avg) |
| d | Multi-level resistance stack |
| e | Failed breakout (briefly above, back below) |

### Scoring
- **HIGH** — 3+ confirmations
- **MEDIUM** — 2 confirmations
- **LOW** — 1 confirmation or just touching the level
- AI states *which* confirmations applied in the Reason field.

### Policy
- At a key level (MA, PDH/PDL, VWAP, session hi/lo, prior swing), prefer
  firing LONG/SHORT LOW over WAIT — user decides.
- WAIT is only for: price mid-range, no level within 0.3%, no structure.

---

## 4. Scanner Policies (global filters)

| Policy | Effect |
|---|---|
| **Staleness** | LONG entry already bounced +0.4% → WAIT. SHORT already rejected -0.4% → WAIT. |
| **SHORT suppression** | SHORT only fires on SPY; other symbols get RESISTANCE notice. |
| **SPY SHORT min conviction** | SPY SHORT LOW → RESISTANCE. MEDIUM/HIGH fire. |
| **Level dedup** | Same (symbol, direction, level bucket) fires once per session. Persists across worker restarts via DB seed. |
| **Excluded from public report** | BTC-USD filtered from all `/auto-trades/*` public endpoints. |

---

## 5. Per-User Delivery Gates (order of checks)

```
alert fired
  ├─ Is user in the symbol's watchlist? (day) / OR matches universe (swing)
  ├─ Does user have Telegram enabled + chat_id set?
  ├─ alert_directions filter — user opted in to this direction?
  ├─ min_conviction filter — signal conviction >= user's minimum?
  ├─ swing_alerts_enabled (swing only) — user has opted in?
  ├─ tier rate limit check — under daily cap?
  └─ deliver via Telegram
```

Position-aware overrides:
- WAIT / RESISTANCE auto-skipped if user **holds** position on that symbol
  (except SPY/NVDA — see §6)

---

## 6. AI UPDATES (WAIT) Delivery Policy

WAIT ("AI UPDATE") messages are informational — price context without an
actionable entry. To reduce noise we restrict who sees them:

| Scenario | Delivery |
|---|---|
| Symbol is SPY or NVDA | Always deliver (market barometer) |
| User holds open position on symbol | Deliver (exit context) |
| Neither condition true | Skip delivery (DB row still written for dashboard) |

Additional gates:
- 5-min / 10-min time-based dedup (if same reason fingerprint)
- Per-reason fingerprint stored in DB (survives restart)
- Free-tier daily cap (`ai_wait_alerts_per_day`)

---

## 7. Prompt Structure (day scanner)

```
SECTION 1: Philosophy — fire at key level with scaled conviction, prefer LOW over WAIT
SECTION 2: Trigger universe — what counts as a "key level"
SECTION 3: Conviction ladder — confluence scoring (§3)
SECTION 4: Output format — SETUP / Direction / Entry / Stop / T1 / T2 / Conviction / Reason
SECTION 5: Rules — entry = level not current, MAX 60 words, etc.

INJECTED DATA:
  [KEY LEVELS]  — PDH, PDL, prior close, daily MAs/EMAs, weekly/monthly
  [DAILY MAs]   — 20/50/100/200 MA + EMA (strongest intraday S/R)
  [INTRADAY]    — VWAP, current price, volume ratio, RSI
  [5-MIN BARS]  — last 20 OHLCV
  [1-HOUR BARS] — last 10 OHLCV
```

---

## 8. Tier Rate Limits

| Feature | Free | Pro | Premium |
|---|---|---|---|
| `ai_scan_alerts_per_day` (LONG/SHORT/RESISTANCE/EXIT) | 3 | ∞ | ∞ |
| `ai_wait_alerts_per_day` (WAIT delivery) | 3 | ∞ | ∞ |
| `ai_swing_alerts_per_day` | 2 | ∞ | ∞ |

### Uncapped symbols (loss leader)
- **SPY, NVDA** bypass `ai_scan_alerts_per_day` entirely — free users get
  unlimited alerts on market barometer symbols.

---

## 9. Swing Scanner — Delta from Day Scanner

| Aspect | Day | Swing |
|---|---|---|
| Bars | 5-min + 1-hour | Daily (60 bars) + weekly/monthly pivots |
| Cadence | 5 min | 15 min during market hours |
| Directions | LONG / SHORT / RESISTANCE / WAIT | LONG / SHORT / WAIT |
| Extra gate | — | AI-driven invalidation: "if structural stop >5% from current, output WAIT" |
| Conviction | Confluence count | Same philosophy, daily-candle focused |
| Dedup | 1% price bucket | 1% price bucket |

---

## 10. Example Decision Walk-through

**Scenario**: ETH-USD at $2,363 testing 100 Daily EMA ($2,363.91) + VWAP ($2,368).
RSI 63.7. Session low tested twice.

```
Sonnet output:
  Direction: LONG
  Entry: $2,363.91
  Stop: $2,356.14
  T1: $2,376.04
  T2: $2,392.66
  Conviction: MEDIUM  (confluence: 100EMA + VWAP + RSI strength = 3 = HIGH technically,
                       but AI noted "overbought risk" so downgraded to MEDIUM)
  Reason: Testing 100 EMA + VWAP confluence, RSI 63 shows strength, double-tested
          session low holding

Staleness check: current $2,365 vs entry $2,363.91 → 0.05% above → not stale.
Dedup check: (ETH-USD, LONG, $2363.91) not fired today → pass.
SHORT policy: N/A.
Fire → watchlist users get Telegram with auto-paper-trade opened.
```

---

## 11. What's Intentionally NOT in the Model

| Not done | Why |
|---|---|
| No model-based position sizing | User controls via `default_portfolio_size` / `default_risk_pct` |
| No options / LEAP signals | Future spec |
| No real brokerage execution | Paper only |
| No backtesting / historical replay | Spec 35 Phase 4 (TBD) |
| No ML-learned conviction weights | AI generates conviction each scan; we'd need ground truth labels to train |

---

## 12. Known Refinement Candidates (future work)

1. **Volatility-adaptive staleness gate** — use ATR(14) instead of fixed 0.4%.
   Currently flagged-to-do — TSLA needs wider slack than SPY.
2. **Live quote refresh at Telegram send** — include "price now $X" so user sees
   drift from scan-time to delivery.
3. **3-min day scanner cadence** — tighter freshness window. Cost ~+$3/mo.
4. **Confluence scorer telemetry** — log which confirmations AI cited per fire,
   so we can audit if conviction distribution is healthy (not all LOW, not all HIGH).
5. **Auto-tune `MAX_ENTRY_DISTANCE`** from swing hit-rate data (replaced by AI
   invalidation rule — revisit after 30 days if AI rule isn't strict enough).
6. **Dedup window decay** — currently session-long. Consider allowing refire at
   same level after 2+ hours if price has traveled through and returned.
7. **Explicit setup taxonomy** — AI free-texts SETUP field today. Could constrain
   to 8-10 canonical buckets (e.g. "PDL reclaim", "VWAP bounce", "100MA test") for
   performance attribution later.

---

## 13. Files Owning This Logic

| File | Role |
|---|---|
| `analytics/ai_day_scanner.py` | Day pipeline: scan, dedup, delivery, WAIT gate, staleness, SHORT policy |
| `analytics/ai_swing_scanner.py` | Swing pipeline (spec 38) |
| `api/app/models/user.py` | User prefs columns (`min_conviction`, `alert_directions`, `wait_alerts_enabled`, `swing_alerts_enabled`) |
| `api/app/tier.py` | Rate limit definitions |
| `api/app/main.py` | Scheduler registration (5-min day, 15-min swing) |
| `alert_config.py` | Model constants (`CLAUDE_MODEL`, `CLAUDE_MODEL_SONNET`) |
| `alerting/notifier.py` | Telegram send primitives |

---

## 14. Tuning Guide (where to change things)

| I want to… | Change |
|---|---|
| Change conviction rubric | `build_day_trade_prompt()` in `ai_day_scanner.py` §3 of prompt |
| Adjust staleness threshold | `1.004` / `0.996` constants in `scan_day_trade()` |
| Change uncapped symbols | `_UNCAPPED_SYMBOLS` set |
| Enable SHORT on more symbols | SHORT policy block after `parse_day_trade_response()` |
| Change WAIT delivery audience | `_is_priority_sym` set + delivery loop condition |
| Tighten scan cadence | `scheduler.add_job(..., minutes=N)` in `main.py` |
| Change tier caps | `TIER_LIMITS` dict in `api/app/tier.py` |
| Add a new symbol policy (e.g. QQQ uncapped) | Add to `_UNCAPPED_SYMBOLS` |
| Kill-switch the swing scanner | `SWING_SCAN_ENABLED=false` env var |

---

## 15. Observability (what to watch in logs)

| Log line | What it tells you |
|---|---|
| `AI day scan SYM: Xs, Y tokens — SETUP: …` | Sonnet scan completed, first 100 chars of response |
| `WAIT gate SYM: near_level=… fires=…` | Why a WAIT did/didn't make it to Telegram |
| `AI day scan SYM: LONG stale — entry $X, now $Y (+Z%)` | Staleness gate rejected |
| `AI day scan SYM: SHORT → RESISTANCE (SPY-only policy)` | SHORT filter applied |
| `AI day scan: seeded dedup from DB — N keys` | Worker restart restoration |
| `WAIT skip uid=U sym=S reason=not_priority_no_position` | AI UPDATE filtered per §6 |
| `auto-pilot CLOSE: SYM ... reason=Target 1 hit` | Spec 35 auto-trade exit |
