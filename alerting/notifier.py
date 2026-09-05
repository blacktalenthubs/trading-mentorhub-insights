"""Notification delivery — email (SMTP) and SMS (Twilio)."""

from __future__ import annotations

import logging
import os
import smtplib
import threading
from datetime import datetime
from email.mime.text import MIMEText
from urllib.parse import quote

from analytics.intraday_rules import AlertSignal, AlertType
from alert_config import (
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    ALERT_SMS_TO,
    SMS_GATEWAY_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_USE_WHATSAPP,
)

logger = logging.getLogger(__name__)


def _get_app_url() -> str:
    """Return the public-facing app URL, ignoring localhost values."""
    _default = "https://tradecopilot.streamlit.app"
    url = os.environ.get("APP_URL", "") or _default
    if "localhost" in url or "127.0.0.1" in url:
        return _default
    return url.rstrip("/")


def _clean_message(msg: str | None) -> str:
    """Strip noisy context from alert messages for Telegram delivery.

    Removes SPY details, bounce quality, volume notes, regime warnings,
    and other verbose context that clutters the notification.
    """
    if not msg:
        return ""
    import re
    # Take only the first segment before " | " separators
    clean = msg.split(" | ")[0]
    # Remove common noise patterns
    _noise = [
        r"\s*CAUTION:.*$",
        r"\s*BOUNCE QUALITY:.*$",
        r"\s*SPY (?:also|at|regime|bearish|bullish).*$",
        r"\s*CHOPPY market.*$",
        r"\s*normal volume.*$",
        r"\s*Defending.*$",
        r"\s*15m trend.*$",
        r"\s*session:\s*\w+\s*$",
        r"\s*\d+MA confluence.*$",
    ]
    for pattern in _noise:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
    return clean.strip()


def _tv_alignment(direction: str, rule: str, stage_text: str) -> tuple[str, str, int]:
    """Map TV signal + stage → (alignment_glyph, conviction_label, conviction_score).

    Sweeps are universally A+ (work in any stage). Triangle signals only
    qualify as HIGH when stage matches direction. Counter-trend is LOW.
    """
    is_long = direction in ("BUY", "LONG")
    is_short = direction == "SHORT"
    rule_l = rule.lower()
    stage_l = stage_text.lower()

    if "sweep" in rule_l:
        return "✓ aligned", "HIGH", 75

    if "stage 2" in stage_l:
        return ("✓ aligned", "HIGH", 75) if is_long else ("✗ counter-trend", "LOW", 30)
    if "stage 4" in stage_l:
        return ("✓ aligned", "HIGH", 75) if is_short else ("✗ counter-trend", "LOW", 30)
    if "stage 3" in stage_l:
        if is_short and ("reject" in rule_l or "rejection" in rule_l):
            return "⚠ topping fade", "MEDIUM", 55
        if is_long:
            return "⚠ caution — distribution", "LOW", 35
    if "stage 1" in stage_l:
        return "— basing (sweeps only)", "LOW", 35
    if "transitioning" in stage_l:
        return "— transitioning", "MEDIUM", 50

    return "— neutral", "MEDIUM", 50


