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

---

*Mocks by Claude · design decisions confirmed with the product owner in-session. Educational product — keep the not-financial-advice footers.*
