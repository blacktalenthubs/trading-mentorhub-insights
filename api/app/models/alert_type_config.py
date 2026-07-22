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
    ("ma_bounce_long_v3", "MA bounce long", "MA / EMA · Bounce Long"),
    # ma_rejection_short_v3 REVIVED 2026-07-18 (user: "a level above is resistance — a tag of the MA
    # from below that moves back below is a short; sometimes they don't wick, resistance is
    # resistance until price STAYS above"). Tag tolerance ma_tol (0.25%); whole watchlist (user:
    # "short should be users watchlists not limited to anything").
    ("ma_rejection_short_v3", "MA rejection SHORT", "MA / EMA · Rejection Short"),
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
    # Pullback continuation (uptrend-gated long entry — companion to MA bounce)
    ("pullback_long", "Uptrend pullback continuation (Buy 1)", "Pullback", False),

    # Prior-HIGH held CUT 2026-06-23 — "high held as support" = buying resistance;
    # RC pine owns the high reclaims (rc_*_hrec, uptrend-gated). → OBSOLETE_ALERT_TYPES.
    # PDH breakout on volume (#291) — close above PDH + volume_ratio>=2 + rising VWAP. KEPT.
    ("staged_pdh_break", "PDH break on volume", "Daily PDH/PDL", False),
    # PDH/PDL HELD (2026-07-14, user: "the held is the alert — a break can fade, a hold shows strength").
    ("pdh_held", "PDH held — broke the prior-day HIGH, retested & held it (strength continuation)", "Daily PDH/PDL", False),
    ("pdl_held", "PDL held — held above the prior-day LOW as support (dip to it & hold)", "Daily PDH/PDL", False),

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
    # is staged_pdh_held (retest of PDH as support). staged_pdh/pwh_break live
    # in OBSOLETE_ALERT_TYPES. Gap-up (open ABOVE PDH) KEPT — separate, valid.
    ("gap_up_continuation_long","Gap-and-go — opened above PDH, ran (stop = open low)", "Gap-and-go", False),

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
    ("rsi_oversold", "RSI oversold buy zone — daily RSI in 30-35 (reclaim/hold, never below 30)", "Swing", False),
    ("swing_rsi_30", "RSI 30 reclaim — daily RSI crossed back ABOVE 30 from oversold (the turn is in; longer-hold bottom)", "Swing", False),
    # PQ reclaim (2026-07-17, re-landed 07-18 after the #820 rollback) — the daily close bounces the
    # prior-quarter LOW, reclaims the prior-quarter CLOSE, or breaks the HIGH. Low win% / high R:R
    # bottom-bounce & breakout swing. The level is named in the alert. From prior_quarter_hl.pine
    # (bind on the daily chart, MASTER watchlist). Delivery = MASTER_OPTIN_TYPES in tv_webhook:
    # broadcast to every user who enabled the toggle, regardless of personal watchlist.
    # Label MUST stay < 200 chars — a longer label aborts the whole startup seed (see #821).
    ("pq_reclaim", "PQ reclaim (master universe) — quarterly-level bounce/reclaim/break on the BROAD master watchlist; opt in HERE to receive it regardless of your own watchlist (rare, high R:R; level named)", "Swing", True),
    # 200-MA bounce — the OTHER emit of swing_trade.pine (daily-close reclaim of the 200 EMA/SMA).
    ("ma200_bounce", "200-MA bounce — daily close reclaimed the 200 EMA/SMA (the institutional dip-buy zone; swing bottom)", "Swing", True),
    # monthly_ma_reclaim ("monthly m8") RETIRED 2026-07-14 (user: "mostly false and bad") → OBSOLETE below.
    # character_change / base_buy / new_high_breakout / fv_pullback / fv_reclaim RETIRED 2026-07-18
    # (user: "remove — we dont need them") → OBSOLETE below. The swing book is the two-control set:
    # weekly_30w_held + pq_reclaim + ma200_bounce + ema_5_20_cross.

    # Index SHORTs (spec 61, 2026-06-06) — SPY/QQQ/IWM only, via the SPY-short
    # routing whitelist. Trade WITH the breakdown: PDL break / PDH rejection on
    # heavy volume. Default OFF — record + watch the count before delivering.
    ("staged_pdl_break", "PDL break — lost the prior-day low on volume", "Short", False),
    ("staged_pdh_rejection", "PDH rejection — rejected at the prior-day high on volume", "Short", False),
    ("pdh_fail_short", "PDH failed break — accepted above PDH then lost it (short the loss, stop = PDH reclaim)", "Short", False),

    # 4h reclaim — long-only now (rc_4h_short RETIRED 2026-06-29 → OBSOLETE; the only
    # shorts we keep are the structural PDL break + PDH rejection). Both default OFF.
    ("rc_4h_long",  "4h RC long — reclaim of the prior 4h LOW (swept-low bounce, support-gated)", "4h reversal", False),
    # rc_4h_hrec (4h HIGH reclaim) RETIRED 2026-07-12 — chases resistance; only the 4h LOW (rc_4h_long) is kept. → OBSOLETE.
    # Daily RC (from rc.pine) — undercut & reclaim of the prior-DAY low/high (≈ PDL/PDH
    # reclaim, RC-model). All default OFF.
    ("rc_daily_long", "Daily RC — reclaim of the prior-DAY LOW / PDL (undercut & reclaim)", "Daily RC", False),
    ("rc_daily_hrec", "Daily RC-H — reclaim of the prior-DAY HIGH / PDH (breakout-retest)", "Daily RC", False),

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
    ("weekly_lvl_reclaim", "Prior-week level — RECLAIM or GAP-and-go above the PRIOR week's High/Low (PWH/PWL)", "Weekly", False),
    # WLV/MLV reject — the bearish mirror (rc.pine, 2026-07-13). Price rallied UP into a weekly/monthly
    # H/L level from below and closed back under it = failed breakout / resistance held → SHORT, stop the
    # poke high. Fired by the same one-toggle level engine as the reclaim/held/break BUYs. day_trade.
    ("weekly_lvl_reject", "Prior-week rejection SHORT — rallied into the PRIOR week's H/L from below (0.25% tag) and closed back under: resistance held", "Short", False),
    # 10w/30w weekly-MA support (rc.pine). Now fires INTRADAY once-per-TOUCH (tag & hold
    # the locked weekly MA, re-arm on leave) — not once per week (#2026-06-29). The
    # _reclaim variants RETIRED → OBSOLETE; the single _held touch covers tag-and-hold +
    # a shallow undercut-reclaim. Both default OFF.
    ("weekly_10w_held", "10w MA — tagged & held the 10-week MA intraday (position support)", "Weekly trend", False),
    ("weekly_30w_held", "30w MA — tagged & held the 30-week MA intraday (LONG-TERM support)", "Weekly trend", False),
    # MLV — Monthly LEVELS · directional reclaim (spec 68, 2026-07-11). THE single monthly
    # alert: EVERY completed monthly level — H/L/O/C of the last 6 months (24 levels). BUY when
    # the day opened ABOVE the level and price wicked below & reclaimed it (support held);
    # optional reclaim-from-below. Entry = the level, stop = the reclaim low. Fired from rc.pine,
    # once per level per day, day-trade. monthly_rc + pml_held + CML are FOLDED IN (retired →
    # OBSOLETE_ALERT_TYPES); MLV is the only monthly toggle.
    ("monthly_lvl_reclaim", "Prior-month level — RECLAIM or GAP-and-go above the PRIOR month's High/Low (PMH/PML)", "Monthly", False),
    ("monthly_lvl_reject", "Prior-month rejection SHORT — rallied into the PRIOR month's H/L from below (0.25% tag) and closed back under: resistance held", "Short", False),
    # MoBO — monthly BOX breakout + monthly RC-H (rc.pine, 2026-06-28). The long-term
    # "next MU/SNDK off a base" engine: a locked flat multi-month Darvas ceiling clearing
    # (monthly_box), or a break of a prior MONTHLY swing high that held as resistance for
    # months (mobo_rch, the high-side complement to monthly_rc, catches stair-step leaders
    # the box can't see). Monthly LEVEL, daily/intraday TRIGGER (price crossing it). Both
    # BUY, gate-exempt (position), default OFF.
    ("monthly_box", "MoBO box breakout — cleared the locked flat multi-month base ceiling (position)", "Monthly trend", False),
    ("mobo_rch", "MoBO RC-H — broke a prior MONTHLY high that held as resistance for months (position)", "Monthly trend", False),
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
    # Reclaims are DAY-TRADE tools — a reclaimed level is an intraday bounce, NOT a hold-for-days
    # pattern (2026-07-07). Listed FIRST so monthly_rc/weekly_rc win over the broad monthly_/weekly.
    ("monthly_rc", "day_trade"), ("weekly_rc", "day_trade"), ("staged_pwl", "day_trade"),
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
    "swing_rsi_30": "Daily RSI crossed back ABOVE 30 from below (was oversold yesterday, reclaimed 30 today) on an upper-half close — the bottom-fishing 'turn is in' confirmation. Higher conviction near the 200 SMA/EMA. A longer-hold reversal entry on washed-out quality/mega caps. Manage by RSI: T1 ~RSI 45-50, T2 RSI 70; STOP = a close back under 30. Pairs with rsi_oversold (the watch) — this is the trigger.",
    "rsi_oversold": "Daily RSI closed in the 30-35 buy zone — reclaimed 30 from below or dipped/holding in 30-35 from above. NEVER fires below 30 (the falling knife — RSI 29 is not a buy; wait for the turn/hold). A SWING entry (hold days), best on washed-out quality/mega caps that mean-revert. Manage by RSI: T1 = RSI 50, T2 = RSI 70; STOP = a daily close back under RSI 30 (exactly where Steve Burns stopped out of NFLX, -2.75%, Fri 06-12). Fired at the daily close, once per entry (rare).",
    "rc_4h_long": "4h RC long: price wicked BELOW the prior 4h low then closed back above it — swept-low bounce / reversal long. Stop = the wick low. A heads-up — eyeball the 4h, not every one is an entry.",
    "rc_4h_hrec": "4h RC-H: price dipped below the prior 4h HIGH then closed back above it — the broken high held as support = breakout-retest continuation long. Stop = the retest low.",
    "rc_4h_short": "4h RC short: price wicked ABOVE the prior 4h high then closed back below it — failed break / rejection (index-leaning). Stop = the wick high.",
    "reclaim_long": "Index reclaim long (SPY/QQQ/DRAM, 15m): in the morning, price was ABOVE the opening-range high or the prior-day high, dipped ~0.18% under it (shakeout), and RECLAIMED it — WITH room to the next resistance (no buying into a ceiling). ENTRY = the reclaim close · STOP = the dip low · TARGET = take profit INTO the next resistance (sell the whole position there). Long-only — the short mirror has no backtested edge.",
    "rc_daily_long": "Daily RC: price undercut the prior-DAY low (PDL) then reclaimed it intraday — swept-low bounce on the daily level. Stop = the day's swept low. ≈ PDL reclaim, RC-model. A day-trade/swing heads-up.",
    "rc_daily_hrec": "Daily RC-H: price dipped below the prior-DAY high (PDH) then closed back above it — broken daily high held as support = breakout-retest continuation. Stop = the day's low. ≈ PDH reclaim, RC-model.",
    "weekly_rc": "Weekly RC: price undercut the prior-WEEK high or low then reclaimed it intraday — the broken weekly level held (RC-H = breakout-retest continuation above the prior-week high; RC = undercut & reclaim of the prior-week low). A SWING heads-up. Stop = the week's swept low. Rare — eyeball the weekly.",
    "monthly_rc": "Monthly RC: price undercut the prior-MONTH high or low then reclaimed it intraday — the broken monthly level held (RC-H = breakout-retest continuation above the prior-month high, the MU play; RC = undercut & reclaim of the prior-month low). A POSITION heads-up. Stop = the month's swept low. Very rare — a major level reclaim, eyeball the monthly.",
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
    "monthly_rc", "pml_held", "staged_pml_held",
    # 2026-07-12 — weekly sub-alerts folded into WLV (weekly_lvl_reclaim, spec 69). WLV
    # covers every completed weekly level (H/L/O/C × 4 weeks), so weekly_rc + PWL-held retire.
    "weekly_rc", "staged_pwl_held",
    # rc_4h_hrec RETIRED 2026-07-12 — the 4h HIGH reclaim chases resistance (buys into overhead).
    # Only rc_4h_long (4h LOW = support bounce) kept. Daily/weekly/monthly RC stay (directional-gated).
    "rc_4h_hrec",
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

    # SHORT alerts — staged_pdl_break + staged_pdh_rejection REVIVED 2026-06-06
    # (SPY/QQQ/IWM index shorts, see _BASE_CATALOG). The rest stay retired.
    "staged_pdh_failed_short",
    "staged_pwh_rejection", "staged_pwh_failed_short", "staged_pwl_break",
    "staged_pmh_rejection", "staged_pmh_failed_short", "staged_pml_break",

    # MA SHORT (per-MA) RE-ENABLED 2026-06-09 — now active in _MA_CATALOG, so
    # NOT obsolete. (The bare prefix ma_rejection_short_v3 stays obsolete above,
    # same as ma_bounce_long_v3 — real types are per-MA.)

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