def format_lifecycle_message(
    *,
    outcome: str,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    hit_price: float,
    rule: str,
    ma_tag_pretty: str = "",
) -> str:
    """Build a one-shot Telegram message for a TV alert outcome (T1/T2/stop hit).

    *outcome* — one of "T1", "T2", "STOP".
    Computes R-multiple from entry/stop spread and direction.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        r_multiple = 0.0
    elif direction == "BUY":
        r_multiple = (hit_price - entry) / risk
    else:
        r_multiple = (entry - hit_price) / risk

    rule_label = f"{rule} ({ma_tag_pretty})" if ma_tag_pretty else rule

    if outcome == "T1":
        head = f"🎯 <b>{symbol} T1 HIT ${hit_price:.2f}</b>"
        tail = f"+{r_multiple:.2f}R · trail to BE or take half"
    elif outcome == "T2":
        head = f"🏆 <b>{symbol} T2 HIT ${hit_price:.2f}</b>"
        tail = f"+{r_multiple:.2f}R · runner complete"
    elif outcome == "STOP":
        head = f"🛑 <b>{symbol} STOPPED ${hit_price:.2f}</b>"
        tail = f"{r_multiple:.2f}R · trade closed"
    else:
        head = f"<b>{symbol} {outcome} ${hit_price:.2f}</b>"
        tail = f"{r_multiple:+.2f}R"

    return f"{head}\nFrom: {rule_label} entry ${entry:.2f}\n{tail}"


def _target_line(signal) -> str | None:
    """The ONE target rendered by kind (Sub-spec A — T2 removed).

    - a price (level target)         → "Target $123.45"
    - an RSI target (Case B / swing) → "Target RSI 70"
    - end-of-day exit                → "Target EOD exit"
    Returns None when there's no target.
    """
    if getattr(signal, "target_1", None) is not None:
        return f"Target ${signal.target_1:.2f}"
    _tk = getattr(signal, "_target_kind", None)
    _tv = getattr(signal, "_target_value", None)
    if _tk == "rsi" and _tv is not None:
        return f"Target RSI {int(_tv)}"
    if _tk == "eod":
        return "Target EOD exit"
    return None


# Rule-name → human title. Mirrors web/src/lib/alertFormat.ts (formatSetup +
# setupTitle) so Telegram reads the same as the app feed instead of a raw rule
# key. Keep in sync with that file when rules are added.
_SETUP_NAMES: dict[str, str] = {
    "rc_4h_long": "4-hour low reclaim",
    "rc_4h_hrec": "4-hour high break",
    "rc_daily_long": "Prior-day low reclaim",
    "rc_daily_hrec": "Prior-day high break",
    "pq_reclaim": "Prior-quarter low reclaim (swing)",
    "ma200_bounce": "200-MA bounce (swing)",
    "pdh_held": "PDH reclaim / hold",
    "pdl_held": "PDL reclaim / hold",
    "orb_high_held": "ORB high held",
    "orb_low_held": "ORB low held",
    "weekly_lvl_reclaim": "Prior-week reclaim / gap",
    "monthly_lvl_reclaim": "Prior-month reclaim / gap",
    "weekly_lvl_reject": "Prior-week rejection",
    "monthly_lvl_reject": "Prior-month rejection",
    "daily_rc": "Daily low reclaim",
    "weekly_rc": "Weekly low reclaim",
    "monthly_rc": "Monthly low reclaim",
    "fourh_reclaim": "4H reclaim (long)",
    "fourh_reject": "4H rejection (short)",
    "fourh_breakup": "4H break-up (long)",
    "fourh_breakdn": "4H break-down (short)",
    "fourh_ema_reclaim": "50 EMA reclaim (long)",
    "fourh_ema_reject": "50 EMA rejection (short)",
    "fourh_ema_breakup": "50 EMA break-up (long)",
    "fourh_ema_breakdn": "50 EMA break-down (short)",
    "fourh_ma200_reclaim": "200 reclaim (long)",
    "gap_and_go": "Gap-and-Go (long)",
    "reclaim_long": "Morning shakeout reclaim",
    "gap_up_continuation_long": "Gap-up continuation",
    "orb_break": "ORB break",
    "orb_held": "ORB held",
    "orb_retest": "ORB retest",
    "orb_exit": "ORB exit",
    "orb_reclaim_low": "ORB low reclaim",
    "orb_reclaim_high": "ORB high reclaim",
    "cml_held": "Month-low support hold",
    "cml_reclaim": "Month-low reclaim",
    "pml_held": "Prior-month-low support hold",
    "monthly_box": "Monthly box breakout",
    "mobo_rch": "Monthly high breakout",
    "weekly_10w_held": "10-week MA support hold",
    "weekly_10w_reclaim": "10-week MA reclaim",
    "weekly_30w_held": "30-week MA support hold",
    "weekly_30w_reclaim": "30-week MA reclaim",
    "swing_rsi_30": "RSI-30 reclaim (the turn)",
    "swing_sma50_reclaim": "50 SMA reclaim (swing)",
    "swing_sma200_reclaim": "200 SMA reclaim (swing)",
    "open_reclaimed": "Open reclaimed",
    "open_held": "Open held",
    "open_wick_reclaim": "Open wick reclaim",
    "open_lost": "Open lost",
    "htf_support_held": "HTF support held",
    "htf_proximity": "HTF proximity",
    "pullback_long": "Pullback continuation",
    "rsi_70": "RSI 70 — momentum",
    "ema_5_20_cross": "5/20 EMA cross",
    "rsi_oversold": "RSI oversold buy zone (30-35)",
    "gap_support": "Gap support bounce",
    "gap_fill": "Gap fill → far edge",
    "gap_reject": "Gap rejection",
    "lost_support_reject": "Lost support → resistance",
    "htf_sr_reject": "Multi-period resistance",
    "htf_sr_bounce": "Multi-period support",
    "last4h_long": "Last 4H reclaim / break",
    "last4h_short": "Last 4H reject / breakdown",
}


def _pretty_setup(rule: str, note: str | None = None) -> str:
    """Human setup name for a Pine rule — mirrors the app's formatSetup/setupTitle.
    For the overloaded last4h_* type, the ACTUAL trigger (which level) is parsed
    out of the Pine note ("RECLAIM of the daily 50 SMA …" → "50 SMA Reclaim")."""
    import re as _re
    t = (rule or "")
    for pre in ("tv_", "ai_"):
        if t.startswith(pre):
            t = t[len(pre):]
    if not t:
        return "Signal"
    # last4h_* — one type, many triggers; the specifics live in the note prose.
    if t in ("last4h_long", "last4h_short"):
        txt = (note or "").upper()
        if _re.search(r"GAP.?AND.?GO", txt):
            return "Gap-and-Go"
        is_long = t == "last4h_long"
        if "RECLAIM" in txt or "BACK ABOVE" in txt:
            verb = "Reclaim"
        elif "REJECT" in txt or "BACK BELOW" in txt:
            verb = "Reject"
        elif "BREAKDOWN" in txt:
            verb = "Breakdown"
        elif "BREAK" in txt:
            verb = "Break"
        else:
            verb = "Long" if is_long else "Short"
        m = _re.search(r"(\d{1,3})\s*(EMA|SMA)", txt)
        if m:
            level = f"{m.group(1)} {m.group(2)}"
        elif "HIGH" in txt:
            level = "Last 4h High"
        elif "LOW" in txt:
            level = "Last 4h Low"
        else:
            level = "Last 4h"
        return f"{level} {verb}".strip()
    # Scanner MA ladder — ma_reclaim_50 → "50 SMA Reclaim", ema_bounce_21 → "21 EMA Bounce".
    # Matched before the v3 family below so the plain ladder keys don't fall through
    # to the raw title-case ("Ma Reclaim 50").
    m = _re.match(r"^(ma|ema)_(reclaim|rejection|bounce)_(\d{1,3})$", t)
    if m:
        kind = "SMA" if m.group(1) == "ma" else "EMA"
        return f"{m.group(3)} {kind} {m.group(2).capitalize()}"
    # MA families — ma_bounce_long_v3_ema8_ema21 → "EMA 8 + EMA 21 bounce"
    m = _re.match(r"^ma_(bounce_long|rejection_short|proximity_long|proximity_short)_v3_(.+)$", t)
    if m:
        kind = {"bounce_long": "bounce", "rejection_short": "rejection"}.get(m.group(1), "proximity")
        mas = " + ".join(_re.sub(r"^(EMA|SMA)", r"\1 ", x.upper()) for x in m.group(2).split("_"))
        return f"{mas} {kind}"
    # Staged level events — staged_pdh_break → "PDH break"
    m = _re.match(r"^staged_p([dwm])([hl])_(.+)$", t)
    if m:
        if m.group(1) == "d":
            lvl = "PD" + m.group(2).upper()
        else:
            lvl = ("Weekly " if m.group(1) == "w" else "Monthly ") + ("high" if m.group(2) == "h" else "low")
        return f"{lvl} {m.group(3).replace('_', ' ')}"
    if t in _SETUP_NAMES:
        return _SETUP_NAMES[t]
    return t.replace("_", " ").title()


def _format_tv_body(signal: AlertSignal) -> str | None:
    """TV-native Telegram message. Driven by Pine script output.

    No rule-engine concepts (Confluence, regime, scanner score). Just the
    rule that fired, stage alignment, and entry/stop/targets.
    """
    import html as _html

    sym = _html.escape(signal.symbol)
    direction = (signal.direction or "").upper()
    dir_label = "LONG" if direction in ("BUY", "LONG") else ("SHORT" if direction == "SHORT" else direction)
    rule = getattr(signal, "_tv_rule", "") or "tv_alert"
    stage_raw = getattr(signal, "_tv_stage", "") or ""
    # Stage text from Pine carries 3 segments (name / trigger / action) joined
    # by " — " (newer Pine) or "\n" (older Pine — broken JSON, kept for compat).
    # Take just the badge name for clean Telegram display.
    import re as _re
    stage_first = _re.split(r"\n| — ", stage_raw, maxsplit=1)[0].strip() if stage_raw else ""

    alignment_tag, conviction_label, conviction_score = _tv_alignment(direction, rule, stage_first)

    ma_tag_pretty = getattr(signal, "_tv_ma_tag_pretty", "") or ""
    # Human setup name (matches the app feed) instead of the raw rule key. For the
    # overloaded last4h_* type the specific trigger is parsed from the Pine note.
    _pretty = _pretty_setup(rule, getattr(signal, "note", None) or (signal.message or ""))
    rule_label = f"{_pretty} ({ma_tag_pretty})" if ma_tag_pretty else _pretty
    parts = [f"<b>{dir_label} {sym} ${signal.price:.2f}</b> — <i>{_html.escape(rule_label)}</i>"]

    # Trade-style badge (day/swing/long/gap) — the first thing a busy trader reads.
    _tt = getattr(signal, "_trade_type", None)
    _TT_TAG = {"day": "⚡ DAY", "swing": "📈 SWING", "long": "💎 LONG-TERM", "gap": "🚀 GAP"}
    if _tt in _TT_TAG:
        parts.append(_TT_TAG[_tt])

    levels = []
    if signal.entry is not None:
        levels.append(f"Entry ${signal.entry:.2f}")
    if signal.stop is not None:
        levels.append(f"Stop ${signal.stop:.2f}")
    _t = _target_line(signal)
    if _t:
        levels.append(_t)
    if levels:
        parts.append(" · ".join(levels))

    if stage_first:
        parts.append(f"Stage: {_html.escape(stage_first)} {alignment_tag}")

    # VWAP context — only if Pine supplied it and slope is meaningful
    vwap = getattr(signal, "_tv_vwap", None)
    slope = getattr(signal, "_tv_vwap_slope_pct", None)
    if vwap is not None and slope is not None:
        slope_word = "rising" if slope > 0.1 else ("falling" if slope < -0.1 else "flat")
        parts.append(f"VWAP ${vwap:.2f} ({slope_word} {slope:+.2f}%)")

    # v2 Pine order-flow context — always show when data present, so the
    # trader sees whether the silence means "good signal" or "missing data".
    # Conviction penalties stay one-sided (only down on bad order flow) to
    # preserve the existing baseline calibration — no upward boost for good.
    volume_ratio = getattr(signal, "_tv_volume_ratio", None)
    cvd_diverging = getattr(signal, "_tv_cvd_diverging", False)
    cvd_delta = getattr(signal, "_tv_cvd_delta", None)

    if volume_ratio is not None:
        if volume_ratio < 1.5:
            conviction_score -= 25
            parts.append(f"⚠️ Low volume on fire bar ({volume_ratio:.2f}× avg)")
        elif volume_ratio >= 2.0:
            parts.append(f"✅ Strong volume ({volume_ratio:.2f}× avg)")
        else:
            parts.append(f"Volume: {volume_ratio:.2f}× avg")

    if cvd_delta is not None:
        if cvd_diverging:
            conviction_score -= 20
            parts.append(f"⚠️ CVD diverging — order flow not confirming move")
        else:
            parts.append(f"✅ CVD confirming move")

    # Confluence — number of timeframe levels stacked at the breakout/reclaim
    # price. 2+ = institutional memory at this level across timeframes,
    # materially higher conviction (per user 2026-05-06 — "the more convinced
    # the better we are at executing"). Only boost on confluence ≥ 2; single-
    # level events get the existing baseline calibration.
    confluence_count = getattr(signal, "_tv_confluence_count", 1) or 1
    if confluence_count >= 3:
        conviction_score += 25
        parts.append(f"🎯 Triple confluence — daily + weekly + monthly stacked")
    elif confluence_count >= 2:
        conviction_score += 15
        parts.append(f"🎯 Confluence x{confluence_count} — multiple timeframes stacked")

    conviction_score = max(15, conviction_score)
    if conviction_score < 35:
        conviction_label = "LOW"
    elif conviction_score < 65:
        conviction_label = "MEDIUM"
    else:
        conviction_label = "HIGH"

    parts.append(f"Conviction: {conviction_label}/{conviction_score}")

    return "\n".join(parts)[:4000]


def _format_sms_body(signal: AlertSignal) -> str | None:
    """Build a concise SMS/Telegram message. Returns None to skip Telegram.

    Output uses HTML formatting for Telegram (clickable links, bold headers).
    """
    import html as _html

    # TradingView alerts are driven purely by what the Pine script emits
    # (rule, stage, VWAP). Rule-engine concepts (Confluence, score, regime)
    # are intentionally absent — see _format_tv_body.
    if getattr(signal, "_source", None) == "tradingview":
        return _format_tv_body(signal)

    label = signal.alert_type.value.replace("_", " ").title()

    # NOTICE — send to Telegram (useful context: inside day, weekly tests, resistance zones)
    if signal.direction == "NOTICE":
        import html as _html_n
        _notice_msg = signal.message.split(" — ")[0] if signal.message else label
        return (
            f"<b>NOTICE — {_html_n.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
            f"{_notice_msg}"
        )

    # Best Setups (user-pinned) — distinct format so users tell them apart from scanner alerts
    if signal.alert_type.value in ("best_setup_day", "best_setup_swing"):
        _sym = _html.escape(signal.symbol)
        _tf = "Day trade" if signal.alert_type.value == "best_setup_day" else "Swing trade"
        _dir = "LONG" if signal.direction == "BUY" else "SHORT"
        parts = [f"<b>\U0001f4cc BEST SETUP (you pinned) \u2014 {_sym} ${signal.price:.2f}</b>"]
        parts.append(f"{_tf} \u00b7 {_dir}")
        _levels = []
        if signal.entry is not None:
            _levels.append(f"Entry ${signal.entry:.2f}")
        if signal.stop is not None:
            _levels.append(f"Stop ${signal.stop:.2f}")
        _t = _target_line(signal)
        if _t:
            _levels.append(_t)
        if _levels:
            parts.append(" \u00b7 ".join(_levels))
        if signal.message:
            parts.append(signal.message)
        if signal.confidence:
            parts.append(f"Conviction: {signal.confidence.upper()}")
        return "\n".join(parts)[:4000]

    # SWING alerts — check BEFORE SELL filter (swing exits have direction "SELL")
    if signal.alert_type.value.startswith("swing_"):
        import html as _html_swing
        _sym = _html_swing.escape(signal.symbol)

        # Swing EXIT alerts
        if signal.alert_type.value in ("swing_target_hit", "swing_stopped_out",
                                        "swing_rsi_target", "swing_pdl_close",
                                        "swing_ma_invalidated"):
            _exit_label = {
                "swing_target_hit": "TARGET REACHED",
                "swing_stopped_out": "STOP REACHED",
                "swing_rsi_target": "RSI TARGET",
                "swing_pdl_close": "CLOSED BELOW PDL",
                "swing_ma_invalidated": "MA INVALIDATED",
            }.get(signal.alert_type.value, "EXIT")
            _msg = signal.message.replace("[SWING] ", "") if signal.message else _exit_label
            return (
                f"<b>SWING EXIT — {_sym} ${signal.price:.2f}</b>\n"
                f"{_msg}"
            )

        # Swing RSI zone notices (oversold/overbought)
        if signal.alert_type.value in ("swing_rsi_oversold", "swing_rsi_overbought"):
            _msg = signal.message.replace("[SWING] ", "") if signal.message else label
            return (
                f"<b>SWING NOTICE — {_sym} ${signal.price:.2f}</b>\n"
                f"{_msg}"
            )

        # Swing BUY entries
        parts = [f"<b>SWING LONG {_sym} ${signal.price:.2f}</b>"]
        _levels = []
        if signal.entry is not None:
            _levels.append(f"Entry ${signal.entry:.2f}")
        if signal.stop is not None:
            _levels.append(f"Stop ${signal.stop:.2f} (daily close)")
        _t = _target_line(signal)
        if _t:
            _levels.append(_t)
        if _levels:
            parts.append(" · ".join(_levels))

        _reason = signal.message.replace("[SWING] ", "") if signal.message else label
        _conviction = "HIGH" if signal.score >= 75 else ("MEDIUM" if signal.score >= 55 else "LOW")
        parts.append(f"Setup: {_reason}")
        parts.append(f"Conviction: {_conviction}/{signal.score}")
        # Multi-timeframe confluence
        _conf = getattr(signal, "_confluence_score", 0)
        if _conf and _conf >= 2:
            _conf_emoji = "🟢" if _conf == 3 else "🟡"
            parts.append(f"{_conf_emoji} Confluence: {_conf}/3 timeframes aligned")
        return "\n".join(parts)[:4000]

    # SELL — route by type: stops → alert, resistance → NOTICE, targets → suppressed
    if signal.direction == "SELL":
        _exit_types = {"stop_loss_hit", "auto_stop_out"}
        _resistance_notice_types = {
            "weekly_high_resistance":  "Rejected at weekly high",
            "ma_resistance":           "Rejected at MA resistance",
            "resistance_prior_high":   "Rejected at prior high",
            "monthly_high_resistance": "Rejected at monthly high",
        }

        if signal.alert_type.value in _exit_types:
            import html as _html2
            return (
                f"<b>STOP LEVEL REACHED — {_html2.escape(signal.symbol)}</b>\n"
                f"Stop ${signal.price:.2f} reached\n"
                f"Review position — exit if thesis broken"
            )

        if signal.alert_type.value in _resistance_notice_types:
            import html as _html_res
            _res_label = _resistance_notice_types[signal.alert_type.value]
            _conviction = "HIGH" if signal.score >= 75 else ("MEDIUM" if signal.score >= 55 else "LOW")
            _vol = signal.volume_label or ""
            _vol_line = f" | Volume: {_vol}" if _vol else ""
            return (
                f"<b>RESISTANCE {_html_res.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
                f"Level: {_res_label}\n"
                f"Conviction: {_conviction}/{signal.score}{_vol_line}\n"
                f"Action: tighten stop / take profits / watch for breakdown"
            )

        return None  # T1/T2 suppressed — monitor sends these with Exit buttons

    # VWAP reclaim — send as NOTICE (awareness, not entry pressure)
    # First VWAP reclaim from below is a momentum shift signal
    if signal.direction == "BUY" and signal.alert_type.value == "vwap_reclaim":
        import html as _html_vwap
        return (
            f"<b>NOTICE — {_html_vwap.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
            f"VWAP reclaimed from below — momentum shifting bullish\n"
            f"Watch for pullback to VWAP for entry"
        )

    # SHORT → all sent as RESISTANCE alerts to Telegram. No suppression.

    # LONG (BUY) and RESISTANCE (SHORT) — entry evaluation format
    _dir = "RESISTANCE" if signal.direction == "SHORT" else "LONG"
    # Clean message — strip SPY noise, take only the core reason
    _reason = _clean_message(signal.message.split(" — ")[0]) if signal.message and " — " in signal.message else label

    parts = [f"<b>{_dir} {_html.escape(signal.symbol)} ${signal.price:.2f}</b>"]

    # Levels
    # BUG-2 fix: show both structural entry and current price when they differ
    _levels = []
    if signal.entry is not None:
        # If current price is >0.5% above entry, show both so trader knows the gap
        _entry_gap = abs(signal.price - signal.entry) / signal.entry if signal.entry > 0 else 0
        if _entry_gap > 0.005:
            _levels.append(f"Entry ${signal.entry:.2f} (now ${signal.price:.2f})")
        else:
            _levels.append(f"Entry ${signal.entry:.2f}")
    if signal.stop is not None:
        _levels.append(f"Stop ${signal.stop:.2f}")
    if signal.target_1 is not None:
        _levels.append(f"T1 ${signal.target_1:.2f}")
    if signal.target_2 is not None:
        _levels.append(f"T2 ${signal.target_2:.2f}")
    if _levels:
        parts.append(" · ".join(_levels))

    # Reason + Conviction
    _conviction = "HIGH" if signal.score >= 75 else ("MEDIUM" if signal.score >= 55 else "LOW")
    parts.append(f"Reason: {_reason}")
    parts.append(f"Conviction: {_conviction}/{signal.score}")
    # Multi-timeframe confluence
    _conf = getattr(signal, "_confluence_score", 0)
    if _conf and _conf >= 2:
        _conf_emoji = "🟢" if _conf == 3 else "🟡"
        parts.append(f"{_conf_emoji} Confluence: {_conf}/3 timeframes aligned")

    # Telegram message limit is 4096 chars; truncate safely
    return "\n".join(parts)[:4000]


def _format_email_body(signal: AlertSignal) -> str:
    """Build a concise plain-text email body — same format as Telegram."""
    import re

    # Reuse the Telegram formatter and strip HTML tags
    body = _format_sms_body(signal)
    if body is None:
        # Fallback for suppressed types (SELL/NOTICE)
        label = signal.alert_type.value.replace("_", " ").title()
        return f"{signal.direction} {signal.symbol} ${signal.price:.2f}\n{label}"

    return re.sub(r"<[^>]+>", "", body)


def send_plain_email(email_to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD or not email_to:
        logger.warning("Email not configured — skipping plain email")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = email_to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [email_to], msg.as_string())
        logger.info("Plain email sent to %s: %s", email_to, subject)
        return True
    except Exception:
        logger.exception("Failed to send plain email to %s", email_to)
        return False


def send_email_to(signal: AlertSignal, email_to: str) -> bool:
    """Send an alert email to an explicit recipient. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD or not email_to:
        logger.warning("Email not configured — skipping")
        return False

    from ui_theme import display_direction
    dir_label, _ = display_direction(signal.direction)
    subject = (
        f"[PATTERN ALERT] {dir_label} {signal.symbol} "
        f"- {signal.alert_type.value.replace('_', ' ').title()} @ ${signal.price:.2f}"
    )
    body = _format_email_body(signal)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = email_to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [email_to], msg.as_string())
        logger.info("Email sent to %s: %s", email_to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", email_to)
        return False


def send_email(signal: AlertSignal) -> bool:
    """Send an alert email to the global ALERT_EMAIL_TO. Returns True on success."""
    return send_email_to(signal, ALERT_EMAIL_TO)


# Sink gate: only send Telegram to the user specified by SCAN_USER_EMAIL.
# Lazily resolved from email → chat_id on first call.  Empty set = no restriction.
_ALLOWED_CHAT_IDS: set[str] | None = None


def _allowed_chat_ids() -> set[str]:
    global _ALLOWED_CHAT_IDS
    if _ALLOWED_CHAT_IDS is not None:
        return _ALLOWED_CHAT_IDS
    email = (os.environ.get("SCAN_USER_EMAIL") or "vbolofinde@gmail.com").strip().lower()
    if not email:
        _ALLOWED_CHAT_IDS = set()
        return _ALLOWED_CHAT_IDS
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT telegram_chat_id FROM users WHERE LOWER(email) = ?",
                (email,),
            ).fetchone()
        _ALLOWED_CHAT_IDS = {str(row["telegram_chat_id"])} if row and row["telegram_chat_id"] else set()
    except Exception:
        logger.warning("Failed to resolve SCAN_USER_EMAIL chat_id", exc_info=True)
        _ALLOWED_CHAT_IDS = set()
    return _ALLOWED_CHAT_IDS


