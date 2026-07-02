"""Daily auto-focus agent — star each user's best setups automatically.

Every morning this scans every user's watchlist, ranks the symbols by the
daily-plan score already computed by the scanner (analytics/signal_engine.py),
and marks the top N as "focus" so they surface first in the Trading-page
sidebar (and the mobile watchlist drawer).

Design notes
------------
* **Source of scores** — we reuse `daily_plans.score` (the 0–100 score from
  `compute_signal_score`: pattern + MA position + support proximity + volume).
  No new scoring or LLM call; the scanner is the single source of truth.
* **Manual stars are sacred** — focus has a `focus_source` column
  ('manual' | 'auto'). The agent only ever clears/sets its OWN 'auto' rows, so a
  symbol the user starred by hand is never overwritten or cleared (see
  `db.clear_auto_focus` / `db.set_auto_focus`).
* **Quality floor** — `min_score` (default 60 = "Moderate"+) means a flat
  market day can yield fewer than N picks rather than starring weak setups.
* **Idempotent** — re-running for the same session replaces the prior auto
  picks; manual focus and counts stay stable.

Run manually / from a scheduler::

    python -m analytics.auto_focus                 # today, top 5, score>=60
    python -m analytics.auto_focus --dry-run       # show picks, change nothing
    python -m analytics.auto_focus --date 2026-06-26 --top 3 --min-score 70
"""

from __future__ import annotations

import argparse
import logging
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 5
DEFAULT_MIN_SCORE = 60


def select_top_setups(
    symbols: Sequence[str],
    scores: Mapping[str, int],
    top_n: int = DEFAULT_TOP_N,
    min_score: int = DEFAULT_MIN_SCORE,
) -> list[str]:
    """Return the top `top_n` symbols by score, highest first.

    Only symbols whose score is >= `min_score` qualify. Ties are broken by
    symbol (A→Z) so the selection is deterministic. Pure function — no DB.
    """
    qualified = [
        (sym, int(scores.get(sym, 0) or 0))
        for sym in symbols
        if int(scores.get(sym, 0) or 0) >= min_score
    ]
    qualified.sort(key=lambda pair: (-pair[1], pair[0]))
    return [sym for sym, _ in qualified[:top_n]]


def format_top5_message(picks_detail: Sequence[Mapping], app_url: str | None = None) -> str:
    """Build the per-user "Top setups" Telegram digest.

    `picks_detail` is a list of daily-plan dicts (symbol, score, entry, stop,
    target_1, ...) for the user's picks, best first. Framed as setups to
    evaluate — explicitly NOT a buy instruction.
    """
    n = len(picks_detail)
    header = f"⭐ Today's Top {n} Setup{'s' if n != 1 else ''}"
    lines = [
        header,
        "",
        "Watchlist names showing the strongest setups right now — worth your "
        "attention, not a buy signal. Do your own evaluation before acting.",
        "",
    ]
    for p in picks_detail:
        sym = p.get("symbol", "")
        score = p.get("score")
        seg = f"• {sym}" + (f"  ·  score {score}" if score is not None else "")
        entry, stop = p.get("entry"), p.get("stop")
        if entry and stop:
            seg += f"  ·  entry ~${float(entry):.2f}, stop ${float(stop):.2f}"
        lines.append(seg)
    if app_url:
        lines += ["", f"Open the app → {app_url}"]
    return "\n".join(lines)


def _notify_user(user_id: int, picks: Sequence[str], plans_by_symbol: Mapping[str, Mapping]) -> bool:
    """Send a user their "Top setups" digest if they have Telegram enabled."""
    import db

    tg = db.get_user_telegram(user_id)
    if not tg or not tg.get("enabled") or not tg.get("chat_id"):
        return False

    detail = [plans_by_symbol.get(sym, {"symbol": sym}) for sym in picks]
    try:
        from alerting.notifier import _get_app_url, _send_telegram_to
        body = format_top5_message(detail, _get_app_url())
        return bool(_send_telegram_to(body, tg["chat_id"]))
    except Exception:
        logger.exception("auto_focus: failed to notify user %d", user_id)
        return False


