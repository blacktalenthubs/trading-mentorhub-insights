"""SPY support/resistance monitor (user 2026-07-28) — runs every 30 min during RTH, checks where
SPY sits relative to its key levels (PDH/PDL, PWH/PWL, weekly 20-SMA, key MAs, prior 4h H/L),
writes a market_report (kind='spy_levels') so the app shows the live status, and pushes ONCE when
SPY freshly reaches support or resistance. Deterministic; a light AI one-liner is added when
Anthropic is available (falls back to a plain line). Never raises — it's a background job."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

_NEAR_PCT = float(os.environ.get("SPY_LEVELS_NEAR_PCT", "0.25"))  # within this % of a level = "at" it
_PUSH_TTL = 6 * 3600  # one push per (level, direction) per session


def _weekly_20sma(symbol: str = "SPY"):
    """Weekly 20-SMA (the 'fair value' basis) — resample daily closes to W-FRI, rolling 20 mean."""
    try:
        from analytics.market_data import fetch_ohlc
        df = fetch_ohlc(symbol, period="18mo", interval="1d")
        if df is None or df.empty:
            return None
        wk = df["Close"].resample("W-FRI").last().dropna()
        if len(wk) < 20:
            return None
        return round(float(wk.rolling(20).mean().iloc[-1]), 2)
    except Exception:
        return None


def _prior_4h(symbol: str = "SPY"):
    """Prior COMPLETED 4h candle's High/Low, resampled from hourly bars (iloc[-2] = last completed)."""
    try:
        from analytics.intraday_data import fetch_hourly_bars
        df = fetch_hourly_bars(symbol, period="5d")
        if df is None or df.empty or len(df) < 4:
            return None, None
        h4 = df.resample("4h").agg({"High": "max", "Low": "min"}).dropna()
        if len(h4) < 2:
            return None, None
        row = h4.iloc[-2]
        return round(float(row["High"]), 2), round(float(row["Low"]), 2)
    except Exception:
        return None, None


def _narrate(price, status, sup, res) -> str:
    """One-line read. Deterministic base; upgraded by Anthropic (haiku) when a key is present."""
    base = f"SPY ${price} — {status}."
    if sup:
        base += f" Support {sup[0]} {sup[1]}."
    if res:
        base += f" Resistance {res[0]} {res[1]}."
    try:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return base
        prompt = (
            f"SPY is trading ${price}, currently {status}. "
            f"Nearest support: {sup[0] if sup else 'none'} at {sup[1] if sup else 'n/a'}. "
            f"Nearest resistance: {res[0] if res else 'none'} at {res[1] if res else 'n/a'}. "
            "In ONE sentence (max 22 words) tell a busy day-trader what to watch right now. "
            "No hype, no financial advice, no preamble — just the read."
        )
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=90,
            messages=[{"role": "user", "content": prompt}], timeout=8.0,
        )
        txt = (r.content[0].text or "").strip()
        return txt or base
    except Exception:
        return base


def _push_touch(body: dict, session_date: str) -> None:
    """Fan an APNs push to all users on a FRESH touch — deduped per (status, level) per session."""
    try:
        from app.cache import cache_get, cache_set
        from app.services.apns import send_apns_push, apns_configured
    except Exception:
        return
    if not apns_configured():
        return
    lvl = (body.get("nearest_resistance") if body["status"] == "at resistance"
           else body.get("nearest_support")) or {}
    guard = f"spy_touch:{session_date}:{body['status']}:{lvl.get('value')}"
    try:
        if cache_get(guard):
            return  # already pushed this touch today
    except Exception:
        pass
    try:
        from app.database import sync_session_factory  # noqa: local import to avoid cycle
        with sync_session_factory() as db:
            tokens = [r[0] for r in db.execute(text(
                "SELECT token FROM device_tokens WHERE platform = 'ios' AND token IS NOT NULL "
                "UNION SELECT apns_token FROM users WHERE apns_enabled = true "
                "AND apns_token IS NOT NULL AND apns_token <> ''")).all() if r[0]]
    except Exception:
        return
    if not tokens:
        return
    title = f"SPY {body['status']}"
    body_txt = (f"SPY ${body['price']} — {body['status']} "
                f"({lvl.get('label')} {lvl.get('value')}). {body.get('narrative', '')}")[:178]
    data = {"type": "market_report", "kind": "spy_levels", "route": "/today?tab=reports", "tab": "reports"}
    import asyncio

    async def _go():
        for t in tokens:
            try:
                await send_apns_push(t, title, body_txt, payload=data)
            except Exception:
                pass
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_go())
    finally:
        loop.close()
    try:
        cache_set(guard, True, _PUSH_TTL)
    except Exception:
        pass
    logger.info("SPY monitor: pushed %s (%s %s) to %d device(s)",
                body["status"], lvl.get("label"), lvl.get("value"), len(tokens))