def _send_telegram_to(
    body: str, chat_id: str, reply_markup: dict | None = None, parse_mode: str | None = None,
) -> bool:
    """Send a message via Telegram Bot API to an explicit chat_id.

    *reply_markup* — optional InlineKeyboardMarkup dict for interactive buttons.
    *parse_mode* — "HTML" or "Markdown". Auto-detected if body contains HTML tags.
    """
    # SCAN_USER_EMAIL allowlist is a DEV safety — restrict ALL Telegram to the scan
    # user during testing. OFF by default in production (#256): per-user routing
    # (_users_watching) already targets the right users, and this allowlist was
    # silently blocking the rollout — only the scan user (vbolofinde) got any
    # Telegram (alerts AND candle pings). Opt in with TELEGRAM_SCAN_USER_ONLY=true
    # for local/dev testing.
    if os.environ.get("TELEGRAM_SCAN_USER_ONLY", "false").strip().lower() in ("1", "true", "yes", "on"):
        allow = _allowed_chat_ids()
        if allow and str(chat_id) not in allow:
            logger.info("Telegram blocked — chat_id %s not in SCAN_USER_EMAIL allowlist", chat_id)
            return False

    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning(
            "Telegram not configured — missing %s",
            "TELEGRAM_BOT_TOKEN" if not TELEGRAM_BOT_TOKEN else "chat_id",
        )
        return False

    import json
    import urllib.request

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Auto-detect HTML if body contains tags; callers can also pass parse_mode explicitly
    _mode = parse_mode
    if _mode is None and ("<b>" in body or "<a " in body or "<i>" in body):
        _mode = "HTML"
    payload: dict = {
        "chat_id": chat_id,
        "text": body,
    }
    if _mode:
        payload["parse_mode"] = _mode
    if reply_markup:
        payload["reply_markup"] = reply_markup  # kept as dict for JSON body

    # Use JSON content-type for reliable inline-keyboard delivery;
    # form-urlencoded can mangle nested JSON with emoji characters.
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        resp_body = resp.read().decode("utf-8", errors="replace")
        logger.info(
            "Telegram sent to %s (status=%s): %s",
            chat_id, resp.status, resp_body[:200],
        )
        return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(
            "Telegram API error %s for chat_id=%s: %s",
            e.code, chat_id, error_body,
        )
        return False
    except Exception:
        logger.exception("Failed to send Telegram message to chat_id=%s", chat_id)
        return False


