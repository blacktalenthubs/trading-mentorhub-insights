# UI Redesign Mockups

Self-contained HTML mockups for the platform redesign (Jul 2026). Open any file in a browser.
Every mock has two toggles in the top bar: **▢ Modern / ▣ Terminal** (corner/typography treatment) and **🌙 / ☀️** (dark/light). Data shown is illustrative.

## Shared design system

All six pages use one token system, mapped to the existing tokens in `web/src/index.css`:

- Surfaces `--s0..--s4` (#0f1117 → #2e3548 dark; light variants included in each file)
- Text ramp `--tp/--ts/--tm/--tf` · lines `--line/--line2`
- Semantic: bull green `#22c55e`, bear red `#ef4444`, amber `#f5b73d` (section headers, warnings), blue `#3b82f6` (accent/selection), violet `#a78bfa` (long-term/core)
- Mono for all numbers/labels/section headers (`.sh` = amber uppercase mono); sans for prose
- Shared shell: status bar (brand · clock · market state pill · SPY/BTC regime chips)

Implementation agents: reuse the CSS class patterns across pages — cards (`.card`/`.pick`), stat tiles (`.tile`), plan quads (`.plan`), lens chips (`.lens`), state badges — they are intentionally identical between files.

## Page roles (the big picture)

- **Trading** = the live cockpit: chart, watchlist, signal feed, level map, alert log.
- **Today** = the briefing room: the day's plan and reports, in trading-day order. **No live feed here** — only a "Live now → Open Trading" bridge.
- Every other page feeds one of those two.

---

## 1. `trading_page_redesign_mockup.html` — Trading

Status bar + 3 columns: watchlist / chart / right rail (signals with Entry-Target-Stop plan grids, per-symbol level map with distance bars, alert log). Already being implemented.

## 2. `todays_tab_redesign_mockup.html` — Today tab

**Kill tabs-within-tabs.** One page in trading-day order, left "Your Day" timeline rail (4:30a Premarket brief → 8:55a Today's Focus → 9:45a Premarket signals → Trend setups → Bottom watch → 4:10p EOD recap) with publish-status per row; content sections anchor-scroll. Key decisions:
- **No signal feed / alert log on this page** (Trading owns live) — amber "Live now · N fired → Open Trading" bridge card in the rail instead.
- Morning Spotlight hero: best setup with NOW/BUY-POINT/AWAY tiles + Entry/Target/Stop/R:R quad + BULL context line.
- Empty states show "nearest to a level" fallbacks, never a giant empty box.
- Bottom Watch is a full-width table section here (it doesn't exist on Trading).
- Past sessions via one dropdown in the rail; reports mirror Telegram.

## 3. `trade_ideas_redesign_mockup.html` — Trade Ideas

**5 tabs → 0 tabs.** Social + AI Scans are REMOVED (hooks/components only used in `FocusListPage.tsx`; `FocusListView.tsx`/`RecommendationCard.tsx` already dead — delete). The 3 remaining screeners (`/screener/emerging|conviction|growth`) become **lenses over one unified, deduped list** (client-side join on symbol):
- "🔥 On Multiple Boards" strip leads the page — names on 2–3 boards are the strongest ideas; disagreements spelled out.
- Boards column badges: T (early turn/amber) · C (conviction/blue) · L (long-term core/violet).
- Expanded row = merged scorecard ✓/✗ + Street (rating/target/weekly stage — rescues the hidden Weekly Stage board) + tape stats + "Open in Trading".
- Keeps: Run scan, past-runs dropdown, theme chips, add-to-watchlist.

## 4. `watchlist_redesign_mockup.html` — Watchlist

3 sub-tabs: Symbols / Earnings / **Research** (rename of "Details" — it's a company dossier, not details). Research is now **master–detail**:
- Left: symbol list grouped by sector, each row = consensus chip + freshness dot (fresh/stale/not-fetched).
- Right: one dossier, fixed order — Head (freshness line, actions) → Key Numbers tiles → Where It's Trading (MA chips + 52w range slider) → The Street (rating distribution bar) → **Investment Brief structured**: thesis lede → 2×2 case grid (moat/growth/valuation/Street) → Bull vs Risks side-by-side (green/red) → Short-term vs Long-term verdict band → company boilerplate collapsed last.
- Maps 1:1 to existing `FundamentalsItem`/`FundMetrics`/`AIBrief` fields. Make it routable: `/watchlist/research/:symbol` (today it's localStorage-only). Replace hardcoded admin email with a real `is_admin` check.
- Symbols tab gains the ★ Focus star inline (hooks exist, currently only usable from Trading sidebar).

## 5. `premarket_redesign_mockup.html` — Premarket

**The gap desk.** Hero = **Gap & Go Queue**: top 3 from the existing broad gap scanner (`analytics/premarket_gaps.py`), ranked by a quality score (gap% × PM $vol × catalyst × above-PDH × watchlist/theme). Each card: Watch (PMH) / Go trigger (5m close above on 2× vol = existing `GAP_AND_GO` condition) / Stop (PM low) / Invalidation (gap fill = existing `GAP_FILL`), plus delivery receipts (📨 8:30 notes · ☀️ Today's tab · 🔔 alert armed).
- Telegram preview panel = the block appended to the 8:30 morning notes (top 3–5 gap-ups with levels).
- Gap Board = one table, Clean/Momentum as lens chips, queue-pin column. Sector Heat = breadth cards + pre-bell read (incl. theme-concentration risk).
- Wiring: add `quality_score`/`queue_rank` to the gap snapshot; `triage-agent/premarket.py` reads top-3 from it; publish queue into Today's morning reports. ⚠️ Arming per-symbol alerts touches protected files (`intraday_rules.py`/`alert_config.py`) → needs impact analysis + explicit approval first (see CLAUDE.md); sequence that last.

## 6. `performance_redesign_mockup.html` — Performance

**"Performance without homework."** Signals grade themselves; users never type close prices:
- Day → intraday R race (+1R before −1R via MFE/MAE on 5m bars) — **already computed nightly** by `analytics/alert_outcomes.py` (16:30 ET) into `Alert.real_outcome/mfe_r/mae_r`; the close is irrelevant (a day trade can win and the stock finish red).
- Swing → EOD marks (`forward_returns.py`, 16:45 ET) while tracking; resolved at target/stop (lifecycle watcher already detects hits — add a verdict write).
- Long-term → weekly mark-to-market.
- **EOD claiming is the primary flow**: report card grouped by session date (date picker + unclaimed-days catch-up strip); each row has `✓ took / — pass` buttons; claims backfill the signal's grade/R automatically (existing `POST /alerts/{id}/ack` works retroactively). "✎ my fill differed" is the optional correction. Unclaimed = ignored (not scored as a decision).
- Style lens All/Day/Swing/Long-term (split exists nowhere today; derive via `style_for(alert_type)` — `RealTrade` needs a style field).
- Pattern Edge table (EDGE/CUT/BUILDING verdicts) fed by auto-grades + user overlay; R-based equity curve (kill fake $50k dollar sizing); Passed On gets the ✓/✗ "would it have worked" verdict (= `real_outcome` joined onto skipped alerts — currently stubbed in `DeclinedTrades.tsx`).
- Cleanup: unify the two took/report flows; delete orphaned `PerformanceDashboard.tsx`, `EquityCurve.tsx`, unused hooks.

## 7. `start_here_redesign_mockup.html` — Start Here

**One persistent checklist replaces the two disconnected onboarding flows** (`/onboarding` register-wizard uses category-based `useUpdateAlertPrefs`; `/start-here` uses `trade_group` bulk toggles — they conflict and neither persists). Redesign:
- **Disclaimer front and center** — a new user's first screen carries the full educational/not-financial-advice notice (amber panel, top of page), not just a footer. Keep the footer versions everywhere else.
- Numbered steps with real state: 1) Choose how you trade (the 4 style cards, kept) → 2) Add symbols (quick chips + editor's-sectors shortcut) → 3) Connect Telegram → 4) Learn the setups (optional). Progress bar persists server-side (add an onboarding-state record — today "Enabled ✓" is lost on refresh).
- **Education finally linked**: each style card gets "see these setups →" to `/pattern/:code`; step 4 shows 3 lesson cards with anatomy mini-diagrams; register-wizard and this page should converge on ONE alert model (recommend the `trade_group` bulk model; retire the category model or map it).
- Right rail: "Your Day With the Desk" timeline (8:30 notes → Today 8:55 → Trading at open → Performance after close) — the orientation/mental-model tour that exists nowhere today; plus "Your Alerts Right Now" status (style/symbols/delivery), which surfaces the killer misconfiguration: alerts enabled but no delivery channel.
- Fixes to carry: the "I'm new" 3-pack codes (`weekly_ma_held` doesn't exist in the catalog; `staged_pdl_reclaim` unverified) must be validated against real `alert_type` values — today the card can show "Enabled ✓" while enabling nothing. Add Start Here to mobile nav (currently desktop-rail only). Route register → this page instead of the separate wizard.

## 8. `settings_redesign_mockup.html` — Settings

**One endless scroll → nav rail with 5 sections** (Alerts / Delivery / Risk & sizing / Appearance / Account), replacing the 9 stacked cards in `web/src/pages/SettingsPage.tsx` (944-line single file). Key decisions:
- **Uniform save model**: everything saves instantly (today it's a mix of instant saves and dirty-state Save buttons) — say so once in the rail.
- **Alert Types wall → clustered toggle rows**: short plain-English name + one-line trigger + Long/Short tag. Day Trade clusters: *PDH/PDL core levels* / *4h reclaims* / *Weekly-monthly wick tests* / *Noisy*. Group master switch per Day/Swing/Long-term header + ON/OFF legend (ON = Telegram+feed, OFF = records silently).
- **Scoping systems unified in place**: the SPY 8/21 market gate renders as a banner INSIDE the Day Trade group (it gates day-trade longs); the ORL allowlist (`orl_always_symbols`) renders as chips ON the ORL row — delete the separate MarketGateSection/OrlScopeSection cards.
- Delivery = Telegram connect/test + channel toggles; Risk = position sizing; Account absorbs referrals.

### ⚠️ Alert catalog retirement spec (decided 2026-07-03, NOT yet implemented — for the coding agent)
Retire exactly these four types (add to `OBSOLETE_ALERT_TYPES` in `api/app/models/alert_type_config.py` and remove from `_BASE_CATALOG`, same pattern as the June retirements; startup seed deletes rows, webhook drops arrivals):
- `orh_break` — ORH-based, opening-range levels retired from the day-trade book
- `reclaim_long` — ORH-based morning reclaim (its PDH half is covered by `rc_daily_hrec`)
- `cml_reclaim`, `cml_held` — CML re-retired (was retired May 2026 by user request; re-added 2026-06-25 in error)

Explicitly KEEP: `staged_orl_held` (the one OR survivor — already scoped to the user-editable ORL allowlist, which is the noise control) and both 4h RC types. No dedup/group moves were approved. Also fix the `pullback_long` zombie (present in both `_BASE_CATALOG` and `OBSOLETE_ALERT_TYPES`; obsolete deletion wins on startup — remove it from the catalog). Net: 33 → 29 types, Day Trade 15 → 13.

### ➕ ORB box alert family (decided 2026-07-03 after backtesting — ADD, do not replace RC)
Owner's call: the RC alerts are powerful and stay untouched. The ORB grammar (validated by eye on
MU/SEZL 15m with `pine_scripts/active/orb_pd.pine`) is ADDED as a new day-trade family, **scoped to
a user-editable symbol allowlist** (same mechanism as `staged_orl_held` / `orl_always_symbols`) —
start with a few names to monitor noise before widening. Four types, all on 15m confirmed closes,
rails = ORH/ORL (first-15m box) + PDH/PDL, once per rail per direction per day, interaction
required (parked-beyond never fires):
- `orb_break` — close through a rail; payload flag `stacked: true` when one close takes ≥2 rails
  in the same direction (the ignition bars — strongest form, worth calling out in the message)
- `orb_held` — rail tested from the far side and held (SEZL's ORL bounce)
- `orb_retest` — a broken rail retested and REJECTED in the break's direction (the second entry)
- `orb_exit` — a rail given back on a confirmed close (the stop — deliver it; today users never
  get the death notice)
Reference logic: `pine_scripts/active/orb_pd.pine` implements the exact state machine (run/touch/
fired/inval/retest arrays). Pipeline note: the existing confluence-collapse dedup should absorb
overlap with `staged_pdh_break`/`staged_pdl_break` on stacked bars.

## 9. Strategy Lab — EOD evaluation agent (spec, no mockup; decided 2026-07-03)

**Concept (the owner's words):** "we have entry and we can query the price" — grading IS that. One
nightly job: take today's sent alerts, query the post-alert prices, write down what happened against
ENTRY and STOP only (targets are explicitly out — they're mostly wrong; MFE distributions will
eventually *derive* correct targets instead). A weekly agent reads the accumulated rows and reports
what's working. A working reference implementation of the whole evaluation exists from the Week-1
manual run: see the session scripts (pull → grade → aggregate) — ~80 lines with yfinance.

### Nightly job (runs with the existing 16:05/16:15/16:30 triage-agent schedule; ~16:30 ET)
- Input: today's alerts where `suppressed_reason IS NULL` (sent only — but ALSO grade a sample of
  suppressed ones: they're a free control group for auditing the gates).
- Dedup: first fire per (session_date, symbol, alert_type).
- Fetch 5m bars (yfinance RTH; Alpaca as second source for the audit). ⚠️ intraday data expires
  (~60d) — grading must happen same-day or evidence is lost forever.
- Per alert compute BOTH stop conventions, entry/stop only:
  - `touch`: 5m wick through stop → stopped, R = −1
  - `close` (PRIMARY — matches how the owner trades): 15m close through stop → stopped, R = actual
  - plus `mfe_r` (max favorable before stop), `r_eod`, horizon per style (day → session close;
    swing → also T+3/T+5 closes on later runs; long → weekly marks)
- Persist to a new `alert_grades` table (alert_id, convention, stopped, r, mfe_r, horizon, data_source,
  ambiguous flag, graded_at). Never overwrite; re-grades append with source.
- Health counters logged every run: N graded / skipped (no-window, bad-risk, no-data) / % stops <0.3%
  of entry / feed-agreement % on a 20-alert two-source sample.

### Weekly report (Friday post-close, publishes via reports_store like the EOD recap → Telegram + Today)
- Health first (grading coverage, stop-quality, feed agreement) — findings are gated on health.
- Per-setup scoreboard: N · stopped% (close) · median R · clipped mean R (±3) · median MFE. Use
  medians/clipped means — raw means are destroyed by tight-stop outliers (proven in Week 1).
- Hypothesis ledger: findings start as HYPOTHESIS with a written forward prediction; only advance to
  CONFIRMED on later, unseen weeks; CONFIRMED → DEGRADING → retire-proposal. Proposals are
  human-veto ONLY — the agent never changes alert config (protected logic).
- Baselines: report excess-R vs same-window SPY (drift check) and vs random-entry control.

### Week-1 findings already in hand (2026-06-26 → 07-03, hypothesis tier)
- 🔴 **Production grading is DOWN**: 0 of 222,136 alerts had real_outcome/mfe_r/ret_eod_pct — the
  16:30/16:45 api jobs aren't running or fail silently. FIX FIRST (protected files → owner sign-off).
- 🟠 **Stop-sizing bug**: 22% of sent alerts carry stops <0.3% from entry (rc_4h_short median 0.15%,
  ma_bounce_ema8 0.20%) — floor stops at e.g. max(level, 0.5×ATR).
- **Close-stops > wick-stops, quantified**: 18% of touch-stop-outs survived the close convention and
  averaged +5.15R after — adopt close-based stops in grading AND alert copy.
- Positive cells: rc_4h_long (N=34, medR +0.56) · rc_daily_hrec (N=29, +0.60) · staged_pdh_break
  (N=6, +1.63, small). Negative: cml_reclaim −0.95 (retired same day ✓) · staged_pdl_held offers
  1.9R MFE but 62% stop → stop too tight, not a dead setup. reclaim_long ≈ 0 and was 19% of ALL
  pipeline fires (41,365/wk) — retirement doubly justified.
- Data nits: tickers `BCHUSD`/`LTCUSD` malformed (missing `-USD`); grade swing/MA-bounce types at
  T+3/T+5 before judging them (day-horizon grades are unfair).

---

*Mocks by Claude · design decisions confirmed with the product owner in-session. Educational product — keep the not-financial-advice footers.*
