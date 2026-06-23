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
    label: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Active MA families — bounce LONG + rejection SHORT (re-enabled 2026-06-09).
# Each generates 6 per-MA toggles: {fam}_{ema8,ema21,ema50,ema100,ema200,sma}.
# An MA is dual-role: support from above (bounce=long) / resistance from below
# (rejection=short). The NOTICE (proximity) family stays removed (too noisy).
MA_SPLIT_FAMILIES = (
    ("ma_bounce_long_v3", "MA bounce long", "MA / EMA · Bounce Long"),
    ("ma_rejection_short_v3", "MA rejection short", "MA / EMA · Rejection Short"),
)
# #282 (2026-06-17) — narrowed to 8/21/50/200 EMA + 50/200 SMA. Dropped 100 EMA,
# 100 SMA, and the combined SMA toggle (split into explicit 50/200). All default OFF;
# fire only for symbols on the ma_alert_symbols allowlist (Settings).
_MA_TOGGLES = (
    ("ema8",   "EMA 8"),
    ("ema21",  "EMA 21"),
    ("ema50",  "EMA 50"),
    ("ema200", "EMA 200"),
    ("sma50",  "SMA 50"),
    ("sma200", "SMA 200"),
)


# ── The canonical 19 (active alert types only) ──────────────────────────
# (alert_type, label, category, default_enabled)
# default_enabled only applies on FIRST insert — `enabled` is never
# overwritten by seeding, so user toggles persist across deploys.
_BASE_CATALOG: list[tuple[str, str, str, bool]] = [
    # Pullback continuation (uptrend-gated long entry — companion to MA bounce)
    ("pullback_long", "Uptrend pullback continuation (Buy 1)", "Pullback", False),

    # Buy 2 — Prior-high held as support (spec 58 FR-004). Monthly RE-ACTIVATED
    # 2026-06-09 — structural focus (D/W/M highs & lows are the validated set).
    ("staged_pdh_held", "PDH held as support (Buy 2)", "Daily PDH/PDL", False),
    ("staged_pwh_held", "PWH held as support (Buy 2)", "Weekly", False),
    ("staged_pmh_held", "PMH held as support (Buy 2)", "Monthly", False),
    # PDH breakout on volume (#291) — close above PDH + volume_ratio>=2 + rising VWAP.
    ("staged_pdh_break", "PDH break on volume", "Daily PDH/PDL", False),

    # Buy 2 — Prior-low held / wick test (spec 58, 2026-05-23)
    ("staged_pdl_held", "PDL held — wick test (Buy 2)", "Daily PDH/PDL", False),
    ("staged_pwl_held", "PWL held — wick test (Buy 2)", "Weekly", False),
    ("staged_pml_held", "PML held — wick test (Buy 2)", "Monthly", False),

    # Proximity bounce DROPPED 2026-06-04 (spec 61) — entry = close, which
    # after a bounce off the level lands far away (TSLA PDL 416, alert fired
    # at 423). "Near support" wasn't near. The _held / _reclaim rules cover the
    # touch cases. staged_pdl/pwl/pdh_proximity live in OBSOLETE_ALERT_TYPES.

    # Opening-range-low defended (spec 61, 2026-06-03) — buy the held 15m
    # low of day, stop below the OR low, PDH = first target.
    ("staged_orl_held", "Opening-range low held (15m)", "Daily PDH/PDL", False),

    # Buy 2 — Prior-low reclaim (lost-and-recovered)
    ("staged_pdl_reclaim", "PDL reclaim", "Daily PDH/PDL", False),
    ("staged_pwl_reclaim", "PWL reclaim", "Weekly", False),
    ("staged_pml_reclaim", "PML reclaim", "Monthly", False),

    # Buy 2 — Prior-high reclaim — price was ABOVE the prior high, LOST it
    # (dipped below), then RECOVERED above it = the high now holds as support.
    # NOT a break (rally up through from below = buying resistance — see #1/#5).
    ("staged_pdh_reclaim", "PDH reclaim — lost & recovered as support", "Daily PDH/PDL", False),
    ("staged_pwh_reclaim", "PWH reclaim — lost & recovered", "Weekly", False),
    ("staged_pmh_reclaim", "PMH reclaim — lost & recovered", "Monthly", False),

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
    ("gap_support", "Gap support bounce — dip to a gap you opened above, held", "Gap S/R", False),
    ("gap_fill", "Gap fill — closed into a gap below; runs to the far edge", "Gap S/R", False),
    ("gap_reject", "Gap resistance reject — tagged an overhead gap and failed", "Gap S/R", False),

    # Lost-support rejection (2026-06-16) — a low level (PDL/PWL/PML) lost intraday
    # becomes resistance; the dual-role the EMAs/high-levels already have. Default OFF.
    ("lost_support_reject", "Lost support → resistance — PDL/PWL/PML lost, rejected on the way back up (SHORT)", "Levels", False),

    # Multi-period S/R (#262) — clustered multi-week / multi-month highs (resistance)
    # + lows (support); price wicks into a cluster and rejects/holds. Default OFF.
    ("htf_sr_reject", "Multi-period resistance reject — wicked into a weekly/monthly wall, closed back below (SHORT)", "Multi-period S/R", False),
    ("htf_sr_bounce", "Multi-period support bounce — wicked into a weekly/monthly floor, closed back above (LONG)", "Multi-period S/R", False),

    # Market context (spec 61) — SPY/QQQ open-line strength, set on 1h.
    ("index_open_strength", "Reclaimed & holding above today's open", "Market context", False),

    # SWING book (2026-06-13) — daily-close momentum/RSI triggers from the Momentum
    # Pine. These are SWING trades (multi-day holds, lower-risk R:R), a separate
    # book from the intraday day-trade entries above — and they BYPASS the
    # SPY-vs-PDL gate (a day-trade protection; see SWING_ALERT_TYPES in tv_webhook).
    # Fire INTRADAY the moment the daily setup forms (#234 removed the 16:00 EOD
    # gate), ≤ once/day each. rsi_70 = bullish (daily RSI above 70 can start a
    # parabola), rsi_oversold = first time the daily RSI enters the 30-35 buy zone
    # (reclaim 30 or hold — NEVER below 30), ema_5_20_cross = Steve Burns 5/20.
    ("rsi_70", "RSI 70 — daily RSI crossed above 70 (momentum)", "Swing", False),
    ("ema_5_20_cross", "5/20 EMA bullish cross (Steve Burns)", "Swing", False),
    ("rsi_oversold", "RSI oversold buy zone — daily RSI in 30-35 (reclaim/hold, never below 30)", "Swing", False),

    # Index SHORTs (spec 61, 2026-06-06) — SPY/QQQ/IWM only, via the SPY-short
    # routing whitelist. Trade WITH the breakdown: PDL break / PDH rejection on
    # heavy volume. Default OFF — record + watch the count before delivering.
    ("staged_pdl_break", "PDL break — index short (volume)", "Index shorts", False),
    ("staged_pdh_rejection", "PDH rejection — index short (volume)", "Index shorts", False),
    ("pdh_fail_short", "PDH failed break — accepted above PDH then lost it (short the loss, stop = PDH reclaim) · allowlist only", "Index shorts", False),

    # 4h reclaim — split into 3 independent toggles (2026-06-22) so users can turn
    # each direction off in Settings (the pine emits rc_4h_long / rc_4h_short /
    # rc_4h_hrec separately). All default OFF.
    ("rc_4h_long",  "4h RC long — reclaim of the prior 4h LOW (swept-low bounce, support-gated)", "4h reversal", False),
    ("rc_4h_hrec",  "4h RC-H — broken prior 4h HIGH held as support, UPTREND-gated (breakout-retest long)", "4h reversal", False),
    ("rc_4h_short", "4h RC short — failed break of the prior 4h HIGH (rejection)", "4h reversal", False),
    # Daily RC (from rc.pine) — undercut & reclaim of the prior-DAY low/high (≈ PDL/PDH
    # reclaim, RC-model). All default OFF.
    ("rc_daily_long", "Daily RC — reclaim of the prior-DAY LOW / PDL (undercut & reclaim)", "Daily RC", False),
    ("rc_daily_hrec", "Daily RC-H — reclaim of the prior-DAY HIGH / PDH (breakout-retest)", "Daily RC", False),

    # Weekly RC — Issue #3 (2026-06-13). The only actionable piece of the old
    # WkStage family: undercut & reclaim of the prior-week low on a GREEN week
    # (stop = the weekly low). The generic BUY/ADD/EXIT/stage NOTICEs were
    # unclear/not-actionable and are SUPPRESSED (weekly_stage → OBSOLETE).
    ("weekly_rc", "Weekly RC — prior-week high/low reclaim (swing)", "Weekly trend", False),
    # Monthly RC — added 2026-06-22. Same intraday level-cross model as 4h/weekly,
    # fired from the consolidated RC pine (rc.pine): undercut & reclaim of the prior
    # MONTH high (breakout-retest, the MU play) or low. Rare by nature. Default OFF.
    ("monthly_rc", "Monthly RC — prior-month high/low reclaim (position)", "Monthly trend", False),
    # weekly_ma_pullback SPLIT 2026-06-20 into held / reclaim / wick-reclaim so the
    # user can toggle each weekly-MA setup independently (10w/30w tagged in the note).
    ("weekly_ma_held", "Weekly MA held — pullback to the rising 10w/30w MA, held as support (Stage-2 position, target = weekly RSI 70)", "Weekly trend", False),
    ("weekly_ma_reclaim", "Weekly MA reclaim — closed back above the 10w/30w MA after being below it (Stage-2 position, target = weekly RSI 70)", "Weekly trend", False),
    ("weekly_ma_wick_reclaim", "Weekly MA wick-reclaim — undercut the 10w/30w MA then closed back above (shakeout, Stage-2 position, target = weekly RSI 70)", "Weekly trend", False),
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
    "staged_orl_held": "Stock pulled back to its first-15-minute low and held — the low of the day is being defended; prior-day high is the first target.",
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
    "rsi_oversold": "Daily RSI closed in the 30-35 buy zone — reclaimed 30 from below or dipped/holding in 30-35 from above. NEVER fires below 30 (the falling knife — RSI 29 is not a buy; wait for the turn/hold). A SWING entry (hold days), best on washed-out quality/mega caps that mean-revert. Manage by RSI: T1 = RSI 50, T2 = RSI 70; STOP = a daily close back under RSI 30 (exactly where Steve Burns stopped out of NFLX, -2.75%, Fri 06-12). Fired at the daily close, once per entry (rare).",
    "rc_4h_long": "4h RC long: price wicked BELOW the prior 4h low then closed back above it — swept-low bounce / reversal long. Stop = the wick low. A heads-up — eyeball the 4h, not every one is an entry.",
    "rc_4h_hrec": "4h RC-H: price dipped below the prior 4h HIGH then closed back above it — the broken high held as support = breakout-retest continuation long. Stop = the retest low.",
    "rc_4h_short": "4h RC short: price wicked ABOVE the prior 4h high then closed back below it — failed break / rejection (index-leaning). Stop = the wick high.",
    "rc_daily_long": "Daily RC: price undercut the prior-DAY low (PDL) then reclaimed it intraday — swept-low bounce on the daily level. Stop = the day's swept low. ≈ PDL reclaim, RC-model. A day-trade/swing heads-up.",
    "rc_daily_hrec": "Daily RC-H: price dipped below the prior-DAY high (PDH) then closed back above it — broken daily high held as support = breakout-retest continuation. Stop = the day's low. ≈ PDH reclaim, RC-model.",
    "weekly_rc": "Weekly RC: price undercut the prior-WEEK high or low then reclaimed it intraday — the broken weekly level held (RC-H = breakout-retest continuation above the prior-week high; RC = undercut & reclaim of the prior-week low). A SWING heads-up. Stop = the week's swept low. Rare — eyeball the weekly.",
    "monthly_rc": "Monthly RC: price undercut the prior-MONTH high or low then reclaimed it intraday — the broken monthly level held (RC-H = breakout-retest continuation above the prior-month high, the MU play; RC = undercut & reclaim of the prior-month low). A POSITION heads-up. Stop = the month's swept low. Very rare — a major level reclaim, eyeball the monthly.",

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
    # rc_4h split into rc_4h_long/short/hrec (2026-06-22) — drop the old combined toggle
    "rc_4h",

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
    # Pulled by request; the trusted ORL-held (staged_orl_held) stays.
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

    # MA set narrowed to 8/21/50/200 EMA + 50/200 SMA (#282, 2026-06-17). The
    # 100 EMA + the combined SMA toggle are retired (SMA split into sma50/sma200).
    "ma_bounce_long_v3_ema100", "ma_bounce_long_v3_sma",
    "ma_rejection_short_v3_ema100", "ma_rejection_short_v3_sma",

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
    "swing_52w_high_retest", "swing_5day_low_reclaim", "swing_rsi_30",
)


async def seed_alert_type_config(conn) -> None:
    """Idempotently sync the catalogue into the table.

    Inserts missing rows; refreshes label/category on existing rows; never
    touches `enabled`, so user toggles persist. Deletes obsoleted keys so
    the Settings UI never shows dead toggles.
    """
    for alert_type, label, category, default_enabled in ALERT_TYPE_CATALOG:
        await conn.execute(
            text(
                "INSERT INTO alert_type_config (alert_type, label, category, enabled) "
                "VALUES (:at, :label, :cat, :en) "
                "ON CONFLICT (alert_type) DO UPDATE SET "
                "label = EXCLUDED.label, category = EXCLUDED.category"
            ),
            {"at": alert_type, "label": label, "cat": category, "en": default_enabled},
        )
    for obsolete in OBSOLETE_ALERT_TYPES:
        await conn.execute(
            text("DELETE FROM alert_type_config WHERE alert_type = :at"),
            {"at": obsolete},
        )