def _send_telegram(body: str) -> bool:
    """Send a message via Telegram Bot API to the global TELEGRAM_CHAT_ID."""
    return _send_telegram_to(body, TELEGRAM_CHAT_ID)


def _send_sms_via_email_gateway(body: str) -> bool:
    """Send SMS via carrier email-to-SMS gateway (e.g. number@txt.att.net).

    Truncates to 160 chars (SMS limit). No Subject header — gateways may
    prepend it to the message body, wasting precious characters.
    """
    if not SMS_GATEWAY_TO or not SMTP_USER or not SMTP_PASSWORD:
        return False

    # Strip HTML tags (body may contain Telegram HTML formatting)
    import re
    plain = re.sub(r"<[^>]+>", "", body)

    # SMS limit is 160 chars; MMS can do more but not all gateways support it
    truncated = plain[:160]

    msg = MIMEText(truncated)
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = SMS_GATEWAY_TO
    # No Subject — carrier gateways prepend it to the body

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [SMS_GATEWAY_TO], msg.as_string())
        logger.info("SMS (email gateway) sent to %s: %s", SMS_GATEWAY_TO, truncated[:50])
        return True
    except Exception:
        logger.exception("Failed to send SMS via email gateway")
        return False


def send_sms(signal: AlertSignal) -> bool:
    """Send alert via all configured channels (Telegram + Twilio)."""
    body = _format_sms_body(signal)
    if body is None:
        # Signal type suppressed (SELL/SHORT/NOTICE)
        return False

    sent_any = False

    # Telegram (primary)
    if TELEGRAM_BOT_TOKEN:
        logger.info("Notification channel: Telegram (chat_id=%s)", TELEGRAM_CHAT_ID or "<missing>")
        if _send_telegram(body):
            sent_any = True

    # Email-to-SMS gateway (always send alongside Telegram)
    if SMS_GATEWAY_TO:
        if _send_sms_via_email_gateway(body):
            sent_any = True

    if not sent_any:
        logger.warning("No notification channel delivered — check Telegram/SMS config")

    return sent_any


