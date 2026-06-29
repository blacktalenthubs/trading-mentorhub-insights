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
    # ma_rejection_short_v3 CUT 2026-06-23 — long-only book; rc.pine ports only the
    # bounce. (DB rows deleted; nothing bound emits the rejection.)
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
    # SMA 50/200 CUT 2026-06-23 — the EMA sits ~1pt away and captures the same test;
    # no need for SMA separately. (rc.pine ports the EMA ladder only.)
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
    ("rsi_70", "RSI 70 — daily RSI crossed above 70 (momentum)", "Swing", False),
    ("ema_5_20_cross", "5/20 EMA bullish cross (Steve Burns)", "Swing", False),
    ("rsi_oversold", "RSI oversold buy zone — daily RSI in 30-35 (reclaim/hold, never below 30)", "Swing", False),
    ("swing_rsi_30", "RSI 30 reclaim — daily RSI crossed back ABOVE 30 from oversold (the turn is in; longer-hold bottom)", "Swing", False),

    # Index SHORTs (spec 61, 2026-06-06) — SPY/QQQ/IWM only, via the SPY-short
    # routing whitelist. Trade WITH the breakdown: PDL break / PDH rejection on
    # heavy volume. Default OFF — record + watch the count before delivering.
    ("staged_pdl_break", "PDL break — index short (volume)", "Index shorts", False),
    ("staged_pdh_rejection", "PDH rejection — index short (volume)", "Index shorts", False),
    ("pdh_fail_short", "PDH failed break — accepted above PDH then lost it (short the loss, stop = PDH reclaim) · allowlist only", "Index shorts", False),

    # 4h reclaim — long-only now (rc_4h_short RETIRED 2026-06-29 → OBSOLETE; the only
    # shorts we keep are the structural PDL break + PDH rejection). Both default OFF.
    ("rc_4h_long",  "4h RC long — reclaim of the prior 4h LOW (swept-low bounce, support-gated)", "4h reversal", False),
    ("rc_4h_hrec",  "4h RC-H — broken prior 4h HIGH held as support, UPTREND-gated (breakout-retest long)", "4h reversal", False),
    # Daily RC (from rc.pine) — undercut & reclaim of the prior-DAY low/high (≈ PDL/PDH
    # reclaim, RC-model). All default OFF.
    ("rc_daily_long", "Daily RC — reclaim of the prior-DAY LOW / PDL (undercut & reclaim)", "Daily RC", False),
    ("rc_daily_hrec", "Daily RC-H — reclaim of the prior-DAY HIGH / PDH (breakout-retest)", "Daily RC", False),

    # Index reclaim long (#65, from index_reclaim_long.pine) — the one backtested
    # day-trade edge for SPY/QQQ/DRAM: morning reclaim of the ORH or PDH after a
    # ~0.18% shakeout, with room to the next resistance → long, take profit into it.
    # Long-only (the short mirror has no edge). Default OFF (opt-in).
    ("reclaim_long", "Reclaim long — morning reclaim of the ORH/PDH with room + ~ATM strike (now in rc.pine)", "Index reclaim", False),
    # staged_orl_held REVIVED 2026-06-27 — the rc.pine OR-channel plays (orl_held/
    # orl_reclaim/orh_reject) were too NOISY (especially ORL) → retired to OBSOLETE. This is
    # the original 60m opening-range-low held (levels_day_vwap.pine). It's noisy by nature, so
    # it's SCOPED to a user-editable symbol allowlist (staged_orl_symbols in Settings; default
    # index SPY/QQQ/IWM, but add whatever you want). Off the list = Not-routed. Default OFF.
    ("staged_orl_held", "ORL held (30m opening-range low) — bounce off the OR low; NOISY, fires only for symbols in your ORL allowlist (Settings → Noisy alerts)", "Index reclaim", False),
    # ORH break (2026-06-28) — the high-side momentum breakout the user asked for (the ORH
    # rejection SHORT was retired; this is a LONG). Close above the 30m OR high on volume.
    ("orh_break", "ORH break — close above the 30m opening-range high on volume (momentum breakout long)", "Index reclaim", False),

    # Weekly RC — Issue #3 (2026-06-13). The only actionable piece of the old
    # WkStage family: undercut & reclaim of the prior-week low on a GREEN week
    # (stop = the weekly low). The generic BUY/ADD/EXIT/stage NOTICEs were
    # unclear/not-actionable and are SUPPRESSED (weekly_stage → OBSOLETE).
    ("weekly_rc", "Weekly RC — prior-week high/low reclaim (swing)", "Weekly trend", False),
    # 10w/30w weekly-MA reclaim·hold (rc.pine, 2026-06-26) — price tagged & held the 10/30
    # week MA on the weekly = long-term/position support reclaim (Weinstein stage). Both OFF.
    ("weekly_10w_held", "10w MA held — held the weekly 10-week MA (no break) (position)", "Weekly trend", False),
    ("weekly_10w_reclaim", "10w MA reclaim — undercut & reclaimed the weekly 10-week MA (position)", "Weekly trend", False),
    ("weekly_30w_held", "30w MA held — held the weekly 30-week MA (no break) (LONG-TERM entry)", "Weekly trend", False),
    ("weekly_30w_reclaim", "30w MA reclaim — undercut & reclaimed the weekly 30-week MA (LONG-TERM entry)", "Weekly trend", False),
    # Monthly RC — added 2026-06-22. Same intraday level-cross model as 4h/weekly,
    # fired from the consolidated RC pine (rc.pine): undercut & reclaim of the prior
    # MONTH high (breakout-retest, the MU play) or low. Rare by nature. Default OFF.
    ("monthly_rc", "Monthly RC — prior-month high/low reclaim (position)", "Monthly trend", False),
    # CML — the CURRENT-month low defended intraday (rc.pine, 2026-06-25). Distinct
    # from monthly_rc (prior month): cml_reclaim = price swept the month floor (new low)
    # and reclaimed it; cml_held = price tagged it from above and held. Both BUY, OFF.
    ("cml_reclaim", "CML reclaim — undercut & reclaim of the CURRENT-month low (month floor swept & held)", "Monthly trend", False),
    ("cml_held", "CML held — tag & hold of the CURRENT-month low as support", "Monthly trend", False),
    ("pml_held", "PML held — tag & hold of the PRIOR-month low as support", "Monthly trend", False),
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
    "orh_break":                "Stock closed above its 30-minute opening-range high on expanding volume — the first-half-hour momentum breakout (long). Stop = the OR high (now reclaimed support); first target = the nearest overhead level (PDH/PWH). Once per session.",
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
    "rc_daily_long": "Daily RC: price undercut the prior-DAY low (PDL) then reclaimed it intraday — swept-low bounce on the daily level. Stop = the day's swept low. ≈ PDL reclaim, RC-model. A day-trade/swing heads-up.",
    "reclaim_long": "Index reclaim long (SPY/QQQ/DRAM, 15m): in the morning, price was ABOVE the opening-range high or the prior-day high, dipped ~0.18% under it (shakeout), and RECLAIMED it — WITH room to the next resistance (no buying into a ceiling). ENTRY = the reclaim close · STOP = the dip low · TARGET = take profit INTO the next resistance (sell the whole position there). Long-only — the short mirror has no backtested edge. Backtested 77% win / +0.80R over 3yr; ~10–16 fires/yr (rare). The big down-moves and bottom-bounces are deliberately skipped (no edge).",
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
    # rc_4h_short RETIRED 2026-06-29 — long-only 4h; the only shorts we keep are the
    # structural PDL break + PDH rejection (levels_day_vwap). No 4h/EMA rejection shorts.
    "rc_4h_short",
    # ma_rejection_short_v3 family — long-only book; no pine emits it (descriptions were
    # leftover). Kept here so any stale row is purged + arrival is dropped.
    "ma_rejection_short_v3", "ma_rejection_short_v3_ema8", "ma_rejection_short_v3_ema21",
    "ma_rejection_short_v3_ema50", "ma_rejection_short_v3_ema100", "ma_rejection_short_v3_ema200",

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
