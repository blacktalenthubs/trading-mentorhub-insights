"""Per-alert-type enablement — the on/off switch for TradingView alert delivery.

The Pine scripts fire every alert they can. This table decides which types
are actually delivered, so each alert type can be enabled/disabled and tested
independently from the Settings UI — no code change, no redeploy.

Spec 58 final state (2026-05-23) — Pine is long-only. The catalog below
mirrors that: only the 19 BUY alert types the Pine actively emits. Every
historical/retired type lives in OBSOLETE_ALERT_TYPES below and is DELETED
from the catalog table on each startup, so the Settings UI never shows
dead toggles.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertTypeConfig(Base):
    __tablename__ = "alert_type_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)  # fv_* labels run 167 chars; DB widened 140→200 (2026-07-18) — a too-long label aborts the WHOLE startup seed (silently: main.py catches it as a warning)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Active MA families — bounce LONG + rejection SHORT (re-enabled 2026-06-09).
# Each generates 6 per-MA toggles: {fam}_{ema8,ema21,ema50,ema100,ema200,sma}.
# An MA is dual-role: support from above (bounce=long) / resistance from below
# (rejection=short). The NOTICE (proximity) family stays removed (too noisy).
MA_SPLIT_FAMILIES = (
    # ma_bounce_long_v3 REMOVED 2026-08-02 (user: "all that ma/sma bounce remove — 4h covers it").
    # The whole MA-bounce LONG family retired; per-MA types listed in OBSOLETE_ALERT_TYPES.
    # ma_rejection_short_v3 REMOVED 2026-07-22 (user: "remove all ema/ma short from settings, not
    # needed — remove any form of shorts except PDH rejection"). The whole MA/EMA rejection-short
    # family is retired; the per-MA types are listed in OBSOLETE_ALERT_TYPES so the seed deletes them.
)
# #282 (2026-06-17) — narrowed to 8/21/50/200 EMA + 50/200 SMA. Dropped 100 EMA,
# 100 SMA, and the combined SMA toggle (split into explicit 50/200). All default OFF;
# fire only for symbols on the ma_alert_symbols allowlist (Settings).
_MA_TOGGLES = (
    ("ema8",   "EMA 8"),
    ("ema21",  "EMA 21"),
    ("ema50",  "EMA 50"),
    ("ema100", "EMA 100"),   # re-added 2026-06-23 — the deep-pullback support (NVDA);
                             # rc.pine MA bounce fires the 100/200 in any regime.
    ("ema200", "EMA 200"),
    # SMA ladder RE-ADDED 2026-07-14 (user): the SMA is its own support level (traders watch the
    # round 20/50/100/200 SMA, not just the EMA) — reclaim it the same way. rc.pine emits the "S" tags.
    ("sma20",  "SMA 20"),
    ("sma50",  "SMA 50"),
    ("sma100", "SMA 100"),
    ("sma200", "SMA 200"),
)


# ── The canonical 19 (active alert types only) ──────────────────────────
# (alert_type, label, category, default_enabled)
# default_enabled only applies on FIRST insert — `enabled` is never
# overwritten by seeding, so user toggles persist across deploys.
_BASE_CATALOG: list[tuple[str, str, str, bool]] = [
    # Candle-close pings (2026-08-02) — scheduled heads-ups (NOT trade signals) to review charts at each
    # 2h candle close. Per-user opt-in, delivered in-app (APNs push) + Telegram. TWO independent toggles
    # so a user can pick equity-only, crypto-only, or both.
    ("candle_ping_equity", "Candle pings · Equity — heads-up at each 2h stock candle close (4/session: 11:30/13:30/15:30/16:00 ET)", "Candle pings", False),
    ("candle_ping_crypto", "Candle pings · Crypto — heads-up at each 2h crypto candle close (12/day, every 2h UTC incl. weekends)", "Candle pings", False),
    # Hourly LEVELS agent (2026-08-02) — AI read of where SPY/BTC sits vs its MA/EMA stack + 4H levels.
    ("levels_hourly", "Levels agent (hourly) — AI read of where SPY (RTH) & BTC (24/7) sit vs the MA/EMA stack + 4H levels", "Candle pings", False),

    # Pullback continuation (uptrend-gated long entry — companion to MA bounce)

    # Prior-HIGH held CUT 2026-06-23 — "high held as support" = buying resistance;
    # RC pine owns the high reclaims (rc_*_hrec, uptrend-gated). → OBSOLETE_ALERT_TYPES.
    # staged_pdh_break / pdh_held / pdl_held REMOVED 2026-08-02 (user: "pdl held etc remove — 4h
    # covers it all"). The 4H reclaim/reject/breakup/breakdn subsumes the daily PDH/PDL reclaims.
    # → OBSOLETE_ALERT_TYPES.

    # RC RETIRED 2026-08-02 (user: "replace the rc with reclaims of smart money zone — no need for
    # weekly rc and monthly rc"). daily/weekly/monthly_rc all → OBSOLETE. The level-reclaim swings are
    # now the SMA reclaims + the FV basis + the Smart Money zones (all in swing_reclaim.pine).
    # 4H day-trade method (2026-07-25) — reactions to the last two 4h candles' H/L/C, 15m-close confirmed,
    # MASTER-optin like RC (bind the pine on a 15m chart). fourh_reclaim/reject = wick+close-back reversal;
    # fourh_breakup/breakdn = one close through. Isolated from dedup (see _FOURH_TYPES) for clean analysis.
    ("fourh_reclaim", "4H reclaim (long) — a 15m candle wicked below one of the last two 4h candles' H/L/C & closed back above (support held). Bind the pine on 15m; opt in HERE.", "4H", False),
    ("fourh_reject",  "4H rejection (short) — a 15m candle wicked above a prior 4h level & closed back below (resistance held). Bind on 15m; opt in HERE.", "4H", False),
    ("fourh_breakup", "4H break-up (long) — a 15m candle closed up through a prior 4h level. Bind on 15m; opt in HERE.", "4H", False),
    ("fourh_breakdn", "4H break-down (short) — a 15m candle closed down through a prior 4h level. Bind on 15m; opt in HERE.", "4H", False),
    # Structural-level DAY reclaims (weekly-low / monthly-low / prior-2-day-low) — 2026-08-05. Same
    # reclaim mechanic as the 4H reactions on the 15m close, LONG only, stop = the swept bar low. They
    # JOIN the 4H DB-anchored day dedup stream: a 4H reclaim + these compete as ONE (symbol,BUY) anchor,
    # so the LOWEST entry wins and worse entries are suppressed. From prior_4h_two_candles.pine.
    ("day_weekly_reclaim",  "Weekly-low reclaim (day) — 15m wicked below the prior-WEEK low (PWL) & closed back above. Long, stop = bar low. Joins the 4H day dedup (lowest entry wins). Opt in HERE.", "Day levels", False),
    ("day_monthly_reclaim", "Monthly-low reclaim (day) — 15m wicked below the prior-MONTH low (PML) & closed back above. Long, stop = bar low. Joins the 4H day dedup (lowest entry wins). Opt in HERE.", "Day levels", False),
    ("day_pdlow_reclaim",   "Prior-day low reclaim (day) — 15m wicked below one of the last two days' lows (D-1/D-2) & closed back above. Long, stop = bar low. Joins the 4H day dedup. Opt in HERE.", "Day levels", False),
    # 50 EMA reactions — the SAME 4-reaction pattern on the daily 50 EMA (the one MA institutions
    # defend), as ISOLATED types so they can be toggled + evaluated separately (user 2026-07-26).
    # The ONE moving-average worth its own alert (user 2026-07-28): the daily 200 SMA/EMA is a structural
    # line institutions defend, and a RECLAIM is the same quality pattern as the 4H reclaim. Long-only,
    # reclaim-only (no reject/break/short). Folds into _FOURH_TYPES so #874's one/day + cooldown apply.

    # Gap-and-Go (equity, 2026-07-27) — the session opened ABOVE the prior high and is holding.
    # Long-only momentum, watchlist-gated. Stop = the morning low. Bind gap_and_go.pine on 15m.
    ("gap_and_go", "Gap-and-Go (long, equity) — the session opened ABOVE the prior high (PDH) and is holding above it (momentum). Stop = the morning low. Bind the pine on 15m; opt in HERE.", "Day", False),

    # Buy 2 — Prior-low held / wick test (spec 58, 2026-05-23)
    # staged_pdl_held (daily PDL held) RETIRED 2026-07-12 → folded into daily RC (rc_daily_long, directional). → OBSOLETE.
    # staged_pwl_held (weekly PWL held) RETIRED 2026-07-12 → folded into WLV. → OBSOLETE.
    # staged_pml_held (monthly PML held) RETIRED 2026-07-11 → folded into MLV. → OBSOLETE_ALERT_TYPES.

    # Proximity bounce DROPPED 2026-06-04 (spec 61) — entry = close, which
    # after a bounce off the level lands far away (TSLA PDL 416, alert fired
    # at 423). "Near support" wasn't near. The _held / _reclaim rules cover the
    # touch cases. staged_pdl/pwl/pdh_proximity live in OBSOLETE_ALERT_TYPES.

    # Opening-range-low defended (spec 61, 2026-06-03) — buy the held 15m
    # low of day, stop below the OR low, PDH = first target.

    # Prior-low + prior-high RECLAIM all CUT 2026-06-23 — the RC pine owns reclaims
    # now (rc_daily_long/hrec, weekly_rc, monthly_rc, gated). No duplicate staged
    # reclaims. → OBSOLETE_ALERT_TYPES.

    # 2026-06-01 — Anchored-VWAP family (MTD / prior-month / 2mo-prior)
    # REMOVED. AVWAP levels stay drawn on chart as visual reference only;
    # no alerts emit. Too noisy in live evaluation — 8 of 15 missed-TG
    # alerts today were mtd_avwap_held fires with no follow-through.

    # Spec 61 (2026-06-04) — PDH/PWH BREAK DROPPED. A break into PDH after a
    # rally from below is buying resistance/exhaustion. The trusted PDH entry
    # is staged_pdh_held (retest of PDH as support). staged_pdh/pwh_break live in OBSOLETE_ALERT_TYPES.
    # gap_up_continuation_long REMOVED 2026-08-02 — the DUPLICATE gap-and-go; the canonical one is
    # gap_and_go (pine-backed, above). → OBSOLETE_ALERT_TYPES.

    # Gap S/R — unfilled gaps as support/resistance (2026-06-15). day_open decides
    # the role. Replaces the old gap_zone info-notice. Default OFF — land in Muted.
    # gap_support / gap_fill / gap_reject CUT 2026-06-23 (user: "a gap means nothing if
    # it doesn't hold"). Only gap_up_continuation_long (gap-and-go) survives. → OBSOLETE.
    # lost_support_reject CUT 2026-06-23 (clearer setup). → OBSOLETE_ALERT_TYPES.

    # Multi-period S/R (htf_sr) + Market context (index_open_strength) CUT 2026-06-23 —
    # orphans, no bound pine emits them. → OBSOLETE_ALERT_TYPES.

    # SWING book (2026-06-13) — daily-close momentum/RSI triggers from the Momentum
    # Pine. These are SWING trades (multi-day holds, lower-risk R:R), a separate
    # book from the intraday day-trade entries above — and they BYPASS the
    # SPY-vs-PDL gate (a day-trade protection; see SWING_ALERT_TYPES in tv_webhook).
    # Fire INTRADAY the moment the daily setup forms (#234 removed the 16:00 EOD
    # gate), ≤ once/day each. rsi_70 = bullish (daily RSI above 70 can start a
    # parabola), rsi_oversold = first time the daily RSI enters the 30-35 buy zone
    # (reclaim 30 or hold — NEVER below 30), ema_5_20_cross = Steve Burns 5/20.
    # rsi_70 RETIRED 2026-07-18 (user: "pointless for entry") → OBSOLETE below.
    ("ema_5_20_cross", "5/20 EMA bullish cross (Steve Burns)", "Swing", False),
    ("swing_rsi_30", "RSI 30 reclaim — daily RSI crossed back ABOVE 30 from oversold (the turn is in; longer-hold bottom)", "Swing", False),
    # swing_reclaim.pine (2026-07-30) — the validated HOLD-200/RSI-30 long-hold entry. SMA-only,
    # long-only reclaims (close back above a level after dipping below). Bind the pine on Daily.
    ("swing_sma200_reclaim", "200 SMA reclaim (long) — a daily close recovered/held the 200 SMA (the line institutions defend). Long-hold accumulation. Bind on Daily; opt in HERE.", "Swing", False),
    ("swing_8ema_w_reclaim", "8 EMA (weekly) reclaim (long) — the week opened above the WEEKLY 8 EMA (fast trend spine) and price reclaimed it — an early trend re-entry after a pullback. Bind swing_reclaim.pine; opt in HERE.", "Swing", False),
    ("swing_21ema_w_reclaim", "21 EMA (weekly) reclaim (long) — the week opened above the WEEKLY 21 EMA and price reclaimed it (Redler trend spine; replaces the noisy 50/100 SMA). Bind swing_reclaim.pine; opt in HERE.", "Swing", False),
    # FV basis + Smart Money zones — the SAME reclaim pattern on a non-MA line (2026-08-02).
    ("swing_30w_reclaim", "30-week MA reclaim/hold (long) — price is back above the 30-week MA (Weinstein Stage-2 re-entry; the weekly trend line). Long-hold. Bind swing_reclaim.pine; opt in HERE.", "Swing", False),
    # PQ reclaim (2026-07-17, re-landed 07-18 after the #820 rollback) — the daily close bounces the
    # prior-quarter LOW, reclaims the prior-quarter CLOSE, or breaks the HIGH. Low win% / high R:R
    # bottom-bounce & breakout swing. The level is named in the alert. From prior_quarter_hl.pine
    # (bind on the daily chart, MASTER watchlist). Delivery = MASTER_OPTIN_TYPES in tv_webhook:
    # broadcast to every user who enabled the toggle, regardless of personal watchlist.
    # Label MUST stay < 200 chars — a longer label aborts the whole startup seed (see #821).
    # pq_reclaim + monthly_low_swing REMOVED 2026-08-02 (user: "retire pq, monthly low swing").
    # The weekly_rc / monthly_rc low-reclaims (above, now Swing) cover the level-reclaim swings;
    # the 33-SMA fair-value reclaim (swing_fv_reclaim) is coming to replace the trend-hold. → OBSOLETE.
    # monthly_ma_reclaim ("monthly m8") RETIRED 2026-07-14 (user: "mostly false and bad") → OBSOLETE below.
    # character_change / base_buy / new_high_breakout / fv_pullback / fv_reclaim RETIRED 2026-07-18
    # (user: "remove — we dont need them") → OBSOLETE below. The swing book is the two-control set:
    # weekly_30w_held + pq_reclaim + ma200_bounce + ema_5_20_cross.

    # Index SHORTs (spec 61, 2026-06-06) — SPY/QQQ/IWM only, via the SPY-short
    # routing whitelist. Trade WITH the breakdown: PDL break / PDH rejection on
    # heavy volume. Default OFF — record + watch the count before delivering.
    # The ONLY two shorts (user 2026-07-22: "for short — only two short conditions: PDH rejection,
    # PDL break. that's all."). pdh_fail_short + all MA/level rejection shorts retired → OBSOLETE.

    # 4h reclaim — long-only now (rc_4h_short RETIRED 2026-06-29 → OBSOLETE; the only
    # shorts we keep are the structural PDL break + PDH rejection). Both default OFF.
    # rc_4h_hrec (4h HIGH reclaim) RETIRED 2026-07-12 — chases resistance; only the 4h LOW (rc_4h_long) is kept. → OBSOLETE.
    # Daily RC (from rc.pine) — undercut & reclaim of the prior-DAY low/high (≈ PDL/PDH
    # reclaim, RC-model). All default OFF.
    # rc_daily_long / rc_daily_hrec RETIRED 2026-07-22 → merged into pdl_held / pdh_held (one PDL +
    # one PDH alert, wick-below-and-reclaim, consistent with WLV/MLV/PQ/MA). → OBSOLETE_ALERT_TYPES.

    # ORB (2026-07-08) — the 15m family (orb_break/held/retest/exit) is RETIRED
    # (user: "there should be no orb in 15mins" — too noisy even allowlist-gated;
    # the machine is deleted from rc.pine). → OBSOLETE below. The ONE ORB alert
    # is the 1h reclaim: clean, low-noise, once per session, allowlist-gated.
    # ORB · 1h family (orb_reclaim_low/high + orb_high/low_held) RETIRED 2026-07-18
    # (user: "remove all orb alerts in settings") → OBSOLETE below. day_trade.pine still
    # computes/emits them; fires drop at the global gate.

    # Index reclaim long (#65) RETIRED 2026-07-03 → OBSOLETE. Superseded by the new ORB
    # family (orb_held / orb_retest cover the ORH/PDH reclaim, across all rails) — removed
    # so it doesn't double-fire during the ORB evaluation.

    # Weekly RC — Issue #3 (2026-06-13). The only actionable piece of the old
    # WkStage family: undercut & reclaim of the prior-week low on a GREEN week
    # (stop = the weekly low). The generic BUY/ADD/EXIT/stage NOTICEs were
    # unclear/not-actionable and are SUPPRESSED (weekly_stage → OBSOLETE).
    # WLV — Weekly LEVELS · directional reclaim (spec 69, 2026-07-12). THE single weekly
    # alert: H/L/O/C of the last 4 weeks (16 levels), directional support reclaim. weekly_rc
    # + PWL-held folded in → OBSOLETE. The weekly 10w/30w MA stays separate (trend tool).
    # WLV/MLV reject — the bearish mirror (rc.pine, 2026-07-13). Price rallied UP into a weekly/monthly
    # H/L level from below and closed back under it = failed breakout / resistance held → SHORT, stop the
    # poke high. Fired by the same one-toggle level engine as the reclaim/held/break BUYs. day_trade.
    # weekly_lvl_reject REMOVED 2026-07-22 (user: shorts except PDH rejection) → OBSOLETE_ALERT_TYPES.
    # 10w/30w weekly-MA support (rc.pine). Now fires INTRADAY once-per-TOUCH (tag & hold
    # the locked weekly MA, re-arm on leave) — not once per week (#2026-06-29). The
    # _reclaim variants RETIRED → OBSOLETE; the single _held touch covers tag-and-hold +
    # a shallow undercut-reclaim. Both default OFF.
    # weekly_30w_held REMOVED 2026-08-02 (user: "all these held alerts don't work well — remove").
    # Long-term bucket retired; two buckets only (Day + Swing). → OBSOLETE_ALERT_TYPES.
    # MLV — Monthly LEVELS · directional reclaim (spec 68, 2026-07-11). THE single monthly
    # alert: EVERY completed monthly level — H/L/O/C of the last 6 months (24 levels). BUY when
    # the day opened ABOVE the level and price wicked below & reclaimed it (support held);
    # optional reclaim-from-below. Entry = the level, stop = the reclaim low. Fired from rc.pine,
    # once per level per day, day-trade. monthly_rc + pml_held + CML are FOLDED IN (retired →
    # OBSOLETE_ALERT_TYPES); MLV is the only monthly toggle.
    # monthly_lvl_reject REMOVED 2026-07-22 (user: shorts except PDH rejection) → OBSOLETE_ALERT_TYPES.
    # MoBO — monthly BOX breakout + monthly RC-H (rc.pine, 2026-06-28). The long-term
    # "next MU/SNDK off a base" engine: a locked flat multi-month Darvas ceiling clearing
    # (monthly_box), or a break of a prior MONTHLY swing high that held as resistance for
    # months (mobo_rch, the high-side complement to monthly_rc, catches stair-step leaders
    # the box can't see). Monthly LEVEL, daily/intraday TRIGGER (price crossing it). Both
    # BUY, gate-exempt (position), default OFF.
    # monthly_box + mobo_rch REMOVED 2026-08-02 (user: "never seen anything from them for a week —
    # don't think they work"). Long-term bucket retired. → OBSOLETE_ALERT_TYPES.
    # weekly_ma_held/reclaim/wick_reclaim CUT 2026-06-23 — NOT in the agreed set and
    # NOT wired (no pine emits them). → OBSOLETE. (Re-wire into rc.pine later if wanted.)
    # weekly_rc2 REMOVED 2026-06-13 — too complicated, some fires didn't hold up.
    # Pulled from the Pine + alert + catalog (now in OBSOLETE_ALERT_TYPES).

    # Notice (gap_zone) RETIRED 2026-06-09 — structural-levels focus. Context,
    # not entries; still drawn on the visual indicators. Moved to
    # OBSOLETE_ALERT_TYPES below (backend drops it).

    # Swing scanner — REMOVED from Settings 2026-06-01 per founder request.
    # Swing scanner not currently working reliably; types listed in
    # OBSOLETE_ALERT_TYPES below for DB cleanup.
]

# Per-MA toggles for the surviving MA-bounce family.
_MA_CATALOG: list[tuple[str, str, str, bool]] = [
    (f"{fam}_{suffix}", f"{flabel} · {malabel}", fcat, False)
    for fam, flabel, fcat in MA_SPLIT_FAMILIES
    for suffix, malabel in _MA_TOGGLES
]

ALERT_TYPE_CATALOG: list[tuple[str, str, str, bool]] = _BASE_CATALOG + _MA_CATALOG


# ── Trade-STYLE classification (day_trade / swing / long_term) ───────
# Every alert is filed in its style FEED (the in-app panels) regardless of whether
# delivery (Telegram/push) is enabled — tracking and delivery are separate. Derived
# from the catalog category, with prefix/MA-depth overrides for the ambiguous ones.
_CATEGORY_BY_KEY: dict[str, str] = {k: c for k, _l, c, _d in ALERT_TYPE_CATALOG}
_STYLE_BY_CATEGORY: dict[str, str] = {
    "Monthly trend": "long_term", "Monthly": "long_term",
    "Weekly trend": "long_term", "Weekly": "long_term",
    "Swing": "swing",
}
# Checked before the category map (most reliable). (prefix, style).
_STYLE_BY_PREFIX: list[tuple[str, str]] = [
    # RC VALIDATION (2026-07-23) — daily/weekly/monthly UNDERCUT-and-reclaim, their OWN feed panel.
    # Listed FIRST so daily_rc/weekly_rc/monthly_rc win over the broad monthly_/weekly_/staged_ rows.
    # 2026-08-02 — two feeds only (Day + Swing). weekly_rc/monthly_rc = SWING bottom-bounces;
    # the 4H method IS the day trade, so fourh_* → day_trade feed (no separate RC / 4H tab).
    ("staged_pwl", "day_trade"),   # weekly_rc/monthly_rc retired 2026-08-02 (→ Smart Money zones)
    ("fourh_reclaim", "day_trade"), ("fourh_reject", "day_trade"), ("fourh_breakup", "day_trade"), ("fourh_breakdn", "day_trade"),
    ("day_weekly_reclaim", "day_trade"), ("day_monthly_reclaim", "day_trade"), ("day_pdlow_reclaim", "day_trade"),   # structural day reclaims → Day feed
    ("gap_and_go", "day_trade"),   # gap-and-go momentum long → Day Trade feed
    ("monthly_lvl", "day_trade"),      # MLV — a monthly-LEVEL reclaim is a day-trade tool, not a hold-for-days swing (user 2026-07-09)
    ("weekly_lvl", "day_trade"),       # WLV — same, a weekly-LEVEL reclaim day-trade tool (user 2026-07-12)
    ("monthly_ma_reclaim", "swing"),   # a trend-MA reclaim = swing, not the day-trade monthly_rc
    ("monthly_", "long_term"), ("mobo_", "long_term"), ("cml_", "long_term"),
    ("pml_", "long_term"), ("weekly_10w", "long_term"), ("weekly_30w", "long_term"),
    ("staged_pml", "long_term"),
    ("swing_", "swing"), ("rsi_oversold", "swing"),
    ("rsi_70", "swing"), ("ema_5_20", "swing"),
    ("fv_", "swing"),                  # Fair Value Swing (fv_pullback / fv_reclaim) — weekly pullback/reclaim
]


def style_for(alert_type: str) -> str:
    """day_trade | swing | long_term — which feed panel an alert belongs to."""
    at = (alert_type or "").replace("tv_", "").lower()
    # MA bounce/rejection: deep MAs (100/200) = long-term support; fast (8/21/50) = day-trade.
    if "ma_bounce" in at or "ma_rejection" in at:
        # ONLY the 200 EMA/SMA reclaim is a swing (major moving support, held for days);
        # 8/21/50/100 bounces are DAY trades (user 2026-07-15, revises the 2026-07-07 all-day-trade call).
        if "ema200" in at or "sma200" in at:
            return "swing"
        return "day_trade"
    for prefix, style in _STYLE_BY_PREFIX:
        if at.startswith(prefix):
            return style
    return _STYLE_BY_CATEGORY.get(_CATEGORY_BY_KEY.get(at, ""), "day_trade")


# ── Plain-English explanation per alert type ────────────────────────
# One sentence each, written for a NEW user who doesn't know PDH / AVWAP /
# Buy-2 jargon. Tooltipped on the Weekly + By Pattern tables and shown as
# a subline on every Signal Feed card. Keep them factual ("stock did X")
# rather than promotional ("strong setup!") so users learn the actual
# mechanics of each pattern.
ALERT_TYPE_DESCRIPTIONS: dict[str, str] = {
    # MA bounce — per moving average. Tightest to widest support.
    "ma_bounce_long_v3_ema8":   "Intraday price pulled back to the 8 EMA in an uptrend and bounced — tightest trend support.",
    "ma_bounce_long_v3_ema21":  "Intraday price pulled back to the 21 EMA in an uptrend and bounced — short trend support.",
    "ma_bounce_long_v3_ema50":  "Intraday price pulled back to the 50 EMA in an uptrend and bounced — mid trend support.",
    "ma_bounce_long_v3_ema100": "Intraday price pulled back to the 100 EMA in an uptrend and bounced — wider trend support.",
    "ma_bounce_long_v3_ema200": "Intraday price pulled back to the 200 EMA in an uptrend and bounced — major trend support.",
    "ma_bounce_long_v3_sma":    "Intraday price pulled back to a major SMA (50/100/200) and bounced — institutional level support.",

    # MA rejection short — the mirror: an MA acting as resistance from below.
    "ma_rejection_short_v3_ema8":   "Price rallied up into the 8 EMA from below, tagged it and closed back below on a red bar — rejected at tightest trend resistance.",
    "ma_rejection_short_v3_ema21":  "Price rallied up into the 21 EMA from below and closed back below on a red bar — rejected at short trend resistance.",
    "ma_rejection_short_v3_ema50":  "Price rallied up into the 50 EMA from below and closed back below on a red bar — rejected at mid trend resistance.",
    "ma_rejection_short_v3_ema100": "Price rallied up into the 100 EMA from below and closed back below on a red bar — rejected at wider trend resistance.",
    "ma_rejection_short_v3_ema200": "Price rallied up into the 200 EMA from below and closed back below on a red bar — rejected at major trend resistance.",
    "ma_rejection_short_v3_sma":    "Price rallied up into a major SMA (50/100/200) from below and closed back below on a red bar — rejected at institutional resistance.",

    # Held-as-support — prior high acted as a floor after price reclaimed it.
    "staged_pdh_held": "Stock pulled back to yesterday's high and bounced — yesterday's resistance is now acting as support.",
    "staged_pwh_held": "Stock pulled back to last week's high and bounced — weekly resistance flipped to support.",

    # Wick-rejected breakdown of a prior low.
    "staged_pdl_held": "Stock dipped below yesterday's low briefly then closed back above — wick-rejected breakdown.",
    "staged_pwl_held": "Stock dipped below last week's low briefly then closed back above — wick-rejected weekly breakdown.",

    # Proximity bounce — level held as support without actually touching.
    "staged_pdl_proximity": "Stock pulled back near yesterday's low without touching it, then closed green — buyers stepped in before the level was tested.",
    "staged_pwl_proximity": "Stock pulled back near last week's low without touching it, then closed green — weekly support defended without a test.",
    "staged_pdh_proximity": "Stock is holding above yesterday's high and pulled back near it without retesting — prior-day high defended as support from above (relative strength).",
    "pullback_long": "In an established uptrend, price pulled back and resumed higher (Buy 1) — a continuation entry on the dip, not a breakout chase.",

    # Reclaim — lost a prior low then recovered it on a bullish bar.
    "staged_pdl_reclaim": "Stock lost yesterday's low then recovered it on a bullish bar — failed breakdown long.",
    "staged_pwl_reclaim": "Stock lost last week's low then recovered it on a bullish bar — failed weekly breakdown long.",

    # Reclaim — gap above a prior high, lost it briefly, reclaimed on a bullish bar.
    "staged_pdh_reclaim": "Stock gapped above yesterday's high, dipped back below it, then reclaimed it on a bullish bar — continuation long after the retest.",
    "staged_pwh_reclaim": "Stock gapped above last week's high, dipped back below it, then reclaimed it on a bullish bar — weekly-level continuation.",

    # Spec 60 breakouts — vol + slope confluence.
    "staged_pdh_break":         "Stock broke above yesterday's high with above-average volume and rising VWAP — confirmed continuation.",
    "staged_pwh_break":         "Stock broke above last week's high with above-average volume and rising VWAP — weekly breakout.",
    "gap_up_continuation_long": "Stock opened above yesterday's high and held it as support — gap-up continuation.",
    "gap_support": "Price opened ABOVE an unfilled gap, pulled back to its top edge and held — the untraded void is acting as support. BUY the bounce; stop below the gap's bottom edge.",
    "gap_fill": "Price closed UP into an unfilled gap from below — a gap has no supply inside, so it tends to fill fast to the far edge. BUY the fill; target = the top edge, stop back below the gap.",
    "gap_reject": "Price opened BELOW an overhead gap, rallied to its near edge and closed back under — the gap resistance held. SHORT the rejection; stop above the gap's top edge.",
    "lost_support_reject": "A prior support (PDL/PWL/PML) that price has LOST — closed below and is now trading under it — flips to resistance. Price wicks back up INTO the level and closes below it on a red bar = rejection. SHORT; stop above the level. The same dual-role the EMAs already use, applied to levels.",
    "htf_sr_reject": "A price where MULTIPLE weeks (or months) topped out — clustered higher-timeframe highs = institutional resistance. Price wicked up into the cluster and closed back below = rejection. SHORT; stop above the level. The note says how many periods touched it (more = stronger).",
    "htf_sr_bounce": "A price where MULTIPLE weeks (or months) bottomed — clustered higher-timeframe lows = institutional support. Price wicked down into the cluster and closed back above = hold. LONG; stop below the level. The note says how many periods touched it (more = stronger).",
    "index_open_strength": "A tracked symbol (default SPY/QQQ/DRAM, editable in the indicator) reclaimed today's open and is holding above it (two closes) — strength, trend intact.",
    "staged_pdl_break": "Index (SPY/QQQ/IWM/BTC) closed below yesterday's low on heavy volume — confirmed breakdown, short with the trend; stop just above the broken level.",
    "staged_pdh_rejection": "Index (SPY/QQQ/IWM/BTC) rallied into yesterday's high and was rejected (closed back below) on volume — failed breakout / resistance held; short, stop above the high.",
    "pdh_fail_short": "Allowlisted name (SPY-style) ACCEPTED above the prior-day high — closed above it earlier in the session — then LOST it, closing back below. Short the loss bar; STOP = a PDH reclaim (close back above). The failed-breakout fade SPY did 2026-06-22. Distinct from PDH rejection, which never accepted above the level. Fires once/session, allowlist only.",
    "gap_zone": "Price entered (testing) or filled an unfilled gap on SPY/NBIS (from the Gaps indicator) — a green gap below is support, a red gap above is resistance; entering = watch for bounce/reject, filled = the void is closed. Informational, not a trade trigger.",
    "weekly_stage": "Weekly long-term signal from the WkStage indicator (set on the weekly chart): RC (undercut & reclaim bottoming), BUY (close above a rising 30-week MA), ADD (pullback to the rising MA), or EXIT (weekly close below the trailing stop). Each carries the entry + structural stop. For the long-term/swing book — size off the stop.",
    "weekly_ma_pullback": "Weekly position entry from the WkPos indicator: in a Stage-2 uptrend (price above a RISING 30-week MA, 10w > 30w), the week dipped to the rising 10-week MA and closed back GREEN above it — buy the pullback in an established trend. STOP = the pullback week's low (trend invalidates on a weekly close below the 30wMA). TARGET = weekly RSI 70. Fires once at the weekly close.",
    "rsi_70": "Daily RSI(14) closed above 70 — momentum/exhaustion gauge at the bullish extreme. A close above 70 often kicks off a parabolic run (e.g. MU → 85 RSI). Fired at the daily close (confirmed, towards EOD), at most once a day. A heads-up to look, not a defended entry; no structural stop of its own.",
    "ema_5_20_cross": "The daily 5 EMA just crossed above the 20 EMA (Steve Burns's 5/20 cross) — a short-term trend flip that frequently starts a sustained up-move. A SWING entry (hold days). Fired at the daily close. STOP = a 5/20 EMA cross-under at the close (≈ the 20 EMA). TARGET = the 70-RSI. (Burns went long AIQ/VGT/QQQ on this exact signal Fri 06-12.)",
    "swing_8ema_w_reclaim": "The WEEK opened above the weekly 8 EMA (the fast trend spine) and price reclaimed it — an early trend re-entry after a pullback (fires a bit more than the 21 EMA-W but still weekly-gated). Long swing entry; stop = a weekly close back below / the swept low.",
    "swing_21ema_w_reclaim": "The WEEK opened above the weekly 21 EMA (it was support) and price reclaimed it — the higher-timeframe trend spine held. Replaces the noisy daily 50/100 SMA reclaims. Long swing entry; stop = a weekly close back below / the swept low.",
    "swing_rsi_30": "Daily RSI crossed back ABOVE 30 from below (was oversold yesterday, reclaimed 30 today) on an upper-half close — the bottom-fishing 'turn is in' confirmation. Higher conviction near the 200 SMA/EMA. A longer-hold reversal entry on washed-out quality/mega caps. Manage by RSI: T1 ~RSI 45-50, T2 RSI 70; STOP = a close back under 30. Pairs with rsi_oversold (the watch) — this is the trigger.",
    "swing_fv_reclaim": "Price closed back ABOVE the Fair-Value basis (33-SMA of weekly OHLC4) after dipping below — the key value level held as support (the reclaim is the best FV signal: continuation / stay-in-trend). Same reclaim + role-guard as the SMAs; STOP = the swept low, invalid on a close back below the basis.",
    "swing_smz_reclaim": "Price reclaimed a Smart-Money zone edge — a golden-pocket fib line (0.618 / 0.786 / 0.85) of the recent weekly swing that was acting as SUPPORT: price wicked below it and closed back above (the discount zone held). The alert names which edge (Institutional / Smart-Money). STOP = the swept low; invalid on a close back below the zone.",
    "rsi_oversold": "Daily RSI closed in the 30-35 buy zone — reclaimed 30 from below or dipped/holding in 30-35 from above. NEVER fires below 30 (the falling knife — RSI 29 is not a buy; wait for the turn/hold). A SWING entry (hold days), best on washed-out quality/mega caps that mean-revert. Manage by RSI: T1 = RSI 50, T2 = RSI 70; STOP = a daily close back under RSI 30 (exactly where Steve Burns stopped out of NFLX, -2.75%, Fri 06-12). Fired at the daily close, once per entry (rare).",
    "rc_4h_long": "4h RC long: price wicked BELOW the prior 4h low then closed back above it — swept-low bounce / reversal long. Stop = the wick low. A heads-up — eyeball the 4h, not every one is an entry.",
    "rc_4h_hrec": "4h RC-H: price dipped below the prior 4h HIGH then closed back above it — the broken high held as support = breakout-retest continuation long. Stop = the retest low.",
    "rc_4h_short": "4h RC short: price wicked ABOVE the prior 4h high then closed back below it — failed break / rejection (index-leaning). Stop = the wick high.",
    "reclaim_long": "Index reclaim long (SPY/QQQ/DRAM, 15m): in the morning, price was ABOVE the opening-range high or the prior-day high, dipped ~0.18% under it (shakeout), and RECLAIMED it — WITH room to the next resistance (no buying into a ceiling). ENTRY = the reclaim close · STOP = the dip low · TARGET = take profit INTO the next resistance (sell the whole position there). Long-only — the short mirror has no backtested edge.",
    "pdl_held": "The ONE prior-day LOW alert. Price wicked to/below the PDL and closed back above it — a reclaim (undercut & reclaimed) OR a support-hold (dipped to it & held), same event, open-agnostic. Entry = the level, stop below the PDL. Once per touch per day. (Merges the old PDL held + rc_daily_long.)",
    "pdh_held": "The ONE prior-day HIGH alert. Price wicked to/below the PDH and closed back above it — a reclaim OR a retest-hold after breaking it, same event, open-agnostic. Entry = the level, stop below the PDH. Once per touch per day. (Merges the old PDH held + rc_daily_hrec.)",
    "weekly_rc": "Weekly RC: price undercut the prior-WEEK high or low then reclaimed it intraday — the broken weekly level held (RC-H = breakout-retest continuation above the prior-week high; RC = undercut & reclaim of the prior-week low). A SWING heads-up. Stop = the week's swept low. Rare — eyeball the weekly.",
    "monthly_rc": "Monthly RC: price undercut the prior-MONTH high or low then reclaimed it intraday — the broken monthly level held (RC-H = breakout-retest continuation above the prior-month high, the MU play; RC = undercut & reclaim of the prior-month low). A POSITION heads-up. Stop = the month's swept low. Very rare — a major level reclaim, eyeball the monthly.",
    "fourh_reclaim": "4H reclaim: a 15m candle undercut one of the last two 4h candles' levels and closed back above — support held, momentum flips up. Entry = the 15m close, stop = the swept wick. Bind the pine on 15m.",
    "fourh_reject": "4H rejection: a 15m candle poked above a prior 4h level and closed back below — resistance held, momentum flips down. Entry = the close, stop = the swept wick.",
    "fourh_breakup": "4H break-up: a 15m candle closed up through a prior 4h level — continuation. Entry = the close, stop back below the level.",
    "fourh_breakdn": "4H break-down: a 15m candle closed down through a prior 4h level — continuation. Entry = the close, stop back above the level.",
    "day_weekly_reclaim": "Weekly-low reclaim (day trade): a 15m candle undercut the prior-WEEK low (PWL) and closed back above — the weekly support held. Entry = the 15m close, stop = the swept bar low. Shares the 4H day dedup, so only the LOWEST entry of the day fires.",
    "day_monthly_reclaim": "Monthly-low reclaim (day trade): a 15m candle undercut the prior-MONTH low (PML) and closed back above — the monthly support held. Entry = the close, stop = the swept bar low. Shares the 4H day dedup (lowest entry wins).",
    "day_pdlow_reclaim": "Prior-day low reclaim (day trade): a 15m candle undercut one of the last two sessions' lows (D-1 or D-2) and closed back above. Entry = the close, stop = the swept bar low. Shares the 4H day dedup (lowest entry wins).",
    "monthly_lvl_reclaim": "The ONE prior-month level alert. Fires a BUY on the PRIOR month's High or Low (PMH/PML) two ways: (1) RECLAIM — price traded below the level today and closed back above it (open-agnostic: dip-and-reclaim OR ran up through from below), or (2) GAP-and-go — the day opened above the level after the prior day closed under it, and held above. Entry = the level, stop = the day low. Once per level per day, day-trade. Pairs with the prior-month visual pine (monthly_levels.pine).",
    "weekly_lvl_reclaim": "The ONE prior-week level alert. Fires a BUY on the PRIOR week's High or Low (PWH/PWL) two ways: (1) RECLAIM — price traded below the level today and closed back above it (open-agnostic), or (2) GAP-and-go — the day opened above the level after the prior day closed under it, and held above. Entry = the level, stop = the day low. Once per level per day, day-trade. Pairs with the prior-week visual pine (weekly_levels.pine).",

    # Swing scanner — REMOVED 2026-06-01. See OBSOLETE_ALERT_TYPES.
}


def describe_alert_type(alert_type: str) -> str:
    """Returns the plain-English description for an alert type, or empty
    string if unknown. UI surfaces the empty case as no tooltip / no subline.
    """
    return ALERT_TYPE_DESCRIPTIONS.get(alert_type, "")


# ── Cleanup — every retired/obsoleted alert type ────────────────────────
# These types are DELETED from the alert_type_config table on every startup
# (see seed_alert_type_config below). Soft-disable was tried first but the
# user wanted them GONE from the Settings UI dropdown, not just hidden.
#
# Historical alerts in the `alerts` table that reference these types stay
# intact — alert_type is just a String column with no FK, so deleting from
# the catalog doesn't orphan anything. The EOD scorecard can still surface
# historical alerts by name; they just won't have a toggle anymore.
OBSOLETE_ALERT_TYPES: tuple[str, ...] = (
    # 2026-08-05 — swing book condensed to 21EMA-W + 200SMA + 30W + RSI30 + 5/20 (user: 50/100 SMA too
    # noisy/intraday, mostly run into resistance). 50/100 reclaims + ALL breakup/hold ALERTS retired
    # (SMA lines stay VISUAL in swing_reclaim.pine for manual day-trading).
    "swing_sma50_reclaim", "swing_sma100_reclaim", "swing_sma50_breakup", "swing_sma100_breakup",
    "swing_sma200_breakup", "swing_sma50_hold", "swing_sma100_hold", "swing_sma200_hold",
    # 2026-08-05 — user: removed FV basis + Smart-Money zones from swing_reclaim.pine (visual + alerts).
    "swing_fv_reclaim", "swing_smz_reclaim",
    # 2026-08-02b — RC retired (user: "replace the rc with reclaims of smart money zone"). weekly_rc +
    # monthly_rc removed; replaced by swing_fv_reclaim + swing_smz_reclaim (the golden-pocket zones).
    "weekly_rc", "monthly_rc",
    # 2026-08-02 — Settings cleanup to TWO buckets (Day + Swing). Day = 4H RC + gap_and_go;
    # Swing = SMA 50/100/200 reclaim + swing_rsi_30 + ema_5_20_cross + FV + Smart Money zones.
    # Removed: the daily PDH/PDL reclaims (4H covers them), the whole MA-bounce family, the dup gap,
    # daily_rc, pq/monthly_low_swing, and the retired Long-term "held" set (weekly_30w/monthly_box/mobo_rch).
    "staged_pdh_break", "pdh_held", "pdl_held", "gap_up_continuation_long", "daily_rc",
    "pq_reclaim", "monthly_low_swing", "weekly_30w_held", "monthly_box", "mobo_rch",
    "ma_bounce_long_v3_ema8", "ma_bounce_long_v3_ema21", "ma_bounce_long_v3_ema50",
    "ma_bounce_long_v3_ema100", "ma_bounce_long_v3_ema200",
    "ma_bounce_long_v3_sma20", "ma_bounce_long_v3_sma50", "ma_bounce_long_v3_sma100", "ma_bounce_long_v3_sma200",
    # 2026-07-30 — Settings cleanup (user): Day = 4H RC (reclaim/reject/breakup/breakdn) + gap_and_go
    # ONLY. No EMA reactions, no separate PDH/PDL/staged/pullback alerts (confluence is TAGGED on the
    # 4H levels). 200-reclaim dedup -> kept swing_sma200_reclaim. rc_4h_long -> fourh_reclaim.
    "pullback_long", "rsi_oversold", "staged_pdl_break", "staged_pdh_rejection", "rc_4h_long", "weekly_lvl_reclaim", "weekly_10w_held", "monthly_lvl_reclaim", "fourh_ma200_reclaim", "ma200_bounce", "fourh_ema_reclaim", "fourh_ema_reject", "fourh_ema_breakup", "fourh_ema_breakdn",
    # 2026-07-18 — swing-book trim (user: "remove — we dont need them"). The swing set is now
    # exactly weekly_30w_held / pq_reclaim / ma200_bounce / ema_5_20_cross; these five are cut.
    # (swing_scan.py may still emit base_buy/character_change — those fires now drop at the
    # global gate as type_not_enabled, which is the intent.)
    "character_change", "base_buy", "new_high_breakout", "fv_pullback", "fv_reclaim",
    # 2026-07-18 — the whole ORB · 1h family retired too (user: "remove all orb alerts in settings").
    "orb_reclaim_low", "orb_reclaim_high", "orb_high_held", "orb_low_held",
    # 2026-07-18 — rsi_70 retired (user: "pointless for entry" — RSI>70 confirms momentum, doesn't time one).
    "rsi_70",
    # 2026-07-18 — WLV/MLV rejects briefly retired, then REVIVED same day as the short book:
    # rejection AT resistance (day opened BELOW the level, price tagged it within lvlTol, closed
    # back below). Index allowlist only. See the catalog entries.
    # 2026-07-08 — the 15m ORB family RETIRED (user: "there should be no orb in 15mins").
    # The state machine is deleted from rc.pine; the 1h orb_reclaim is the one ORB alert.
    "orb_break", "orb_held", "orb_retest", "orb_exit",
    # 2026-07-14 — the combined orb_reclaim SPLIT into orb_reclaim_low / orb_reclaim_high (the side
    # matters: low reclaim = better risk). Retire the merged one so Settings shows the two.
    "orb_reclaim",
    # 2026-07-14 — monthly_ma_reclaim ("monthly m8") retired: mostly false/bad (user). Monthly
    # BREAKOUT (monthly_box/MoBO) stays; only the monthly-MA reclaim is dropped.
    "monthly_ma_reclaim",
    # 2026-07-03 — ORL/ORH opening-range types + current-month-low (CML) RETIRED. Index
    # reclaim (reclaim_long) RETIRED 2026-07-03 too — superseded by the new ORB family
    # (orb_held/orb_retest), removed to avoid double-firing during the ORB eval. Startup
    # purges stale rows; webhook drops arrivals.
    "orh_break", "staged_orl_held", "cml_reclaim", "cml_held", "reclaim_long",
    # 2026-07-11 — ALL monthly sub-alerts folded into MLV (monthly_lvl_reclaim, spec 68).
    # MLV now covers every completed monthly level (H/L/O/C × 6 months incl. month[1]), so the
    # prior-month RC + PML-held are redundant. MLV is the one monthly toggle.
    # monthly_rc / weekly_rc REVIVED 2026-07-23 as the RC-validation types (in _BASE_CATALOG above,
    # style "rc") — REMOVED from obsolete so the seed no longer deletes them right after inserting.
    "pml_held", "staged_pml_held",
    # 2026-07-12 — weekly sub-alerts folded into WLV (weekly_lvl_reclaim, spec 69). WLV
    # covers every completed weekly level (H/L/O/C × 4 weeks), so PWL-held retires.
    "staged_pwl_held",
    # rc_4h_hrec RETIRED 2026-07-12 — the 4h HIGH reclaim chases resistance (buys into overhead).
    # Only rc_4h_long (4h LOW = support bounce) kept. Daily/weekly/monthly RC stay (directional-gated).
    "rc_4h_hrec",
    # rc_daily_long / rc_daily_hrec RETIRED 2026-07-22 — merged into pdl_held / pdh_held (one PDL +
    # one PDH alert, open-agnostic wick-below-and-reclaim, consistent with WLV/MLV/PQ/MA).
    "rc_daily_long", "rc_daily_hrec",
    # staged_pdl_held RETIRED 2026-07-12 — daily PDL held, redundant with the directional
    # daily RC (rc_daily_long). Daily twin of the staged_pwl_held retire.
    "staged_pdl_held",
    # rc_4h split into rc_4h_long/short/hrec (2026-06-22) — drop the old combined toggle
    "rc_4h",
    # rc_4h_short RETIRED 2026-06-29 — long-only 4h; the only shorts we keep are the
    # structural PDL break + PDH rejection (levels_day_vwap). No 4h/EMA rejection shorts.
    "rc_4h_short",
    # ma_rejection_short_v3 FAMILY REVIVED 2026-07-18 — only the bare prefix (never a real type)
    # and the old combined _sma toggle stay retired.
    "ma_rejection_short_v3",
    # weekly_10w/30w_reclaim RETIRED 2026-06-29 — the 10w/30w now fire once-per-TOUCH
    # intraday (the _held type covers tag-and-hold + shallow reclaim). No separate reclaim.
    "weekly_10w_reclaim", "weekly_30w_reclaim",

    # 2026-06-27 — the rc.pine OR-channel plays RETIRED (too noisy, especially ORL). The
    # original staged_orl_held (60m OR low, levels_day_vwap.pine) is REVIVED in their place
    # (back in _BASE_CATALOG above), scoped to the user-editable staged_orl_symbols allowlist.
    "orl_held", "orl_reclaim", "orh_reject",

    # 2026-06-23 SETTINGS CLEANUP — only the agreed RC + MA-bounce + levels_day set
    # stays. These orphans (no bound pine emits them) are retired so Settings shows
    # exactly what fires. weekly_ma can be re-wired into rc.pine later if wanted.
    "htf_sr_bounce", "htf_sr_reject", "multitouch_level", "index_open_strength",
    "weekly_ma_held", "weekly_ma_reclaim", "weekly_ma_wick_reclaim",

    # 2026-06-23 DECLUTTER — RC pine owns the reclaims; "high held"=resistance; gaps
    # mean nothing if they don't hold. Cut from levels_day's catalog; the webhook
    # OBSOLETE-drop guard makes them vanish (no feed, no Not-routed) even while the
    # pine still emits them pre-re-paste.
    "staged_pdh_held", "staged_pwh_held", "staged_pmh_held",
    "staged_pdl_reclaim", "staged_pwl_reclaim", "staged_pml_reclaim",
    "staged_pdh_reclaim", "staged_pwh_reclaim", "staged_pmh_reclaim",
    "gap_support", "gap_fill", "gap_reject",
    "lost_support_reject",

    # Bare prefixes (pre per-MA split)
    "ma_bounce_long_v3",
    "ma_proximity_long_v3",
    "ma_rejection_short_v3",

    # Open-line entries — retired spec 58 FR-007 (open line stays visual)
    "open_reclaimed", "open_held", "open_wick_reclaim", "open_lost",

    # staged_pdh_break RE-ENABLED 2026-06-18 (#291) — back in _BASE_CATALOG, default OFF
    # (high-volume PDH breakout the user asked for again). staged_pwh_break stays dropped.
    "staged_pwh_break",

    # Proximity bounce — DROPPED 2026-06-04 (spec 61). Entry = close landed
    # far from the level after the bounce ran (TSLA PDL 416 → alert at 423).
    "staged_pdl_proximity", "staged_pwl_proximity", "staged_pdh_proximity",

    # Rolling higher-low tracker — REMOVED 2026-06-05 (added 2026-06-04, spec 61).
    # (staged_orl_held REVIVED 2026-06-27 — back in _BASE_CATALOG, scoped to staged_orl_symbols.)
    "staged_higher_low_held",

    # SHORT alerts — ONLY the two structural index shorts kept (user 2026-07-22: "for short — only
    # two short conditions: PDH rejection, PDL break. that's all."). Everything else retired.
    "pdh_fail_short",
    "staged_pdh_failed_short",
    "staged_pwh_rejection", "staged_pwh_failed_short", "staged_pwl_break",
    "staged_pmh_rejection", "staged_pmh_failed_short", "staged_pml_break",
    # WLV/MLV rejection shorts REMOVED 2026-07-22 (user: shorts except PDH rejection)
    "weekly_lvl_reject", "monthly_lvl_reject",

    # MA/EMA rejection SHORT family REMOVED 2026-07-22 (user: "remove all ema/ma short from
    # settings, not needed"). All per-MA types retired so the seed deletes them from the catalog.
    "ma_rejection_short_v3_ema8", "ma_rejection_short_v3_ema21",
    "ma_rejection_short_v3_ema50", "ma_rejection_short_v3_ema100",
    "ma_rejection_short_v3_ema200",
    "ma_rejection_short_v3_sma20", "ma_rejection_short_v3_sma50",
    "ma_rejection_short_v3_sma100", "ma_rejection_short_v3_sma200",

    # MA proximity NOTICEs (long + short, per-MA) — Pine no longer emits
    "ma_proximity_long_v3_ema8", "ma_proximity_long_v3_ema21",
    "ma_proximity_long_v3_ema50", "ma_proximity_long_v3_ema100",
    "ma_proximity_long_v3_ema200", "ma_proximity_long_v3_sma",
    "ma_proximity_short_v3",
    "ma_proximity_short_v3_ema8", "ma_proximity_short_v3_ema21",
    "ma_proximity_short_v3_ema50", "ma_proximity_short_v3_ema100",
    "ma_proximity_short_v3_ema200", "ma_proximity_short_v3_sma",

    # ma_bounce_long_v3_ema100 RE-ADDED 2026-06-23 (deep-pullback support, rc.pine).
    # The combined SMA toggle stays retired (split into sma50/sma200).
    "ma_bounce_long_v3_sma",
    "ma_rejection_short_v3_sma",

    # HTF NOTICEs / superseded held — spec 58
    "htf_support_held",  # superseded by granular staged_p[dwm]h_held
    "htf_proximity",     # NOTICE — removed Pine, long-only

    # VWAP NOTICEs — Pine no longer emits
    "vwap_reclaim_long", "vwap_reject_short", "vwap_support_hold",

    # Spec 56 swing scanner — `swing_bounce_ema100`/`sma100` stay retired
    # (per-rule trim 2026-05-28). The rest were un-retired and re-added
    # to ALERT_TYPE_CATALOG with default-disabled for opt-in delivery.
    "swing_bounce_ema100", "swing_bounce_sma100",
    "swing_exit",

    # pullback_long — DEPRECATED 2026-05-30 per user feedback. v2 quality
    # gates suppressed 100/100 of the pullback fires in the May 29 CSV;
    # the rule has no level test and is structurally noisy. Replaced by
    # the staged_*_held family which always tests a level.
    "pullback_long",

    # Anchored-VWAP family REMOVED — too noisy. AVWAP stays drawn on chart as
    # visual reference only; no alerts emit.
    "staged_mtd_avwap_held", "staged_pm_avwap_held", "staged_p2m_avwap_held",
    # Monthly PMH/PML held + reclaim RE-ACTIVATED 2026-06-09 (now in _BASE_CATALOG
    # — structural focus). Only the monthly *break* stays retired here.
    "staged_pmh_break",

    # gap_zone retired (structural-levels focus). weekly_stage RETIRED 2026-06-13
    # (Issue #3 — unclear/not-actionable; only the reclaim survives as weekly_rc).
    "gap_zone",
    "weekly_stage",

    # weekly_rc2 REMOVED 2026-06-13 — too complicated, some fires didn't hold up.
    "weekly_rc2",
    # weekly_ma_pullback SPLIT 2026-06-20 → weekly_ma_held / _reclaim / _wick_reclaim
    "weekly_ma_pullback",

    # 2026-06-01 — Swing scanner alerts REMOVED from Settings per founder
    # request. Swing scanner not currently working reliably; types pulled
    # from catalog so they don't show up as dead toggles.
    "swing_bounce_ema21", "swing_bounce_ema50", "swing_bounce_sma50",
    "swing_bounce_ema200", "swing_bounce_sma200",
    "swing_8_21_cross", "swing_golden_cross_retest",
    "swing_52w_high_retest", "swing_5day_low_reclaim",
    # swing_rsi_30 REVIVED 2026-06-25 (back in _BASE_CATALOG) — the RSI-30 RECLAIM
    # (crossed back above 30 from oversold) fires from evaluate_swing_rules, the same
    # path that already produces rsi_oversold. The bottom-fishing "the turn is in" signal.
)


async def seed_alert_type_config(conn) -> None:
    """Idempotently sync the catalogue into the table.

    Inserts missing rows; refreshes label/category on existing rows. Deletes
    obsoleted keys so the Settings UI never shows dead toggles.

    EVERY supported (non-obsolete) type is seeded GLOBALLY ENABLED (2026-06-24).
    The global `enabled` flag is an ADMIN kill-switch, NOT the opt-in — the real,
    per-user gate is `user_alert_type_prefs` (default OFF, opt-in via Settings).
    Seeding global=True uniformly means a re-seed (a brand-new type, or an
    obsolete round-trip) can NEVER silently suppress a supported type the way
    monthly_rc was — it sat at the catalog's default-False and the global gate
    (checked before the per-user gate) dropped every fire as `type_not_enabled`.
    All alert types now behave the same: globally available, gated solely by the
    user's toggle. `default_enabled` in the catalog is kept for documentation but
    no longer drives the global flag. Existing rows are NOT downgraded (an admin
    who globally muted a type keeps that), so this only heals new/re-added rows.
    """
    for alert_type, label, category, _default_enabled in ALERT_TYPE_CATALOG:
        await conn.execute(
            text(
                "INSERT INTO alert_type_config (alert_type, label, category, enabled) "
                "VALUES (:at, :label, :cat, TRUE) "
                "ON CONFLICT (alert_type) DO UPDATE SET "
                "label = EXCLUDED.label, category = EXCLUDED.category"
            ),
            {"at": alert_type, "label": label, "cat": category},
        )
    for obsolete in OBSOLETE_ALERT_TYPES:
        await conn.execute(
            text("DELETE FROM alert_type_config WHERE alert_type = :at"),
            {"at": obsolete},
        )