# Exit signals always Tier 1 (time-critical)
_TIER1_ALERT_TYPES = {
    AlertType.STOP_LOSS_HIT,
    AlertType.TARGET_1_HIT,
    AlertType.TARGET_2_HIT,
}


def _build_trade_buttons(signal: AlertSignal, alert_id: int | None) -> dict | None:
    """Build InlineKeyboardMarkup for trade ACK buttons.

    BUY/SHORT signals get "Took It" + "Skip" buttons.
    SELL signals get "Exited" + "Still Holding" buttons.
    NOTICE signals get no buttons.
    """
    if alert_id is None:
        return None

    if signal.direction in ("BUY", "SHORT"):
        return {
            "inline_keyboard": [[
                {"text": "\u2705 Took It", "callback_data": f"ack:{alert_id}"},
                {"text": "\u274c Skip", "callback_data": f"skip:{alert_id}"},
                {"text": "\U0001f6d1 Exit", "callback_data": f"exit:{alert_id}"},
            ]]
        }

    if signal.direction == "SELL":
        # T1/stop alerts get a single Exit button
        _exit_types = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
        if signal.alert_type.value in _exit_types:
            return {
                "inline_keyboard": [[
                    {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{alert_id}"},
                ]]
            }
        return {
            "inline_keyboard": [[
                {"text": "\U0001f4b0 Exited", "callback_data": f"exit:{alert_id}"},
                {"text": "\U0001f4aa Still Holding", "callback_data": f"hold:{alert_id}"},
            ]]
        }

    return None


# ---------------------------------------------------------------------------
# Per-alert-type channel routing (AI scanner alerts)
# ---------------------------------------------------------------------------
# User can configure each AI alert type to go to Telegram, Email, Both, or Off.
# Valid alert types: ai_update, ai_resistance, ai_long, ai_short, ai_exit
# Valid channels: "telegram" | "email" | "both" | "off"
# If notification_routing is NULL or missing a key, fall back to Telegram
# (legacy behavior — preserves today's default).

_AI_ALERT_TYPES = {"ai_update", "ai_resistance", "ai_long", "ai_short", "ai_exit"}


def resolve_ai_channels(
    user, alert_type: str, symbol: str | None = None,
) -> tuple[bool, bool]:
    """Resolve (send_telegram, send_email) for a given user + alert type.

    Reads user.notification_routing (JSON) if present. Unknown / missing →
    Telegram-only (legacy default). Respects telegram_enabled / email_enabled
    master switches and presence of chat_id / email.

    *symbol* — when provided and the alert is an AI update (ai_update or
    ai_resistance), checks user.telegram_update_symbols for a per-symbol
    Telegram override.  E.g. general routing is "email" but SPY is in the
    override list → force Telegram on for SPY.
    """
    import json

    raw = getattr(user, "notification_routing", None)
    channel = "telegram"  # legacy default
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, dict):
                val = data.get(alert_type)
                if val in ("telegram", "email", "both", "off"):
                    channel = val
        except Exception:
            logger.warning("notification_routing parse failed for user; using default")

    want_tg = channel in ("telegram", "both")
    want_email = channel in ("email", "both")

    # Per-symbol Telegram override for AI updates: if the symbol is in the
    # user's telegram_update_symbols list, force Telegram delivery on.
    if symbol and alert_type in ("ai_update", "ai_resistance"):
        tg_override_raw = getattr(user, "telegram_update_symbols", None) or ""
        tg_override_syms = {
            s.strip().upper() for s in tg_override_raw.split(",") if s.strip()
        }
        if symbol.upper() in tg_override_syms:
            want_tg = True

    # Respect master switches + presence of destination
    tg_ok = bool(
        want_tg
        and getattr(user, "telegram_enabled", True)
        and getattr(user, "telegram_chat_id", None)
    )
    email_ok = bool(want_email and getattr(user, "email", None))

    return tg_ok, email_ok


