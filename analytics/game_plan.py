"""Alert Sniper — Premarket Game Plan.

Generates a personalized "Top 3 Setups" for each user based on their watchlist.
Ranks by confluence score, distance to support, and R:R ratio.
Runs at 9:00 AM ET and delivers via Telegram + API.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

logger = logging.getLogger("game_plan")


def generate_game_plan(symbols: List[str], max_setups: int = 3) -> List[dict]:
    """Generate today's top setups from a symbol list.

    Returns a list of setup dicts sorted by composite score.
    """
    import sys
    from pathlib import Path

    # Ensure analytics is importable
    _root = str(Path(__file__).resolve().parents[1])
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from analytics.signal_engine import scan_watchlist, action_label
    from analytics.confluence import compute_confluence

    results = scan_watchlist(symbols)
    if not results:
        return []

    setups = []
    for r in results:
        # Only include actionable entries
        label = action_label(r.support_status, r.score)
        if label not in ("Potential Entry", "Watch"):
            continue

        # Compute confluence
        direction = getattr(r, "direction", "")
        if direction in ("Bullish", "LONG"):
            alert_dir = "BUY"
        elif direction in ("Bearish", "SHORT"):
            alert_dir = "SHORT"
        else:
            alert_dir = "BUY"  # default for entries

        try:
            conf_score, conf_label = compute_confluence(r.symbol, alert_dir)
        except Exception:
            conf_score, conf_label = 1, "Weak"

        # Composite ranking score
        # Confluence (0-3) * 30 + Score (0-100) * 0.3 + R:R bonus
        rr = getattr(r, "rr_ratio", 0) or 0
        composite = (conf_score * 30) + (r.score * 0.3) + (min(rr, 5) * 5)

        entry = getattr(r, "entry", None)
        stop = getattr(r, "stop", None)
        risk = abs(entry - stop) if entry and stop else None

        setups.append({
            "symbol": r.symbol,
            "direction": alert_dir,
            "action_label": label,
            "score": r.score,
            "confluence_score": conf_score,
            "confluence_label": conf_label,
            "entry": round(entry, 2) if entry else None,
            "stop": round(stop, 2) if stop else None,
            "target_1": round(r.target_1, 2) if r.target_1 else None,
            "target_2": round(r.target_2, 2) if r.target_2 else None,
            "rr_ratio": round(rr, 1) if rr else None,
            "risk_per_share": round(risk, 2) if risk else None,
            "support_status": r.support_status or "",
            "pattern": getattr(r, "pattern", ""),
            "bias": getattr(r, "bias", ""),
            "composite_score": round(composite, 1),
        })

    # Sort by composite score descending, take top N
    setups.sort(key=lambda x: x["composite_score"], reverse=True)
    return setups[:max_setups]


def format_game_plan_telegram(setups: List[dict]) -> str:
    """Format game plan as Telegram HTML message."""
    if not setups:
        return ""

    today = date.today().strftime("%b %d")
    lines = [f"🎯 <b>Today's Top {len(setups)} Setups — {today}</b>\n"]

    for i, s in enumerate(setups, 1):
        emoji = "🟢" if s["direction"] == "BUY" else "🔴"
        conf_bar = "●" * s["confluence_score"] + "○" * (3 - s["confluence_score"])

        lines.append(f"{emoji} <b>#{i} {s['symbol']}</b> — {s['direction']}")
        lines.append(f"   Entry ${s['entry']:.2f}  Stop ${s['stop']:.2f}  T1 ${s['target_1']:.2f}" if s["entry"] and s["stop"] and s["target_1"] else "")
        lines.append(f"   R:R {s['rr_ratio']}:1 · Score {s['score']} · Confluence [{conf_bar}]")
        if s.get("pattern"):
            lines.append(f"   {s['pattern']}")
        if s.get("bias"):
            lines.append(f"   <i>{s['bias']}</i>")
        lines.append("")

    lines.append("Focus on these. Ignore the noise. 🎯")

    return "\n".join(lines)


def send_game_plans(sync_session_factory) -> int:
    """Generate and send game plans to all Pro users via Telegram.

    Returns count of users who received a game plan.
    """
    from sqlalchemy import select, text
    from app.models.user import Subscription, User
    from app.models.watchlist import WatchlistItem

    count = 0

    with sync_session_factory() as db:
        # Get Pro users with Telegram enabled
        from datetime import datetime as _dt
        _now = _dt.utcnow()
        pro_users = db.execute(
            select(User.id, User.telegram_chat_id).join(Subscription).where(
                Subscription.status == "active",
                Subscription.tier.in_(["pro", "premium", "admin"]),
                User.telegram_chat_id.isnot(None),
                User.telegram_chat_id != "",
                User.telegram_enabled == 1,
            )
        ).fetchall()

        for user_id, chat_id in pro_users:
            # Get user's watchlist
            symbols = [
                row[0] for row in db.execute(
                    select(WatchlistItem.symbol).where(WatchlistItem.user_id == user_id)
                ).fetchall()
            ]
            if not symbols:
                continue

            try:
                setups = generate_game_plan(symbols)
                if not setups:
                    continue

                msg = format_game_plan_telegram(setups)
                if msg:
                    from alerting.notifier import _send_telegram_to
                    _send_telegram_to(msg, chat_id, parse_mode="HTML")
                    count += 1
                    logger.info("Game plan sent to user %d (%d setups)", user_id, len(setups))
            except Exception:
                logger.exception("Failed to send game plan to user %d", user_id)

    return count
