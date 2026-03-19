"""Alert Tuning Agent — weekly analysis of alert performance with threshold suggestions.

Runs weekly (Sunday EOD or Monday pre-market). Analyzes the past week's alerts
to calculate per-rule win rates, then suggests config threshold changes for
underperforming rules.

Sends a Telegram report with:
- Per-rule win rate and signal count
- Specific threshold suggestions for underperforming rules
- Rules to consider disabling
- Rules performing well (keep as-is)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz

from alerting.alert_store import get_alerts_today, get_session_dates, today_session
from alerting.notifier import _send_telegram_to, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analytics.post_market_review import _fetch_bars_after_alert, _evaluate_alert_outcome

logger = logging.getLogger("alert_tuner")

ET = pytz.timezone("US/Eastern")

# Guard: only send once per week
_tuner_sent_week: str | None = None

# Thresholds for suggestions
MIN_SIGNALS_FOR_ANALYSIS = 3  # need at least 3 signals to judge a rule
POOR_WIN_RATE = 0.35  # below 35% = suggest tightening
GOOD_WIN_RATE = 0.60  # above 60% = performing well
GREAT_WIN_RATE = 0.75  # above 75% = highlight as best

# Map alert types to tunable config parameters
_TUNING_MAP: dict[str, list[str]] = {
    "ma_bounce_20": ["MA_BOUNCE_PROXIMITY_PCT (currently 0.5%)", "consider tightening to 0.4%"],
    "ma_bounce_50": ["MA_BOUNCE_PROXIMITY_PCT (currently 0.5%)", "consider tightening to 0.4%"],
    "ma_bounce_100": ["MA100_BOUNCE_PROXIMITY_PCT (currently 0.7%)", "consider tightening to 0.5%"],
    "ma_bounce_200": ["MA200_BOUNCE_PROXIMITY_PCT (currently 1.0%)", "consider tightening to 0.8%"],
    "ema_bounce_20": ["MA_BOUNCE_PROXIMITY_PCT (currently 0.5%)", "consider tightening to 0.4%"],
    "ema_bounce_50": ["MA_BOUNCE_PROXIMITY_PCT (currently 0.5%)", "consider tightening to 0.4%"],
    "ema_bounce_100": ["MA100_BOUNCE_PROXIMITY_PCT (currently 0.7%)", "consider tightening to 0.5%"],
    "ema_bounce_200": ["MA200_BOUNCE_PROXIMITY_PCT (currently 1.0%)", "consider tightening to 0.8%"],
    "prior_day_low_reclaim": ["PDL_RECLAIM_MAX_DISTANCE_PCT (currently 2.0%)", "consider tightening to 1.5%"],
    "prior_day_low_bounce": ["PDL_BOUNCE_PROXIMITY_PCT (currently 0.5%)", "consider tightening to 0.3%"],
    "prior_day_high_breakout": ["PDH_BREAKOUT_VOLUME_RATIO (currently 0.8x)", "consider raising to 1.0x"],
    "intraday_support_bounce": ["SUPPORT_BOUNCE_PROXIMITY_PCT", "consider tightening proximity"],
    "session_low_double_bottom": ["SESSION_LOW_PROXIMITY_PCT", "consider requiring more recovery bars"],
    "vwap_reclaim": ["VWAP_RECLAIM_VOLUME_RATIO (currently 1.2x)", "consider raising volume threshold"],
    "vwap_bounce": ["VWAP_BOUNCE_TOUCH_PCT", "consider tightening touch proximity"],
    "opening_low_base": ["OPENING_LOW_BASE_HOLD_BARS", "consider requiring more hold bars"],
    "morning_low_retest": ["MORNING_LOW_RETEST_RALLY_PCT (currently 0.5%)", "consider raising to 0.7%"],
    "planned_level_touch": ["Planned level quality", "review scanner accuracy"],
}


def _get_week_sessions(lookback_days: int = 7) -> list[str]:
    """Get session dates for the past N days."""
    all_dates = get_session_dates()
    if not all_dates:
        return []

    cutoff = (datetime.now(ET) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    return [d for d in all_dates if d >= cutoff]


def build_weekly_tuning_report(lookback_days: int = 7) -> str | None:
    """Analyze the past week's alerts and suggest threshold changes.

    Returns formatted Telegram message or None if insufficient data.
    """
    sessions = _get_week_sessions(lookback_days)
    if not sessions:
        return None

    # Collect all BUY alerts from the past week
    all_results: list[dict] = []
    for session in sessions:
        alerts = get_alerts_today(session)
        buy_alerts = [
            a for a in alerts
            if a.get("direction") == "BUY"
            and a.get("entry")
            and a.get("stop")
            and a.get("target_1")
        ]

        for alert in buy_alerts:
            bars = _fetch_bars_after_alert(alert["symbol"], alert.get("created_at", ""))
            outcome = _evaluate_alert_outcome(alert, bars)
            all_results.append({
                "symbol": alert["symbol"],
                "alert_type": alert["alert_type"],
                "session": session,
                "user_action": alert.get("user_action", ""),
                **outcome,
            })

    if not all_results:
        return None

    # Aggregate by alert type
    type_stats: dict[str, dict] = {}
    for r in all_results:
        at = r["alert_type"]
        if at not in type_stats:
            type_stats[at] = {"wins": 0, "losses": 0, "open": 0, "total": 0, "r_sum": 0.0, "took": 0}
        type_stats[at]["total"] += 1
        if r["outcome"] in ("t1_hit", "t2_hit"):
            type_stats[at]["wins"] += 1
        elif r["outcome"] == "stopped":
            type_stats[at]["losses"] += 1
        else:
            type_stats[at]["open"] += 1
        if r["outcome"] != "no_data":
            type_stats[at]["r_sum"] += r["r_achieved"]
        if r["user_action"] == "took":
            type_stats[at]["took"] += 1

    # Overall stats
    total_signals = len(all_results)
    total_wins = sum(s["wins"] for s in type_stats.values())
    total_losses = sum(s["losses"] for s in type_stats.values())
    total_decided = total_wins + total_losses
    overall_wr = (total_wins / total_decided * 100) if total_decided > 0 else 0

    # Build report
    lines = []
    lines.append(f"<b>WEEKLY ALERT TUNING REPORT</b>")
    lines.append(f"Period: {sessions[-1]} to {sessions[0]} ({len(sessions)} sessions)")
    lines.append(f"Total: {total_signals} BUY alerts | {total_wins}W {total_losses}L")
    if total_decided > 0:
        lines.append(f"<b>Overall Win Rate: {overall_wr:.0f}%</b>")
    lines.append("")

    # Sort rules by win rate (worst first)
    sorted_rules = sorted(
        type_stats.items(),
        key=lambda x: x[1]["wins"] / max(x[1]["wins"] + x[1]["losses"], 1),
    )

    # Poor performers — suggest tightening
    poor = []
    for at, stats in sorted_rules:
        decided = stats["wins"] + stats["losses"]
        if decided < MIN_SIGNALS_FOR_ANALYSIS:
            continue
        wr = stats["wins"] / decided
        if wr < POOR_WIN_RATE:
            poor.append((at, stats, wr))

    if poor:
        lines.append("<b>UNDERPERFORMING (suggest tightening):</b>")
        for at, stats, wr in poor:
            label = at.replace("_", " ").title()
            decided = stats["wins"] + stats["losses"]
            avg_r = stats["r_sum"] / max(stats["total"], 1)
            lines.append(f"  {label}: {wr:.0%} win rate ({stats['wins']}W/{stats['losses']}L, {stats['total']} signals)")
            if at in _TUNING_MAP:
                param, suggestion = _TUNING_MAP[at]
                lines.append(f"    → Tune: {param}")
                lines.append(f"    → Action: {suggestion}")
            else:
                lines.append(f"    → Review rule thresholds")
        lines.append("")

    # Good performers — keep as-is
    good = []
    for at, stats in sorted_rules:
        decided = stats["wins"] + stats["losses"]
        if decided < MIN_SIGNALS_FOR_ANALYSIS:
            continue
        wr = stats["wins"] / decided
        if wr >= GOOD_WIN_RATE:
            good.append((at, stats, wr))

    if good:
        lines.append("<b>PERFORMING WELL (keep current settings):</b>")
        for at, stats, wr in good:
            label = at.replace("_", " ").title()
            avg_r = stats["r_sum"] / max(stats["total"], 1)
            emoji = "🔥" if wr >= GREAT_WIN_RATE else "✅"
            lines.append(f"  {emoji} {label}: {wr:.0%} ({stats['wins']}W/{stats['losses']}L, avg {avg_r:.1f}R)")
        lines.append("")

    # Low sample — need more data
    low_sample = [(at, s) for at, s in type_stats.items()
                  if s["wins"] + s["losses"] < MIN_SIGNALS_FOR_ANALYSIS and s["total"] >= 1]
    if low_sample:
        lines.append("<b>LOW SAMPLE (need more data):</b>")
        for at, stats in low_sample:
            label = at.replace("_", " ").title()
            lines.append(f"  {label}: {stats['total']} signals ({stats['wins']}W/{stats['losses']}L)")

    # Rules that were "took" but lost
    took_losses = [r for r in all_results if r["user_action"] == "took" and r["outcome"] == "stopped"]
    if took_losses:
        lines.append("")
        lines.append(f"<b>TRADES YOU TOOK THAT LOST: {len(took_losses)}</b>")
        for r in took_losses[:5]:
            label = r["alert_type"].replace("_", " ").title()
            lines.append(f"  {r['symbol']} {label} ({r['session']})")

    return "\n".join(lines)


def send_weekly_tuning_report() -> bool:
    """Send the weekly tuning report via Telegram (once per week)."""
    global _tuner_sent_week

    now = datetime.now(ET)
    week_key = now.strftime("%Y-W%W")
    if _tuner_sent_week == week_key:
        logger.debug("Weekly tuning report already sent for %s", week_key)
        return False

    report = build_weekly_tuning_report()
    if not report:
        logger.info("Weekly tuning: no data for report")
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    sent = _send_telegram_to(report, TELEGRAM_CHAT_ID, parse_mode="HTML")
    if sent:
        _tuner_sent_week = week_key
        logger.info("Weekly tuning report sent for %s", week_key)
    return sent