def refresh_spy_levels(sync_session_factory) -> dict:
    """The scheduled job: compute SPY's S/R position, upsert the report, push on a fresh touch."""
    try:
        from analytics.intraday_data import fetch_prior_day, fetch_latest_price
        sym = "SPY"
        pd_ = fetch_prior_day(sym) or {}
        price = fetch_latest_price(sym) or pd_.get("close")
        if not price:
            logger.warning("SPY monitor: no price — skipping")
            return {"error": "no price"}
        price = round(float(price), 2)

        levels: list[tuple[str, float]] = []

        def add(lbl, v):
            if v and float(v) > 0:
                levels.append((lbl, round(float(v), 2)))

        add("PDH", pd_.get("high"))
        add("PDL", pd_.get("low"))
        add("PWH", pd_.get("prior_week_high"))
        add("PWL", pd_.get("prior_week_low"))
        add("8 EMA", pd_.get("ema8"))
        add("21 EMA", pd_.get("ema21"))
        add("50 EMA", pd_.get("ema50"))
        add("200 EMA", pd_.get("ema200"))
        add("50 SMA", pd_.get("ma50"))
        add("200 SMA", pd_.get("ma200"))
        add("Wk 20-SMA", _weekly_20sma(sym))
        h4h, h4l = _prior_4h(sym)
        add("4H High", h4h)
        add("4H Low", h4l)

        sup = sorted([(l, v) for l, v in levels if v <= price], key=lambda x: -x[1])  # nearest below first
        res = sorted([(l, v) for l, v in levels if v > price], key=lambda x: x[1])    # nearest above first
        nearest_sup = sup[0] if sup else None
        nearest_res = res[0] if res else None

        def pct(v):
            return round(abs(price - v) / v * 100, 2)

        at_res = bool(nearest_res) and pct(nearest_res[1]) <= _NEAR_PCT
        at_sup = bool(nearest_sup) and pct(nearest_sup[1]) <= _NEAR_PCT
        status = "at resistance" if at_res else "at support" if at_sup else "mid-range"
        narrative = _narrate(price, status, nearest_sup, nearest_res)

        body = {
            "symbol": sym, "price": price, "status": status,
            "nearest_support": ({"label": nearest_sup[0], "value": nearest_sup[1], "pct": pct(nearest_sup[1])} if nearest_sup else None),
            "nearest_resistance": ({"label": nearest_res[0], "value": nearest_res[1], "pct": pct(nearest_res[1])} if nearest_res else None),
            "levels": [{"label": l, "value": v} for l, v in levels],
            "narrative": narrative, "at_ts": datetime.utcnow().isoformat(),
        }
        session_date = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            with sync_session_factory() as db:
                db.execute(text(
                    "INSERT INTO market_reports (kind, session_date, body, created_at) "
                    "VALUES ('spy_levels', :d, :b, NOW()) "
                    "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()"
                ), {"d": session_date, "b": json.dumps(body)})
                db.commit()
        except Exception:
            logger.exception("SPY monitor: report upsert failed")

        if at_sup or at_res:
            _push_touch(body, session_date)
        logger.info("SPY monitor: %s @ %s — %s", sym, price, status)
        return body
    except Exception:
        logger.exception("SPY monitor failed")
        return {"error": "exception"}
