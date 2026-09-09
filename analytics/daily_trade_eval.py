"""Daily trade evaluation — grade the fills you ACTUALLY took.

Distinct from analytics.eod_review, which reviews the alerts the system FIRED.
This reviews the trades you executed and joins them back to the alerts, so the
question it answers is "did I trade my plan?" rather than "did the scanner have
a good day?".

Three facts per session:
  - realized P&L, from the FIFO-matched round-trips closed today;
  - positions opened today and still held;
  - for every symbol traded, whether an alert fired for it today — an entry with
    no alert behind it is off-plan, and that is the number worth watching.

No protected business logic: this reads trade + alert history and writes a
Telegram message. It never fires an alert and never touches a rule.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from db import get_db, get_matched_trades, get_trades_monthly

logger = logging.getLogger(__name__)

_EVAL_MODEL = "claude-sonnet-4-20250514"
_MAX_PROMPT_ROWS = 40

_SYSTEM_PROMPT = """\
You are a direct trading coach reviewing a trader's ACTUAL executed trades for \
one session — not hypothetical signals.

Cover, in this order:
1. Scorecard (1 line): realized P&L, winners/losers, win rate
2. Best and worst trade, by name, with the number that made it so
3. Plan discipline: which entries had a scanner alert behind them and which did \
not. Off-plan entries are the headline if there are any.
4. One concrete, actionable change for tomorrow

Rules:
- Reference real symbols, prices and P&L figures from the data
- Under 200 words, plain text only, no markdown
- Do not invent trades or prices that are not in the data
- If discipline was clean, say so plainly rather than manufacturing a criticism"""


def _resolve_api_key() -> str:
    """Anthropic key: env first, then the per-user DB fallback.

    Mirrors analytics.eod_review so the master ANTHROPIC_ENABLED kill switch
    silences this job too.
    """
    from alert_config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED

    if not ANTHROPIC_ENABLED:
        return ""
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def _alerts_by_symbol(session_date: date) -> dict[str, list[dict]]:
    """Alerts that fired on this session, grouped by symbol.

    Used to decide whether a fill was signal-driven. Keyed on the bare ticker so
    an option fill on SPY matches a SPY alert via underlying_symbol.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol, alert_type, direction, entry, stop, target_1, score "
                "FROM alerts WHERE session_date=?",
                (session_date.isoformat(),),
            ).fetchall()
        for r in rows:
            out[str(r["symbol"]).upper()].append(dict(r))
    except Exception:
        logger.exception("daily eval: alert lookup failed for %s", session_date)
    return out


def collect_session_trades(user_id: int, session_date: date, account: str) -> dict:
    """Gather everything needed to evaluate one session. Pure data, no AI.

    Split out from the narrative so the numbers can be tested and rendered
    without an Anthropic call.
    """
    closed: list[dict] = []
    opened: list[dict] = []

    matched = get_matched_trades(user_id)
    if not matched.empty:
        same_day = matched[
            (matched["account"] == account)
            & (matched["sell_date"].astype(str) == session_date.isoformat())
        ]
        closed = same_day.to_dict("records")

    fills = get_trades_monthly(user_id, account=account)
    if not fills.empty:
        today_fills = fills[fills["trade_date"].dt.date == session_date]
        opened = today_fills[
            today_fills["transaction_type"].isin(["Buy", "BTO"])
        ].to_dict("records")

    realized = round(sum(float(t.get("realized_pnl") or 0) for t in closed), 2)
    winners = [t for t in closed if float(t.get("realized_pnl") or 0) > 0]
    losers = [t for t in closed if float(t.get("realized_pnl") or 0) < 0]

    alerts = _alerts_by_symbol(session_date)
    # An option fill's symbol is a contract key, so fall back to the underlying.
    def _had_alert(row: dict) -> bool:
        for key in (row.get("underlying_symbol"), row.get("symbol")):
            if key and str(key).upper() in alerts:
                return True
        return False

    on_plan = [t for t in opened if _had_alert(t)]
    off_plan = [t for t in opened if not _had_alert(t)]

    return {
        "session_date": session_date,
        "account": account,
        "closed": closed,
        "opened": opened,
        "realized_pnl": realized,
        "win_count": len(winners),
        "loss_count": len(losers),
        "win_rate": round(100 * len(winners) / len(closed), 1) if closed else 0.0,
        "on_plan": on_plan,
        "off_plan": off_plan,
        "alerts_by_symbol": alerts,
    }


