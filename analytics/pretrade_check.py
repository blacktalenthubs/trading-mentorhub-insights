"""Pre-trade Checklist — quick conviction assessment before taking a trade.

Runs 6 structural checks and returns pass/warn/fail for each,
plus an AI synthesis with overall conviction score.
"""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def run_pretrade_check(symbol: str, direction: str, entry: float,
                       stop: float, target: float) -> dict:
    """Run pre-trade checklist for a proposed trade.

    Returns dict with:
      checks: list of {name, status, detail}
      conviction: 1-10 score
      summary: AI-generated 1-2 sentence synthesis
    """
    checks = []

    # 1. Structure check — is the level real?
    try:
        from analytics.intraday_data import fetch_prior_day, fetch_intraday
        prior = fetch_prior_day(symbol)
        intraday = fetch_intraday(symbol)

        if prior:
            pdh = prior.get("high", 0)
            pdl = prior.get("low", 0)
            near_pdl = abs(entry - pdl) / entry < 0.005
            near_pdh = abs(entry - pdh) / entry < 0.005
            near_ma = False
            for ma in ["ema20", "ema50", "ema100", "ema200", "ma20", "ma50"]:
                val = prior.get(ma, 0)
                if val and abs(entry - val) / entry < 0.005:
                    near_ma = True
                    break

            if near_pdl or near_pdh or near_ma:
                checks.append({"name": "Structure", "status": "pass", "detail": "Entry near a key structural level"})
            else:
                checks.append({"name": "Structure", "status": "warn", "detail": "Entry not near PDH/PDL/MA — no clear structural basis"})
        else:
            checks.append({"name": "Structure", "status": "warn", "detail": "Could not fetch prior day data"})
    except Exception:
        checks.append({"name": "Structure", "status": "warn", "detail": "Check failed"})

    # 2. Volume check
    try:
        if intraday is not None and not intraday.empty:
            avg_vol = intraday["Volume"].mean()
            last_vol = float(intraday.iloc[-1]["Volume"])
            ratio = last_vol / avg_vol if avg_vol > 0 else 1
            if ratio >= 1.2:
                checks.append({"name": "Volume", "status": "pass", "detail": f"{ratio:.1f}x average — buyers/sellers active"})
            elif ratio >= 0.8:
                checks.append({"name": "Volume", "status": "warn", "detail": f"{ratio:.1f}x average — normal volume"})
            else:
                checks.append({"name": "Volume", "status": "fail", "detail": f"{ratio:.1f}x average — thin volume, low conviction"})
        else:
            checks.append({"name": "Volume", "status": "warn", "detail": "No intraday data"})
    except Exception:
        checks.append({"name": "Volume", "status": "warn", "detail": "Check failed"})

    # 3. SPY regime check
    try:
        from analytics.intraday_data import get_spy_context
        spy = get_spy_context()
        regime = spy.get("regime", "UNKNOWN")
        trend = spy.get("trend", "neutral")

        if direction == "BUY" and trend == "bullish":
            checks.append({"name": "Regime", "status": "pass", "detail": f"SPY {regime} — bullish regime supports longs"})
        elif direction == "SHORT" and trend == "bearish":
            checks.append({"name": "Regime", "status": "pass", "detail": f"SPY {regime} — bearish regime supports shorts"})
        elif trend == "neutral":
            checks.append({"name": "Regime", "status": "warn", "detail": f"SPY {regime} — neutral, proceed with caution"})
        else:
            checks.append({"name": "Regime", "status": "fail", "detail": f"SPY {regime} ({trend}) — trading against market direction"})
    except Exception:
        checks.append({"name": "Regime", "status": "warn", "detail": "SPY data unavailable"})

    # 4. R:R check
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0

    if rr >= 2.0:
        checks.append({"name": "Risk/Reward", "status": "pass", "detail": f"{rr:.1f}:1 — excellent risk/reward"})
    elif rr >= 1.5:
        checks.append({"name": "Risk/Reward", "status": "pass", "detail": f"{rr:.1f}:1 — acceptable risk/reward"})
    elif rr >= 1.0:
        checks.append({"name": "Risk/Reward", "status": "warn", "detail": f"{rr:.1f}:1 — marginal, consider wider target"})
    else:
        checks.append({"name": "Risk/Reward", "status": "fail", "detail": f"{rr:.1f}:1 — poor risk/reward, skip this trade"})

    # 5. Timing check
    try:
        from datetime import datetime
        import pytz
        now_et = datetime.now(pytz.timezone("US/Eastern"))
        hour = now_et.hour
        minute = now_et.minute

        if 9 <= hour < 10:
            checks.append({"name": "Timing", "status": "pass", "detail": "First hour — highest volume, best follow-through"})
        elif 10 <= hour < 14:
            checks.append({"name": "Timing", "status": "pass", "detail": "Core session — normal trading conditions"})
        elif 14 <= hour < 15:
            checks.append({"name": "Timing", "status": "warn", "detail": "Late session — reduced follow-through"})
        elif hour >= 15:
            checks.append({"name": "Timing", "status": "fail", "detail": "Last hour — low conviction entries, consider waiting"})
        else:
            checks.append({"name": "Timing", "status": "warn", "detail": "Pre-market / after hours"})
    except Exception:
        checks.append({"name": "Timing", "status": "warn", "detail": "Timing check failed"})

    # 6. Daily loss budget check
    try:
        from db import get_db
        with get_db() as conn:
            today_losses = conn.execute(
                """SELECT COUNT(*) FROM alerts
                   WHERE session_date = ? AND alert_type = 'stop_loss_hit'""",
                (date.today().isoformat(),),
            ).fetchone()
            loss_count = today_losses[0] if today_losses else 0

        if loss_count == 0:
            checks.append({"name": "Daily Budget", "status": "pass", "detail": "No losses today — full risk budget available"})
        elif loss_count <= 2:
            checks.append({"name": "Daily Budget", "status": "warn", "detail": f"{loss_count} loss(es) today — reduce position size"})
        else:
            checks.append({"name": "Daily Budget", "status": "fail", "detail": f"{loss_count} losses today — consider stopping for the day"})
    except Exception:
        checks.append({"name": "Daily Budget", "status": "warn", "detail": "Could not check loss count"})

    # Calculate conviction score
    pass_count = sum(1 for c in checks if c["status"] == "pass")
    fail_count = sum(1 for c in checks if c["status"] == "fail")
    conviction = min(10, max(1, pass_count * 2 - fail_count * 3))

    # AI synthesis
    summary = _generate_synthesis(checks, conviction, symbol, direction, entry, rr)

    return {
        "checks": checks,
        "conviction": conviction,
        "conviction_label": "HIGH" if conviction >= 7 else ("MEDIUM" if conviction >= 4 else "LOW"),
        "summary": summary,
    }