def send_ai_alert(
    user,
    alert_type: str,
    subject: str,
    body_html: str,
    telegram_kwargs: dict | None = None,
) -> tuple[bool, bool]:
    """Deliver an AI scanner alert according to user routing preferences.

    *body_html* — Telegram-flavored HTML. Email uses a tag-stripped version.
    *telegram_kwargs* — extra kwargs passed to _send_telegram_to (reply_markup, parse_mode).
    Returns (telegram_sent, email_sent).
    """
    import re

    tg_ok, email_ok = resolve_ai_channels(user, alert_type)

    tg_sent = False
    email_sent = False

    if tg_ok:
        kwargs = telegram_kwargs or {}
        tg_sent = _send_telegram_to(body_html, user.telegram_chat_id, **kwargs)

    if email_ok:
        plain = re.sub(r"<[^>]+>", "", body_html)
        email_sent = send_plain_email(user.email, subject, plain)

    return tg_sent, email_sent


def _send_auto_analysis(symbol: str, chat_id: str) -> None:
    """Background thread: generate AI Take and send as follow-up Telegram message.

    Never raises — silent failure to avoid disrupting alert flow.
    """
    try:
        from analytics.chart_analyzer import generate_alert_analysis

        ai_take = generate_alert_analysis(symbol, "5m")
        if ai_take:
            _send_telegram_to(f"<i>{ai_take}</i>", chat_id, parse_mode="HTML")
    except Exception:
        pass  # Silent failure — never disrupt alert flow


