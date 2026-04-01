"""Monthly trade journal report — generates PDF/text summary of all trades."""

from __future__ import annotations

from datetime import datetime
from db import get_db


def get_monthly_trades(year: int, month: int, user_id: int | None = None) -> dict:
    """Get all trades and alerts for a given month.

    Returns dict with:
      - took_trades: list of real_trades (ACK'd entries with entry/exit/P&L)
      - skipped_alerts: list of alerts that were skipped (not ACK'd)
      - summary: aggregate stats
    """
    month_start = f"{year}-{month:02d}-01"
    if month == 12:
        month_end = f"{year + 1}-01-01"
    else:
        month_end = f"{year}-{month + 1:02d}-01"

    with get_db() as conn:
        # All trades (Took It) for the month
        took_trades = conn.execute(
            """SELECT * FROM real_trades
               WHERE session_date >= ? AND session_date < ?
               ORDER BY opened_at""",
            (month_start, month_end),
        ).fetchall()

        # All alerts for the month (for skip tracking)
        all_alerts = conn.execute(
            """SELECT * FROM alerts
               WHERE session_date >= ? AND session_date < ?
               AND direction IN ('BUY', 'SHORT')
               ORDER BY created_at""",
            (month_start, month_end),
        ).fetchall()

    took_trades = [dict(t) for t in took_trades]
    all_alerts = [dict(a) for a in all_alerts]

    # Find skipped alerts (alerts with no matching real_trade)
    took_alert_ids = {t.get("alert_id") for t in took_trades if t.get("alert_id")}
    skipped_alerts = [a for a in all_alerts if a.get("id") not in took_alert_ids]

    # Compute summary
    closed_trades = [t for t in took_trades if t.get("status") == "closed"]
    open_trades = [t for t in took_trades if t.get("status") == "open"]
    winners = [t for t in closed_trades if (t.get("pnl") or 0) > 0]
    losers = [t for t in closed_trades if (t.get("pnl") or 0) < 0]
    total_pnl = sum(t.get("pnl", 0) or 0 for t in closed_trades)

    # Per-pattern breakdown
    pattern_stats: dict[str, dict] = {}
    for t in closed_trades:
        pat = t.get("alert_type", "unknown")
        if pat not in pattern_stats:
            pattern_stats[pat] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
        pnl = t.get("pnl", 0) or 0
        if pnl > 0:
            pattern_stats[pat]["wins"] += 1
        elif pnl < 0:
            pattern_stats[pat]["losses"] += 1
        pattern_stats[pat]["total_pnl"] += pnl

    # Per-day breakdown
    daily_pnl: dict[str, float] = {}
    for t in closed_trades:
        day = t.get("session_date", "unknown")
        daily_pnl[day] = daily_pnl.get(day, 0) + (t.get("pnl", 0) or 0)

    summary = {
        "total_trades": len(took_trades),
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": len(winners) / len(closed_trades) * 100 if closed_trades else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(sum(t.get("pnl", 0) or 0 for t in winners) / len(winners), 2) if winners else 0,
        "avg_loss": round(sum(t.get("pnl", 0) or 0 for t in losers) / len(losers), 2) if losers else 0,
        "total_skipped": len(skipped_alerts),
        "pattern_stats": pattern_stats,
        "daily_pnl": daily_pnl,
    }

    return {
        "took_trades": took_trades,
        "skipped_alerts": skipped_alerts,
        "summary": summary,
    }


def format_monthly_report(year: int, month: int, user_id: int | None = None) -> str:
    """Generate a text-based monthly trade journal report."""
    data = get_monthly_trades(year, month, user_id)
    s = data["summary"]
    month_name = datetime(year, month, 1).strftime("%B %Y")

    lines = [
        f"{'=' * 60}",
        f"  TRADE JOURNAL — {month_name}",
        f"{'=' * 60}",
        "",
        f"Total Trades Taken:  {s['total_trades']}",
        f"Closed:              {s['closed_trades']}",
        f"Open:                {s['open_trades']}",
        f"Winners:             {s['winners']}",
        f"Losers:              {s['losers']}",
        f"Win Rate:            {s['win_rate']:.1f}%",
        f"Total P&L:           ${s['total_pnl']:+,.2f}",
        f"Avg Win:             ${s['avg_win']:+,.2f}",
        f"Avg Loss:            ${s['avg_loss']:+,.2f}",
        f"Alerts Skipped:      {s['total_skipped']}",
        "",
    ]

    # Pattern breakdown
    if s["pattern_stats"]:
        lines.append(f"{'─' * 60}")
        lines.append("  PATTERN PERFORMANCE")
        lines.append(f"{'─' * 60}")
        lines.append(f"{'Pattern':<30} {'W':>4} {'L':>4} {'Win%':>6} {'P&L':>10}")
        for pat, stats in sorted(s["pattern_stats"].items(),
                                  key=lambda x: x[1]["total_pnl"], reverse=True):
            total = stats["wins"] + stats["losses"]
            wr = stats["wins"] / total * 100 if total > 0 else 0
            name = pat.replace("_", " ").title()[:29]
            lines.append(
                f"{name:<30} {stats['wins']:>4} {stats['losses']:>4} "
                f"{wr:>5.0f}% ${stats['total_pnl']:>+9,.2f}"
            )
        lines.append("")

    # Daily P&L
    if s["daily_pnl"]:
        lines.append(f"{'─' * 60}")
        lines.append("  DAILY P&L")
        lines.append(f"{'─' * 60}")
        cumulative = 0.0
        for day in sorted(s["daily_pnl"].keys()):
            pnl = s["daily_pnl"][day]
            cumulative += pnl
            lines.append(f"  {day}  ${pnl:>+9,.2f}  (cumulative: ${cumulative:>+9,.2f})")
        lines.append("")

    # Trade log
    lines.append(f"{'─' * 60}")
    lines.append("  TRADE LOG (Took It)")
    lines.append(f"{'─' * 60}")
    for t in data["took_trades"]:
        status = t.get("status", "?")
        pnl = t.get("pnl")
        pnl_str = f"${pnl:+,.2f}" if pnl is not None else "open"
        direction = t.get("direction", "?")
        lines.append(
            f"  {t.get('session_date', '?')} | {direction:<5} {t.get('symbol', '?'):<6} "
            f"| Entry ${t.get('entry_price', 0):.2f} "
            f"| Exit ${t.get('exit_price', 0) or 0:.2f} "
            f"| {pnl_str:<12} "
            f"| {t.get('alert_type', '?')}"
        )

    # Skipped alerts summary
    if data["skipped_alerts"]:
        lines.append("")
        lines.append(f"{'─' * 60}")
        lines.append(f"  SKIPPED ALERTS ({s['total_skipped']} total)")
        lines.append(f"{'─' * 60}")
        # Group by pattern
        skip_by_type: dict[str, int] = {}
        for a in data["skipped_alerts"]:
            at = a.get("alert_type", "unknown")
            skip_by_type[at] = skip_by_type.get(at, 0) + 1
        for at, count in sorted(skip_by_type.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {at.replace('_', ' ').title():<35} {count:>3}x skipped")

    lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"{'=' * 60}")

    return "\n".join(lines)