def apply_for_user(
    user_id: int,
    scores: Mapping[str, int],
    top_n: int = DEFAULT_TOP_N,
    min_score: int = DEFAULT_MIN_SCORE,
    dry_run: bool = False,
) -> dict:
    """Refresh one user's auto-focus picks. Returns a per-user summary dict."""
    import db

    rows = db.get_watchlist_focus(user_id)
    symbols = [r["symbol"] for r in rows]
    picks = select_top_setups(symbols, scores, top_n, min_score)

    summary = {
        "user_id": user_id,
        "watchlist_size": len(symbols),
        "picks": picks,
        "auto_set": [],
        "applied": not dry_run,
        "notified": False,
    }
    if dry_run:
        return summary

    db.clear_auto_focus(user_id)
    summary["auto_set"] = [sym for sym in picks if db.set_auto_focus(user_id, sym)]
    return summary


def run(
    session_date: str | None = None,
    top_n: int = DEFAULT_TOP_N,
    min_score: int = DEFAULT_MIN_SCORE,
    dry_run: bool = False,
    notify: bool = False,
) -> dict:
    """Run the agent across every user with a watchlist.

    `session_date` defaults to the most recent date present in daily_plans
    (so it works whether invoked pre-open or intraday). When `notify` is True,
    each user who got picks AND has Telegram enabled receives a "Top setups"
    digest. Returns a summary.
    """
    import db

    if session_date is None:
        session_date = db.get_latest_daily_plan_date()
    if not session_date:
        logger.warning("auto_focus: no daily plans found — nothing to focus")
        return {"session_date": None, "users": 0, "total_auto": 0, "notified": 0, "results": []}

    plans = db.get_all_daily_plans(session_date)
    plans_by_symbol = {p["symbol"]: p for p in plans}
    scores = {sym: int(p.get("score") or 0) for sym, p in plans_by_symbol.items()}

    results = []
    for uid in db.get_user_ids_with_watchlist():
        r = apply_for_user(uid, scores, top_n, min_score, dry_run)
        if notify and not dry_run and r["picks"]:
            r["notified"] = _notify_user(uid, r["picks"], plans_by_symbol)
        results.append(r)

    total_auto = sum(len(r["auto_set"]) for r in results)
    notified = sum(1 for r in results if r.get("notified"))
    logger.info(
        "auto_focus: session=%s users=%d auto_focused=%d notified=%d "
        "(top_n=%d, min_score=%d, dry_run=%s, notify=%s)",
        session_date, len(results), total_auto, notified, top_n, min_score, dry_run, notify,
    )
    return {
        "session_date": session_date,
        "users": len(results),
        "total_auto": total_auto,
        "notified": notified,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Daily auto-focus: star the top setups on each user's watchlist.",
    )
    parser.add_argument("--date", help="Session date YYYY-MM-DD (default: most recent plans)")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="How many to focus per user")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE, help="Minimum score to qualify")
    parser.add_argument("--dry-run", action="store_true", help="Show picks without writing")
    parser.add_argument("--notify", action="store_true", help="Send each user a Telegram 'Top setups' digest")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import db
    db.init_db()
    summary = run(args.date, args.top, args.min_score, args.dry_run, args.notify)

    verb = "Would focus" if args.dry_run else "Focused"
    print(f"\nAuto-focus — session {summary['session_date']} ({summary['users']} users)")
    for r in summary["results"]:
        picks = ", ".join(r["picks"]) or "—"
        flag = "  📲 notified" if r.get("notified") else ""
        print(f"  user {r['user_id']:>4}: {verb} {picks}{flag}")
    print(f"\nTotal auto-focused: {summary['total_auto']}  ·  notified: {summary.get('notified', 0)}\n")


if __name__ == "__main__":
    main()