def notify_user(
    signal: AlertSignal, prefs: dict, alert_id: int | None = None,
) -> tuple[bool, bool]:
    """Send notifications to a specific user based on their preferences.

    *alert_id* — if provided, BUY/SELL Telegram messages include inline
    buttons for trade acknowledgement (Took It / Skip / Exited).

    Returns (email_sent, telegram_sent).
    """
    email_sent = False
    telegram_sent = False

    if prefs.get("email_enabled"):
        email_to = prefs.get("notification_email", "")
        if email_to:
            email_sent = send_email_to(signal, email_to)

    if prefs.get("telegram_enabled"):
        chat_id = prefs.get("telegram_chat_id", "")
        if chat_id:
            # Feature flag: when on, the triage-agent service owns Telegram
            # delivery (it sends a unified Pine + agent-context message via
            # LISTEN/NOTIFY). Email/SMS paths still run here.
            from alert_config import AGENT_OWNS_TELEGRAM
            if AGENT_OWNS_TELEGRAM:
                logger.info(
                    "notify_user: skipping Telegram for chat_id=%s — "
                    "AGENT_OWNS_TELEGRAM=true (triage-agent will deliver)", chat_id,
                )
            else:
                body = _format_sms_body(signal)
                if body is not None:
                    buttons = _build_trade_buttons(signal, alert_id)
                    telegram_sent = _send_telegram_to(body, chat_id, reply_markup=buttons)

                    # Auto-analysis follow-up: spawn background thread if enabled
                    if telegram_sent and prefs.get("auto_analysis_enabled"):
                        if signal.direction in ("BUY", "SHORT"):
                            thread = threading.Thread(
                                target=_send_auto_analysis,
                                args=(signal.symbol, chat_id),
                                daemon=True,
                            )
                            thread.start()
        else:
            logger.warning("notify_user: telegram_enabled but chat_id empty")
    else:
        logger.debug("notify_user: telegram_enabled=False, skipping")

    return email_sent, telegram_sent


def notify(signal: AlertSignal, alert_id: int | None = None) -> tuple[bool, bool]:
    """Send notifications for an alert signal (global fallback).

    Both email and Telegram are sent for ALL signals.
    If *alert_id* is provided, BUY/SELL Telegram messages include inline
    buttons for trade acknowledgement (Took It / Skip / Exited).

    Returns (email_sent, sms_sent).
    """
    email_sent = send_email(signal)
    sms_sent = False

    body = _format_sms_body(signal)
    if body is not None:
        # Telegram (with buttons if alert_id provided)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            buttons = _build_trade_buttons(signal, alert_id)
            if _send_telegram_to(body, TELEGRAM_CHAT_ID, reply_markup=buttons):
                sms_sent = True

        # Email-to-SMS gateway (always send alongside Telegram)
        if SMS_GATEWAY_TO:
            if _send_sms_via_email_gateway(body):
                sms_sent = True

    return email_sent, sms_sent