def _generate_synthesis(checks: list, conviction: int, symbol: str,
                        direction: str, entry: float, rr: float) -> str:
    """Generate 1-2 sentence AI synthesis of the checklist."""
    from alert_config import ANTHROPIC_API_KEY
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        # Fallback: simple template
        pass_items = [c["name"] for c in checks if c["status"] == "pass"]
        fail_items = [c["name"] for c in checks if c["status"] == "fail"]
        if fail_items:
            return f"Conviction {conviction}/10. Concerns: {', '.join(fail_items)}. Consider skipping or reducing size."
        return f"Conviction {conviction}/10. {', '.join(pass_items)} all check out."

    check_text = "\n".join(f"  {c['name']}: {c['status'].upper()} — {c['detail']}" for c in checks)
    prompt = f"""{direction} {symbol} @ ${entry:.2f} | R:R {rr:.1f}:1

Checklist:
{check_text}

Write a 1-2 sentence conviction assessment. Be specific and actionable."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system="You are a trading coach. Given a pre-trade checklist, write a 1-2 sentence conviction assessment. Be direct. No markdown.",
            messages=[{"role": "user", "content": prompt}],
            timeout=10.0,
        )
        return response.content[0].text.strip()
    except Exception:
        pass_items = [c["name"] for c in checks if c["status"] == "pass"]
        return f"Conviction {conviction}/10. {len(pass_items)}/{len(checks)} checks passed."