def build_eval_prompt(data: dict) -> str:
    """Render the collected session data as the model's user message."""
    lines = [
        f"Session date: {data['session_date'].isoformat()}",
        f"Account: {data['account']}",
        "",
        "--- REALIZED (closed today) ---",
        f"Realized P&L: ${data['realized_pnl']:.2f} | "
        f"Winners: {data['win_count']} | Losers: {data['loss_count']} | "
        f"Win rate: {data['win_rate']}%",
    ]

    for t in data["closed"][:_MAX_PROMPT_ROWS]:
        lines.append(
            f"  {t.get('symbol')} qty {float(t.get('quantity') or 0):g} "
            f"buy ${float(t.get('buy_price') or 0):.2f} -> "
            f"sell ${float(t.get('sell_price') or 0):.2f} | "
            f"P&L ${float(t.get('realized_pnl') or 0):.2f} | "
            f"held {t.get('holding_days')}d"
        )
    if not data["closed"]:
        lines.append("  (nothing closed today)")

    lines += ["", "--- ENTRIES TAKEN TODAY ---"]
    for t in data["opened"][:_MAX_PROMPT_ROWS]:
        underlying = str(t.get("underlying_symbol") or t.get("symbol") or "").upper()
        matching = data["alerts_by_symbol"].get(underlying, [])
        if matching:
            a = matching[0]
            plan = (
                f"ALERT {a.get('alert_type')} "
                f"entry ${float(a.get('entry') or 0):.2f} "
                f"stop ${float(a.get('stop') or 0):.2f} "
                f"score {a.get('score')}"
            )
        else:
            plan = "NO ALERT — off-plan entry"
        lines.append(
            f"  {t.get('symbol')} {t.get('transaction_type')} "
            f"qty {float(t.get('quantity') or 0):g} @ ${float(t.get('price') or 0):.2f} | {plan}"
        )
    if not data["opened"]:
        lines.append("  (no entries taken today)")

    lines += [
        "",
        "--- DISCIPLINE ---",
        f"Entries with a scanner alert behind them: {len(data['on_plan'])}",
        f"Entries with no alert (off-plan): {len(data['off_plan'])}",
    ]
    return "\n".join(lines)


def build_daily_eval(user_id: int, session_date: date | None = None,
                     account: str = "Robinhood") -> str | None:
    """Build the session's trade evaluation. Returns None when there is nothing to say."""
    session_date = session_date or date.today()
    data = collect_session_trades(user_id, session_date, account)

    if not data["closed"] and not data["opened"]:
        logger.info("daily eval: no trades on %s", session_date)
        return None

    header = (
        f"TRADE REVIEW — {session_date.strftime('%b %d, %Y')}\n"
        f"Realized: ${data['realized_pnl']:.2f} | "
        f"{data['win_count']}W / {data['loss_count']}L | "
        f"Entries: {len(data['opened'])} ({len(data['off_plan'])} off-plan)"
    )

    api_key = _resolve_api_key()
    if not api_key:
        # Still worth sending: the numbers are the point, the narrative is a bonus.
        logger.info("daily eval: no Anthropic key — sending scorecard only")
        return header

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_EVAL_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_eval_prompt(data)}],
            timeout=30.0,
        )
        return f"{header}\n\n{response.content[0].text.strip()}"
    except Exception:
        logger.exception("daily eval: Claude call failed — falling back to scorecard")
        return header


def send_daily_eval(user_id: int, session_date: date | None = None,
                    account: str = "Robinhood") -> bool:
    """Build and deliver the evaluation over Telegram. True when sent."""
    review = build_daily_eval(user_id, session_date=session_date, account=account)
    if not review:
        return False
    try:
        from alerting.notifier import _send_telegram

        _send_telegram(review)
        return True
    except Exception:
        logger.exception("daily eval: Telegram delivery failed")
        return False
