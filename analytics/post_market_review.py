"""Post-Market Review Agent — data-driven alert performance scorecard.

Runs after market close. For each BUY alert fired today, checks whether
T1 was hit, T2 was hit, or stop was hit first using actual intraday bars.
Sends a Telegram scorecard with win rate, best/worst rules, and per-alert outcomes.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import pytz

from alerting.alert_store import get_alerts_today, today_session
from alerting.notifier import _send_telegram_to, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analytics.intraday_data import fetch_intraday
from config import is_crypto_alert_symbol

logger = logging.getLogger("post_market_review")

ET = pytz.timezone("US/Eastern")

# Guard: only send once per session
_review_sent_date: str | None = None


def _fetch_bars_after_alert(symbol: str, alert_time_str: str) -> pd.DataFrame:
    """Fetch intraday bars and filter to bars AFTER the alert fired."""
    try:
        if is_crypto_alert_symbol(symbol):
            from analytics.intraday_data import fetch_intraday_crypto
            bars = fetch_intraday_crypto(symbol)
        else:
            bars = fetch_intraday(symbol)

        if bars.empty:
            return pd.DataFrame()

        # Parse alert time and filter to bars after it
        try:
            alert_time = pd.Timestamp(alert_time_str)
            # If alert_time is timezone-aware, strip it
            if alert_time.tz is not None:
                alert_time = alert_time.tz_localize(None)
            after = bars[bars.index >= alert_time]
            return after if not after.empty else bars
        except Exception:
            return bars
    except Exception:
        logger.debug("Failed to fetch bars for %s", symbol)
        return pd.DataFrame()


def _evaluate_alert_outcome(
    alert: dict, bars_after: pd.DataFrame,
) -> dict:
    """Check if T1, T2, or stop was hit first after the alert.

    Returns dict with:
      outcome: "t1_hit", "t2_hit", "stopped", "open" (still in play), "no_data"
      max_gain_pct: maximum gain from entry
      max_drawdown_pct: maximum drawdown from entry
      r_achieved: R multiple achieved (gain / risk)
    """
    entry = alert.get("entry")
    stop = alert.get("stop")
    t1 = alert.get("target_1")
    t2 = alert.get("target_2")

    result = {
        "outcome": "no_data",
        "max_gain_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "r_achieved": 0.0,
        "exit_price": None,
        "exit_time": None,
    }

    if not entry or bars_after.empty:
        return result

    risk = entry - stop if stop and stop > 0 else 0

    # Track max gain and drawdown
    max_high = bars_after["High"].max()
    min_low = bars_after["Low"].min()
    result["max_gain_pct"] = round((max_high - entry) / entry * 100, 2) if entry > 0 else 0
    result["max_drawdown_pct"] = round((entry - min_low) / entry * 100, 2) if entry > 0 else 0

    # Walk through bars chronologically to find first outcome
    for idx, bar in bars_after.iterrows():
        # Check stop hit first (conservative — if both hit in same bar, stop wins)
        if stop and bar["Low"] <= stop:
            result["outcome"] = "stopped"
            result["exit_price"] = stop
            result["exit_time"] = str(idx)
            if risk > 0:
                result["r_achieved"] = round(-1.0, 2)
            break

        # Check T1 hit
        if t1 and bar["High"] >= t1:
            result["outcome"] = "t1_hit"
            result["exit_price"] = t1
            result["exit_time"] = str(idx)
            if risk > 0:
                result["r_achieved"] = round((t1 - entry) / risk, 2)
            # Check T2 in remaining bars
            remaining = bars_after[bars_after.index > idx]
            if t2 and not remaining.empty and remaining["High"].max() >= t2:
                result["outcome"] = "t2_hit"
                result["exit_price"] = t2
                if risk > 0:
                    result["r_achieved"] = round((t2 - entry) / risk, 2)
            break
    else:
        # Neither stop nor T1 hit — still open
        last_close = bars_after.iloc[-1]["Close"]
        result["outcome"] = "open"
        result["exit_price"] = last_close
        if risk > 0:
            result["r_achieved"] = round((last_close - entry) / risk, 2)

    return result


def build_review(session_date: str | None = None, user_id: int | None = None) -> str | None:
    """Build the post-market review scorecard.

    Returns formatted text for Telegram, or None if no alerts.
    """
    session = session_date or today_session()
    alerts = get_alerts_today(session, user_id=user_id)

    # Filter to BUY alerts with entry/stop/targets
    buy_alerts = [
        a for a in alerts
        if a.get("direction") == "BUY"
        and a.get("entry")
        and a.get("stop")
        and a.get("target_1")
    ]

    sell_alerts = [a for a in alerts if a.get("direction") == "SELL"]
    notice_alerts = [a for a in alerts if a.get("direction") == "NOTICE"]

    if not buy_alerts and not sell_alerts:
        return None

    # Evaluate each BUY alert
    results = []
    for alert in buy_alerts:
        bars = _fetch_bars_after_alert(alert["symbol"], alert.get("created_at", ""))
        outcome = _evaluate_alert_outcome(alert, bars)
        results.append({
            "symbol": alert["symbol"],
            "alert_type": alert["alert_type"],
            "entry": alert["entry"],
            "stop": alert["stop"],
            "t1": alert["target_1"],
            "score": alert.get("score", 0),
            "user_action": alert.get("user_action", ""),
            **outcome,
        })

    # Calculate stats
    wins = [r for r in results if r["outcome"] in ("t1_hit", "t2_hit")]
    losses = [r for r in results if r["outcome"] == "stopped"]
    open_trades = [r for r in results if r["outcome"] == "open"]
    total_decided = len(wins) + len(losses)
    win_rate = (len(wins) / total_decided * 100) if total_decided > 0 else 0
    avg_r = sum(r["r_achieved"] for r in results if r["outcome"] != "no_data") / max(len(results), 1)

    # Stats by alert type
    type_stats: dict[str, dict] = {}
    for r in results:
        at = r["alert_type"].replace("_", " ").title()
        if at not in type_stats:
            type_stats[at] = {"wins": 0, "losses": 0, "total": 0}
        type_stats[at]["total"] += 1
        if r["outcome"] in ("t1_hit", "t2_hit"):
            type_stats[at]["wins"] += 1
        elif r["outcome"] == "stopped":
            type_stats[at]["losses"] += 1

    # Build Telegram message
    lines = []
    lines.append(f"<b>POST-MARKET REVIEW — {session}</b>")
    lines.append("")
    lines.append(
        f"Today: {len(buy_alerts)} BUY | {len(sell_alerts)} SELL | "
        f"{len(notice_alerts)} NOTICE"
    )
    lines.append(
        f"Outcomes: {len(wins)} wins | {len(losses)} losses | "
        f"{len(open_trades)} open"
    )
    if total_decided > 0:
        lines.append(f"<b>Win Rate: {win_rate:.0f}%</b> | Avg R: {avg_r:.1f}R")
    lines.append("")

    # Winners
    if wins:
        lines.append("<b>WINNERS</b>")
        for r in wins:
            label = r["alert_type"].replace("_", " ").title()
            took = " (TOOK)" if r["user_action"] == "took" else ""
            lines.append(
                f"  {r['symbol']} {label} ${r['entry']:.2f} → "
                f"${r['exit_price']:.2f} ({r['r_achieved']:.1f}R){took}"
            )
        lines.append("")

    # Losers
    if losses:
        lines.append("<b>LOSERS</b>")
        for r in losses:
            label = r["alert_type"].replace("_", " ").title()
            took = " (TOOK)" if r["user_action"] == "took" else ""
            lines.append(
                f"  {r['symbol']} {label} ${r['entry']:.2f} → "
                f"Stop ${r['exit_price']:.2f} (-1R){took}"
            )
        lines.append("")

    # Still open
    if open_trades:
        lines.append("<b>OPEN (no T1/stop hit)</b>")
        for r in open_trades:
            label = r["alert_type"].replace("_", " ").title()
            pnl = f"+{r['max_gain_pct']:.1f}%" if r["r_achieved"] >= 0 else f"{r['max_gain_pct']:.1f}%"
            lines.append(
                f"  {r['symbol']} {label} ${r['entry']:.2f} — "
                f"max gain {r['max_gain_pct']:.1f}%, max DD {r['max_drawdown_pct']:.1f}%"
            )
        lines.append("")

    # Best/worst rule types
    if type_stats:
        best = max(type_stats.items(), key=lambda x: x[1]["wins"] / max(x[1]["total"], 1))
        worst = min(type_stats.items(), key=lambda x: x[1]["wins"] / max(x[1]["total"], 1))
        if best[1]["total"] > 0:
            best_wr = best[1]["wins"] / best[1]["total"] * 100
            lines.append(f"<b>BEST RULE:</b> {best[0]} ({best_wr:.0f}% win rate, {best[1]['total']} signals)")
        if worst[1]["total"] > 0 and worst[0] != best[0]:
            worst_wr = worst[1]["wins"] / worst[1]["total"] * 100
            lines.append(f"<b>WORST RULE:</b> {worst[0]} ({worst_wr:.0f}% win rate, {worst[1]['total']} signals)")

    return "\n".join(lines)


def send_post_market_review(user_id: int | None = None) -> bool:
    """Send the post-market review via Telegram (once per day)."""
    global _review_sent_date

    session = today_session()
    if _review_sent_date == session:
        logger.debug("Post-market review already sent for %s", session)
        return False

    review = build_review(session, user_id=user_id)
    if not review:
        logger.info("Post-market review: no alerts to review for %s", session)
        return False

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Post-market review: Telegram not configured")
        return False

    sent = _send_telegram_to(review, TELEGRAM_CHAT_ID, parse_mode="HTML")
    if sent:
        _review_sent_date = session
        logger.info("Post-market review sent for %s", session)
    return sent
