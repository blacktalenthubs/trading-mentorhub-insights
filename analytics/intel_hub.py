"""AI Intelligence Hub — data layer for the hub page.

Provides win-rate analytics, multi-timeframe S/R levels, fundamentals,
weekly bars, AI insight streaming, and AI scanner context assembly.
No protected business logic here.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Generator

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alert win-rate analytics
# ---------------------------------------------------------------------------

def get_alert_win_rates(days: int = 90, user_id: int | None = None) -> dict:
    """Compute alert outcome win rates from the alerts table.

    Groups alerts by (symbol, session_date). Entry-type alerts (BUY direction,
    non-outcome types) are matched against target hits (win) or stop outs (loss)
    in the same (symbol, session_date) group.

    Returns dict with keys: by_symbol, by_alert_type, by_hour, overall.
    Each bucket: {wins, losses, unknown, total, win_rate}.
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE session_date >= ? "
                "AND (user_id=? OR user_id IS NULL) ORDER BY created_at",
                (cutoff, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE session_date >= ? ORDER BY created_at",
                (cutoff,),
            ).fetchall()

    alerts = [dict(r) for r in rows]

    _OUTCOME_TYPES = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
    _WIN_TYPES = {"target_1_hit", "target_2_hit"}
    _LOSS_TYPES = {"stop_loss_hit", "auto_stop_out"}

    # Group by (symbol, session_date)
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in alerts:
        key = (a.get("symbol", ""), a.get("session_date", ""))
        groups.setdefault(key, []).append(a)

    # Track outcomes per entry alert
    entry_outcomes: list[dict] = []
    for (symbol, session), group_alerts in groups.items():
        outcomes = set()
        for a in group_alerts:
            at = a.get("alert_type", "")
            if at in _WIN_TYPES:
                outcomes.add("win")
            elif at in _LOSS_TYPES:
                outcomes.add("loss")

        # Find entry-type alerts (non-outcome BUY/SHORT alerts)
        for a in group_alerts:
            at = a.get("alert_type", "")
            direction = a.get("direction", "")
            if at in _OUTCOME_TYPES:
                continue
            if direction not in ("BUY", "SHORT"):
                continue
            result = "unknown"
            if "win" in outcomes:
                result = "win"
            elif "loss" in outcomes:
                result = "loss"

            created = a.get("created_at", "")
            hour = None
            if created:
                try:
                    hour = datetime.fromisoformat(str(created)).hour
                except (ValueError, TypeError):
                    pass

            entry_outcomes.append({
                "symbol": symbol,
                "alert_type": at,
                "hour": hour,
                "result": result,
            })

    def _bucket(items: list[dict]) -> dict:
        wins = sum(1 for i in items if i["result"] == "win")
        losses = sum(1 for i in items if i["result"] == "loss")
        unknown = sum(1 for i in items if i["result"] == "unknown")
        total = len(items)
        win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
        return {"wins": wins, "losses": losses, "unknown": unknown,
                "total": total, "win_rate": win_rate}

    # by_symbol
    by_symbol: dict[str, dict] = {}
    for e in entry_outcomes:
        by_symbol.setdefault(e["symbol"], []).append(e)
    by_symbol = {sym: _bucket(items) for sym, items in by_symbol.items()}

    # by_alert_type
    by_alert_type: dict[str, dict] = {}
    for e in entry_outcomes:
        by_alert_type.setdefault(e["alert_type"], []).append(e)
    by_alert_type = {at: _bucket(items) for at, items in by_alert_type.items()}

    # by_hour
    by_hour: dict[int, dict] = {}
    for e in entry_outcomes:
        if e["hour"] is not None:
            by_hour.setdefault(e["hour"], []).append(e)
    by_hour = {h: _bucket(items) for h, items in sorted(by_hour.items())}

    overall = _bucket(entry_outcomes)

    return {
        "by_symbol": by_symbol,
        "by_alert_type": by_alert_type,
        "by_hour": by_hour,
        "overall": overall,
    }


def get_acked_trade_win_rates(user_id: int, days: int = 90) -> dict:
    """Win rates for trades the user actually took (user_action='took').

    Same structure as get_alert_win_rates but filtered to ACK'd entries only.
    Returns dict with keys: by_symbol, by_alert_type, by_hour, overall, total_trades.
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # Get all alerts for this user in the period
        all_rows = conn.execute(
            "SELECT * FROM alerts WHERE session_date >= ? "
            "AND (user_id=? OR user_id IS NULL) ORDER BY created_at",
            (cutoff, user_id),
        ).fetchall()

    alerts = [dict(r) for r in all_rows]

    _OUTCOME_TYPES = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
    _WIN_TYPES = {"target_1_hit", "target_2_hit"}
    _LOSS_TYPES = {"stop_loss_hit", "auto_stop_out"}

    # Group by (symbol, session_date) to find outcomes
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in alerts:
        key = (a.get("symbol", ""), a.get("session_date", ""))
        groups.setdefault(key, []).append(a)

    entry_outcomes: list[dict] = []
    for (symbol, session), group_alerts in groups.items():
        outcomes = set()
        for a in group_alerts:
            at = a.get("alert_type", "")
            if at in _WIN_TYPES:
                outcomes.add("win")
            elif at in _LOSS_TYPES:
                outcomes.add("loss")

        # Only include ACK'd entry alerts
        for a in group_alerts:
            at = a.get("alert_type", "")
            direction = a.get("direction", "")
            if at in _OUTCOME_TYPES:
                continue
            if direction not in ("BUY", "SHORT"):
                continue
            if a.get("user_action") != "took":
                continue

            result = "unknown"
            if "win" in outcomes:
                result = "win"
            elif "loss" in outcomes:
                result = "loss"

            created = a.get("created_at", "")
            hour = None
            if created:
                try:
                    hour = datetime.fromisoformat(str(created)).hour
                except (ValueError, TypeError):
                    pass

            entry_outcomes.append({
                "symbol": symbol,
                "alert_type": at,
                "hour": hour,
                "result": result,
            })

    def _bucket(items: list[dict]) -> dict:
        wins = sum(1 for i in items if i["result"] == "win")
        losses = sum(1 for i in items if i["result"] == "loss")
        unknown = sum(1 for i in items if i["result"] == "unknown")
        total = len(items)
        win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
        return {"wins": wins, "losses": losses, "unknown": unknown,
                "total": total, "win_rate": win_rate}

    by_symbol: dict[str, dict] = {}
    for e in entry_outcomes:
        by_symbol.setdefault(e["symbol"], []).append(e)
    by_symbol = {sym: _bucket(items) for sym, items in by_symbol.items()}

    by_alert_type: dict[str, dict] = {}
    for e in entry_outcomes:
        by_alert_type.setdefault(e["alert_type"], []).append(e)
    by_alert_type = {at: _bucket(items) for at, items in by_alert_type.items()}

    by_hour: dict[int, dict] = {}
    for e in entry_outcomes:
        if e["hour"] is not None:
            by_hour.setdefault(e["hour"], []).append(e)
    by_hour = {h: _bucket(items) for h, items in sorted(by_hour.items())}

    overall = _bucket(entry_outcomes)

    return {
        "by_symbol": by_symbol,
        "by_alert_type": by_alert_type,
        "by_hour": by_hour,
        "overall": overall,
        "total_trades": len(entry_outcomes),
    }


def get_trading_journal(user_id: int, days: int = 30) -> list[dict]:
    """Return ACK'd trades with outcomes and P&L for the journal view.

    Each entry includes: symbol, alert_type, direction, price, entry, stop,
    target_1, target_2, user_action, acked_at, session_date, outcome, pnl,
    real_trade (matched real_trade row if exists).
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # All alerts with user_action set (took or skipped)
        alerts = conn.execute(
            """SELECT * FROM alerts
               WHERE user_id = ? AND user_action IS NOT NULL
                 AND session_date >= ?
               ORDER BY created_at DESC""",
            (user_id, cutoff),
        ).fetchall()
        alerts = [dict(r) for r in alerts]

        # All real trades in the period (matched by alert_id)
        trades = conn.execute(
            """SELECT * FROM real_trades
               WHERE session_date >= ?
               ORDER BY opened_at DESC""",
            (cutoff,),
        ).fetchall()
        trades_by_alert = {r["alert_id"]: dict(r) for r in trades if r.get("alert_id")}

    # Also build outcome map: (symbol, session_date) → outcome
    _WIN_TYPES = {"target_1_hit", "target_2_hit"}
    _LOSS_TYPES = {"stop_loss_hit", "auto_stop_out"}

    outcome_map: dict[tuple[str, str], str] = {}
    for a in alerts:
        at = a.get("alert_type", "")
        key = (a.get("symbol", ""), a.get("session_date", ""))
        if at in _WIN_TYPES:
            outcome_map[key] = "win"
        elif at in _LOSS_TYPES and key not in outcome_map:
            outcome_map[key] = "loss"

    journal: list[dict] = []
    for a in alerts:
        at = a.get("alert_type", "")
        direction = a.get("direction", "")
        # Only include entry alerts (BUY/SHORT with took/skipped)
        if at in _WIN_TYPES | _LOSS_TYPES:
            continue
        if direction not in ("BUY", "SHORT"):
            continue

        key = (a.get("symbol", ""), a.get("session_date", ""))
        outcome = outcome_map.get(key, "open")
        real_trade = trades_by_alert.get(a.get("id"))

        journal.append({
            "id": a.get("id"),
            "symbol": a["symbol"],
            "alert_type": at,
            "direction": direction,
            "price": a.get("price", 0),
            "entry": a.get("entry"),
            "stop": a.get("stop"),
            "target_1": a.get("target_1"),
            "target_2": a.get("target_2"),
            "score": a.get("score", 0),
            "score_label": a.get("score_label", ""),
            "user_action": a.get("user_action"),
            "acked_at": a.get("acked_at"),
            "session_date": a.get("session_date"),
            "created_at": a.get("created_at"),
            "outcome": outcome,
            "pnl": real_trade.get("pnl") if real_trade else None,
            "exit_price": real_trade.get("exit_price") if real_trade else None,
            "trade_status": real_trade.get("status") if real_trade else None,
        })

    return journal


def get_decision_quality(user_id: int, days: int = 90) -> dict:
    """Compare win rates of took vs skipped alerts to measure decision quality.

    Returns:
        took: {wins, losses, unknown, total, win_rate, total_pnl}
        skipped: {wins, losses, unknown, total, win_rate, hypothetical_pnl}
        decision_edge: took_win_rate - skipped_win_rate (positive = good filtering)
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        all_rows = conn.execute(
            "SELECT * FROM alerts WHERE session_date >= ? "
            "AND (user_id=? OR user_id IS NULL) ORDER BY created_at",
            (cutoff, user_id),
        ).fetchall()

    alerts = [dict(r) for r in all_rows]

    _OUTCOME_TYPES = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
    _WIN_TYPES = {"target_1_hit", "target_2_hit"}
    _LOSS_TYPES = {"stop_loss_hit", "auto_stop_out"}

    # Group by (symbol, session_date)
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in alerts:
        key = (a.get("symbol", ""), a.get("session_date", ""))
        groups.setdefault(key, []).append(a)

    took_outcomes: list[dict] = []
    skipped_outcomes: list[dict] = []

    for (symbol, session), group_alerts in groups.items():
        outcomes = set()
        for a in group_alerts:
            at = a.get("alert_type", "")
            if at in _WIN_TYPES:
                outcomes.add("win")
            elif at in _LOSS_TYPES:
                outcomes.add("loss")

        for a in group_alerts:
            at = a.get("alert_type", "")
            direction = a.get("direction", "")
            action = a.get("user_action")
            if at in _OUTCOME_TYPES or direction not in ("BUY", "SHORT"):
                continue
            if action not in ("took", "skipped"):
                continue

            result = "unknown"
            if "win" in outcomes:
                result = "win"
            elif "loss" in outcomes:
                result = "loss"

            entry = {"symbol": symbol, "result": result}
            if action == "took":
                took_outcomes.append(entry)
            else:
                skipped_outcomes.append(entry)

    def _stats(items):
        wins = sum(1 for i in items if i["result"] == "win")
        losses = sum(1 for i in items if i["result"] == "loss")
        unknown = sum(1 for i in items if i["result"] == "unknown")
        total = len(items)
        wr = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
        return {"wins": wins, "losses": losses, "unknown": unknown,
                "total": total, "win_rate": wr}

    took = _stats(took_outcomes)
    skipped = _stats(skipped_outcomes)

    edge = round(took["win_rate"] - skipped["win_rate"], 1) if (
        took["total"] > 0 and skipped["total"] > 0
    ) else None

    return {
        "took": took,
        "skipped": skipped,
        "decision_edge": edge,
    }


def get_symbol_ack_stats(user_id: int, days: int = 90) -> dict[str, dict]:
    """Per-symbol ACK stats for scanner badges.

    Returns {symbol: {took, skipped, wins, losses, win_rate}}.
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        all_rows = conn.execute(
            "SELECT * FROM alerts WHERE session_date >= ? "
            "AND (user_id=? OR user_id IS NULL) ORDER BY created_at",
            (cutoff, user_id),
        ).fetchall()

    alerts = [dict(r) for r in all_rows]

    _OUTCOME_TYPES = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
    _WIN_TYPES = {"target_1_hit", "target_2_hit"}
    _LOSS_TYPES = {"stop_loss_hit", "auto_stop_out"}

    # Group by (symbol, session_date) for outcome matching
    groups: dict[tuple[str, str], list[dict]] = {}
    for a in alerts:
        key = (a.get("symbol", ""), a.get("session_date", ""))
        groups.setdefault(key, []).append(a)

    # Per-symbol stats
    sym_stats: dict[str, dict] = {}

    for (symbol, session), group_alerts in groups.items():
        outcomes = set()
        for a in group_alerts:
            at = a.get("alert_type", "")
            if at in _WIN_TYPES:
                outcomes.add("win")
            elif at in _LOSS_TYPES:
                outcomes.add("loss")

        for a in group_alerts:
            at = a.get("alert_type", "")
            direction = a.get("direction", "")
            action = a.get("user_action")
            if at in _OUTCOME_TYPES or direction not in ("BUY", "SHORT"):
                continue
            if action not in ("took", "skipped"):
                continue

            if symbol not in sym_stats:
                sym_stats[symbol] = {"took": 0, "skipped": 0, "wins": 0, "losses": 0}

            s = sym_stats[symbol]
            if action == "took":
                s["took"] += 1
                if "win" in outcomes:
                    s["wins"] += 1
                elif "loss" in outcomes:
                    s["losses"] += 1
            else:
                s["skipped"] += 1

    # Compute win rates
    for s in sym_stats.values():
        resolved = s["wins"] + s["losses"]
        s["win_rate"] = round(s["wins"] / resolved * 100, 1) if resolved > 0 else 0.0

    return sym_stats


# ---------------------------------------------------------------------------
# Multi-timeframe S/R levels
# ---------------------------------------------------------------------------

def get_sr_levels(symbol: str) -> list[dict]:
    """Gather support/resistance levels from multiple timeframes.

    Sources: daily MAs (20/50/100/200), EMAs (20/50/100), prior day H/L,
    prior week H/L, hourly swing highs/lows. Each level includes distance %
    from current price.

    Returns list of dicts sorted by abs(distance_pct) — nearest first.
    """
    from analytics.intraday_data import (
        detect_hourly_resistance,
        detect_hourly_support,
        fetch_hourly_bars,
        fetch_intraday,
        fetch_prior_day,
    )

    levels: list[dict] = []
    prior = fetch_prior_day(symbol)
    if prior is None:
        return levels

    # Current price from intraday data
    intra = fetch_intraday(symbol)
    if not intra.empty:
        current_price = float(intra["Close"].iloc[-1])
    else:
        current_price = float(prior["close"])

    if current_price <= 0:
        return levels

    def _add(level_price, label, level_type, source):
        if level_price and level_price > 0:
            dist = (current_price - level_price) / level_price * 100
            levels.append({
                "level": round(level_price, 2),
                "label": label,
                "type": level_type,
                "source": source,
                "distance_pct": round(dist, 2),
            })

    # Daily MAs
    for key, label in [("ma20", "20 SMA"), ("ma50", "50 SMA"),
                       ("ma100", "100 SMA"), ("ma200", "200 SMA")]:
        val = prior.get(key)
        if val:
            ltype = "support" if current_price > val else "resistance"
            _add(val, label, ltype, "daily_ma")

    # EMAs
    for key, label in [("ema20", "20 EMA"), ("ema50", "50 EMA"),
                       ("ema100", "100 EMA")]:
        val = prior.get(key)
        if val:
            ltype = "support" if current_price > val else "resistance"
            _add(val, label, ltype, "daily_ema")

    # Prior day high/low
    _add(prior.get("high"), "Prior Day High", "resistance", "prior_day")
    _add(prior.get("low"), "Prior Day Low", "support", "prior_day")

    # Prior week high/low
    _add(prior.get("prior_week_high"), "Prior Week High", "resistance", "prior_week")
    _add(prior.get("prior_week_low"), "Prior Week Low", "support", "prior_week")

    # Hourly swing levels — keep only the 3 nearest support + 3 nearest
    # resistance within 5% of current price to avoid clutter.
    _HOURLY_MAX_PER_SIDE = 3
    _HOURLY_MAX_DIST_PCT = 5.0
    try:
        bars_1h = fetch_hourly_bars(symbol)
        if not bars_1h.empty:
            # Resistance: sorted ascending → nearest above = smallest > price
            hourly_res = detect_hourly_resistance(bars_1h)
            above = sorted(
                (r for r in hourly_res if r >= current_price),
                key=lambda r: r - current_price,
            )
            for r in above[:_HOURLY_MAX_PER_SIDE]:
                dist = abs(current_price - r) / r * 100
                if dist <= _HOURLY_MAX_DIST_PCT:
                    _add(r, "Hourly Swing High", "resistance", "hourly")

            # Support: nearest below = largest < price
            hourly_sup = detect_hourly_support(bars_1h)
            below = sorted(
                (s for s in hourly_sup if s <= current_price),
                key=lambda s: current_price - s,
            )
            for s in below[:_HOURLY_MAX_PER_SIDE]:
                dist = abs(current_price - s) / s * 100
                if dist <= _HOURLY_MAX_DIST_PCT:
                    _add(s, "Hourly Swing Low", "support", "hourly")
    except Exception:
        logger.debug("intel_hub: hourly S/R failed for %s", symbol)

    # Sort by proximity
    levels.sort(key=lambda x: abs(x["distance_pct"]))
    return levels


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def _format_market_cap(val) -> str:
    """Format market cap to human-readable string: $2.5T, $500B, $12.3M."""
    if val is None:
        return "N/A"
    try:
        val = float(val)
    except (TypeError, ValueError):
        return "N/A"
    if val >= 1e12:
        return f"${val / 1e12:.1f}T"
    if val >= 1e9:
        return f"${val / 1e9:.1f}B"
    if val >= 1e6:
        return f"${val / 1e6:.1f}M"
    return f"${val:,.0f}"


def get_fundamentals(symbol: str) -> dict | None:
    """Fetch fundamental data from yfinance.

    Returns dict with PE, forward PE, market cap, 52W high/low, sector,
    industry, beta, dividend yield, short ratio, earnings date.
    Returns None on failure.
    """
    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # Earnings date from calendar
        earnings_date = None
        try:
            cal = ticker.calendar
            if cal is not None:
                if isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.columns:
                    ed = cal["Earnings Date"].iloc[0]
                    earnings_date = str(ed.date()) if hasattr(ed, "date") else str(ed)
                elif isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if isinstance(ed, list) and ed:
                        ed = ed[0]
                    if ed is not None:
                        earnings_date = str(ed.date()) if hasattr(ed, "date") else str(ed)
        except Exception:
            pass

        mkt_cap_raw = info.get("marketCap")
        return {
            "pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "market_cap": mkt_cap_raw,
            "market_cap_fmt": _format_market_cap(mkt_cap_raw),
            "high_52w": info.get("fiftyTwoWeekHigh"),
            "low_52w": info.get("fiftyTwoWeekLow"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "beta": info.get("beta"),
            "dividend_yield": info.get("dividendYield"),
            "short_ratio": info.get("shortRatio"),
            "earnings_date": earnings_date,
            "name": info.get("shortName") or info.get("longName"),
        }
    except Exception:
        logger.exception("intel_hub: fundamentals failed for %s", symbol)
        return None


# ---------------------------------------------------------------------------
# Weekly bars
# ---------------------------------------------------------------------------

def get_weekly_bars(symbol: str) -> tuple[pd.DataFrame, dict]:
    """Fetch 2-year daily history and resample to weekly OHLCV + weekly MAs.

    Returns (weekly_df, {"wma10": float, "wma20": float, "wma50": float}).
    On failure returns (empty DataFrame, empty dict).
    """
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="2y")
        if hist.empty:
            return pd.DataFrame(), {}
        hist.index = hist.index.tz_localize(None)
        ohlcv = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        # Resample to weekly (same pattern as pages/7_Charts.py)
        weekly = ohlcv.resample("W-FRI").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna()

        if weekly.empty:
            return pd.DataFrame(), {}

        # Compute weekly MAs
        wmas = {}
        for period in (10, 20, 50):
            if len(weekly) >= period:
                ma_val = float(weekly["Close"].rolling(period).mean().iloc[-1])
                wmas[f"wma{period}"] = round(ma_val, 2)

        return weekly, wmas
    except Exception:
        logger.exception("intel_hub: weekly bars failed for %s", symbol)
        return pd.DataFrame(), {}


# ---------------------------------------------------------------------------
# Weekly swing-trade setup detection
# ---------------------------------------------------------------------------

def analyze_weekly_setup(weekly_df: pd.DataFrame, wmas: dict) -> dict:
    """Detect multi-week base patterns and classify weekly swing setups.

    Scans the last N weekly bars for consolidation bases, classifies the
    current week's position relative to the base, and computes entry/stop/target
    levels with a 0-100 score.

    Returns dict with setup_type, score, score_label, levels, and edge text.
    """
    from alert_config import (
        WEEKLY_BASE_LOOKBACK,
        WEEKLY_BASE_MAX_RANGE_PCT,
        WEEKLY_BASE_MIN_WEEKS,
        WEEKLY_BASE_TIGHT_RANGE_PCT,
        WEEKLY_BREAKOUT_VOLUME_RATIO,
        WEEKLY_PULLBACK_WMA_PCT,
        WEEKLY_STOP_OFFSET_PCT,
        WEEKLY_VOLUME_CONTRACTION_RATIO,
    )

    _NO_SETUP = {
        "setup_type": "NO_SETUP",
        "score": 0,
        "score_label": "C",
        "base_weeks": 0,
        "base_high": None,
        "base_low": None,
        "base_range_pct": 0.0,
        "volume_contracting": False,
        "volume_ratio": 0.0,
        "entry": None,
        "stop": None,
        "target_1": None,
        "target_2": None,
        "risk_reward": 0.0,
        "weekly_candle": ("normal", "neutral"),
        "edge": "No weekly setup detected",
    }

    if weekly_df.empty or len(weekly_df) < WEEKLY_BASE_LOOKBACK:
        return _NO_SETUP

    # --- Weekly candle classification (reuse market_data.classify_day) ---
    from analytics.market_data import classify_day

    current_bar = weekly_df.iloc[-1]
    prev_bar = weekly_df.iloc[-2] if len(weekly_df) >= 2 else None
    weekly_candle = classify_day(current_bar, prev_bar)

    # --- Phase 1: Base Detection ---
    # Scan bars excluding the current (incomplete) week
    lookback_bars = weekly_df.iloc[-(WEEKLY_BASE_LOOKBACK + 1):-1]
    n_bars = len(lookback_bars)

    best_base = None  # (start_idx, end_idx, base_high, base_low, range_pct, weeks)

    for window_len in range(WEEKLY_BASE_MIN_WEEKS, n_bars + 1):
        # Window ending at the last lookback bar
        window = lookback_bars.iloc[-window_len:]
        max_high = float(window["High"].max())
        min_low = float(window["Low"].min())
        avg_close = float(window["Close"].mean())

        if avg_close <= 0:
            continue

        range_pct = (max_high - min_low) / avg_close

        if range_pct <= WEEKLY_BASE_MAX_RANGE_PCT:
            # Valid base — keep the longest
            best_base = {
                "start_idx": len(lookback_bars) - window_len,
                "weeks": window_len,
                "base_high": max_high,
                "base_low": min_low,
                "range_pct": range_pct,
                "avg_vol": float(window["Volume"].mean()) if "Volume" in window.columns else 0,
            }

    # Volume contraction: compare base avg vol to prior period avg vol
    volume_contracting = False
    volume_ratio = 0.0

    if best_base and best_base["avg_vol"] > 0:
        prior_start = max(0, best_base["start_idx"] - best_base["weeks"])
        prior_end = best_base["start_idx"]
        if prior_end > prior_start:
            prior_bars = lookback_bars.iloc[prior_start:prior_end]
            prior_avg_vol = float(prior_bars["Volume"].mean()) if not prior_bars.empty else 0
            if prior_avg_vol > 0:
                volume_ratio = best_base["avg_vol"] / prior_avg_vol
                volume_contracting = volume_ratio < WEEKLY_VOLUME_CONTRACTION_RATIO

    # --- Phase 2: Classify Setup ---
    close = float(current_bar["Close"])
    current_vol = float(current_bar["Volume"]) if pd.notna(current_bar.get("Volume")) else 0

    setup_type = "NO_SETUP"
    base_high = best_base["base_high"] if best_base else None
    base_low = best_base["base_low"] if best_base else None
    base_weeks = best_base["weeks"] if best_base else 0
    base_range_pct = best_base["range_pct"] if best_base else 0.0
    base_avg_vol = best_base["avg_vol"] if best_base else 0

    if best_base:
        breakout_vol_ok = (
            base_avg_vol > 0 and current_vol > WEEKLY_BREAKOUT_VOLUME_RATIO * base_avg_vol
        )
        if close > base_high and breakout_vol_ok:
            setup_type = "BREAKOUT"
        elif base_low <= close <= base_high:
            setup_type = "BASE_FORMING"

    if setup_type == "NO_SETUP":
        # Check for pullback to WMA
        wma10 = wmas.get("wma10")
        wma20 = wmas.get("wma20")
        wma50 = wmas.get("wma50")
        near_wma = False
        if wma10 and close > 0:
            near_wma = abs(close - wma10) / close <= WEEKLY_PULLBACK_WMA_PCT
        if not near_wma and wma20 and close > 0:
            near_wma = abs(close - wma20) / close <= WEEKLY_PULLBACK_WMA_PCT
        wma_aligned = (
            wma10 is not None and wma20 is not None and wma50 is not None
            and wma10 > wma20 > wma50
        )
        above_wma50 = wma50 is not None and close > wma50

        if near_wma and above_wma50 and wma_aligned:
            setup_type = "PULLBACK"

    # --- Phase 3: Compute Levels ---
    entry = None
    stop = None
    target_1 = None
    target_2 = None

    if setup_type == "BASE_FORMING" and base_high and base_low:
        base_range = base_high - base_low
        entry = base_high
        stop = base_low
        target_1 = base_high + base_range
        target_2 = base_high + 2 * base_range
    elif setup_type == "BREAKOUT" and base_high and base_low:
        base_range = base_high - base_low
        entry = close
        stop = base_high
        target_1 = close + base_range
        target_2 = close + 2 * base_range
    elif setup_type == "PULLBACK":
        wma10 = wmas.get("wma10")
        wma20 = wmas.get("wma20")
        wma50 = wmas.get("wma50")
        # Entry at nearest WMA
        if wma10 and abs(close - wma10) / close <= WEEKLY_PULLBACK_WMA_PCT:
            entry = wma10
        elif wma20:
            entry = wma20
        # Stop below WMA50
        if wma50:
            stop = round(wma50 * (1 - WEEKLY_STOP_OFFSET_PCT), 2)
        # Targets from prior swing high
        swing_high = float(weekly_df.iloc[-8:]["High"].max()) if len(weekly_df) >= 8 else None
        if swing_high and entry:
            target_1 = swing_high
            target_2 = swing_high + (close - (entry or close))

    # Risk:reward
    risk_reward = 0.0
    if entry and stop and target_1 and entry != stop:
        risk = abs(entry - stop)
        if risk > 0:
            risk_reward = round((target_1 - entry) / risk, 1)

    # --- Phase 4: Score (0-100) ---
    score = 0

    # Base quality (0-30)
    if best_base:
        if best_base["range_pct"] <= WEEKLY_BASE_TIGHT_RANGE_PCT:
            score += 30
        else:
            score += 20

    # Volume (0-20)
    if setup_type == "BREAKOUT" and base_avg_vol > 0 and current_vol > WEEKLY_BREAKOUT_VOLUME_RATIO * base_avg_vol:
        score += 20
    elif volume_contracting:
        score += 15
    else:
        score += 5

    # WMA alignment (0-25)
    wma10 = wmas.get("wma10")
    wma20 = wmas.get("wma20")
    wma50 = wmas.get("wma50")
    if wma10 and wma20 and wma50:
        if wma10 > wma20 > wma50:
            score += 25
        elif wma10 > wma50 or wma20 > wma50:
            score += 12

    # Weekly candle (0-15)
    pattern, direction = weekly_candle
    if pattern == "inside":
        score += 15
    elif direction == "bullish":
        score += 10
    elif direction == "neutral":
        score += 5
    # bearish = 0

    # R:R (0-10)
    if risk_reward >= 3.0:
        score += 10
    elif risk_reward >= 2.0:
        score += 7
    elif risk_reward >= 1.5:
        score += 3

    # Score label
    if score >= 80:
        score_label = "A+"
    elif score >= 70:
        score_label = "A"
    elif score >= 55:
        score_label = "B"
    else:
        score_label = "C"

    # --- Phase 6: Edge text ---
    if setup_type == "BASE_FORMING" and base_high and base_low:
        edge_parts = [f"{base_weeks}-week base ({base_low:.2f} \u2013 {base_high:.2f})"]
        if volume_contracting:
            contraction_pct = round((1 - volume_ratio) * 100)
            edge_parts.append(f"vol contracting {contraction_pct}%")
        if wma10 and wma20 and wma50 and wma10 > wma20 > wma50:
            edge_parts.append("WMAs aligned")
        edge = ", ".join(edge_parts)
    elif setup_type == "BREAKOUT" and base_high:
        vol_mult = round(current_vol / base_avg_vol, 1) if base_avg_vol > 0 else 0
        edge = f"Breakout above {base_weeks}-week base ({base_high:.2f}) on {vol_mult}x volume"
    elif setup_type == "PULLBACK":
        nearest_wma_label = "WMA10" if (wma10 and abs(close - wma10) / close <= WEEKLY_PULLBACK_WMA_PCT) else "WMA20"
        nearest_wma_val = wma10 if nearest_wma_label == "WMA10" else wma20
        edge = f"Pullback to {nearest_wma_label} ({nearest_wma_val:.2f}) in weekly uptrend"
    else:
        edge = "No weekly setup detected"

    return {
        "setup_type": setup_type,
        "score": score,
        "score_label": score_label,
        "base_weeks": base_weeks,
        "base_high": base_high,
        "base_low": base_low,
        "base_range_pct": round(base_range_pct, 4),
        "volume_contracting": volume_contracting,
        "volume_ratio": round(volume_ratio, 3),
        "entry": round(entry, 2) if entry else None,
        "stop": round(stop, 2) if stop else None,
        "target_1": round(target_1, 2) if target_1 else None,
        "target_2": round(target_2, 2) if target_2 else None,
        "risk_reward": risk_reward,
        "weekly_candle": weekly_candle,
        "edge": edge,
    }


# ---------------------------------------------------------------------------
# AI insight (one-shot, focused analysis)
# ---------------------------------------------------------------------------

def ask_ai_insight(prompt: str, context_text: str) -> Generator[str, None, None]:
    """One-shot Claude call for in-tab AI analysis buttons.

    Streams a concise, focused analysis. Separate from multi-turn chat.
    Raises ValueError if no API key configured.
    """
    from analytics.trade_coach import _resolve_api_key
    from alert_config import CLAUDE_MODEL

    api_key = _resolve_api_key()
    if not api_key:
        raise ValueError(
            "No Anthropic API key configured. Set ANTHROPIC_API_KEY in "
            "environment or add it in Settings."
        )

    import anthropic

    system = (
        "You are a sharp trading analyst. Structure your response with markdown:\n"
        "- Use **bold** for key numbers and levels\n"
        "- Use bullet points for each insight\n"
        "- Provide 3-5 focused bullet points\n"
        "- NEVER use the $ character for dollar amounts — write '150.25' or 'USD 150.25' instead\n"
        "- Use specific numbers from the data. No filler, no preamble.\n"
        "- Be direct and actionable."
    )

    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": f"{context_text}\n\n{prompt}"}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


# ---------------------------------------------------------------------------
# Hub context assembly (for enriching AI Coach system prompt)
# ---------------------------------------------------------------------------

def get_paper_trade_win_rates(days: int = 90) -> dict:
    """Paper trade win rates bucketed by symbol, alert_type, and overall.

    Returns {by_symbol: {SYM: {wins, losses, total, win_rate, total_pnl}},
             by_alert_type: {TYPE: ...}, overall: {...}}.
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol, alert_type, pnl FROM paper_trades "
            "WHERE status != 'open' AND pnl IS NOT NULL AND session_date >= ?",
            (cutoff,),
        ).fetchall()

    if not rows:
        return {}

    def _bucket(items):
        wins = sum(1 for r in items if r["pnl"] > 0)
        losses = sum(1 for r in items if r["pnl"] <= 0)
        total = len(items)
        return {
            "wins": wins,
            "losses": losses,
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "total_pnl": round(sum(r["pnl"] for r in items), 2),
        }

    by_symbol: dict[str, list] = {}
    by_type: dict[str, list] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append(r)
        by_type.setdefault(r["alert_type"] or "unknown", []).append(r)

    return {
        "by_symbol": {k: _bucket(v) for k, v in by_symbol.items()},
        "by_alert_type": {k: _bucket(v) for k, v in by_type.items()},
        "overall": _bucket(rows),
    }


def assemble_hub_context(symbol: str) -> dict:
    """Assemble hub data for a single symbol — used by trade_coach.

    Returns dict with fundamentals, sr_levels, weekly_trend, win_rates.
    All fields are best-effort (None/empty on failure).
    """
    fundamentals = None
    try:
        fundamentals = get_fundamentals(symbol)
    except Exception:
        logger.debug("intel_hub: fundamentals context failed for %s", symbol)

    sr_levels = []
    try:
        sr_levels = get_sr_levels(symbol)[:10]  # top 10 by proximity
    except Exception:
        logger.debug("intel_hub: S/R context failed for %s", symbol)

    weekly_trend = {}
    try:
        weekly_df, wmas = get_weekly_bars(symbol)
        if not weekly_df.empty:
            last_bar = weekly_df.iloc[-1]
            weekly_trend = {
                "close": round(float(last_bar["Close"]), 2),
                "open": round(float(last_bar["Open"]), 2),
                "direction": "up" if last_bar["Close"] >= last_bar["Open"] else "down",
                **wmas,
            }
    except Exception:
        logger.debug("intel_hub: weekly trend context failed for %s", symbol)

    win_rates = {}
    try:
        all_rates = get_alert_win_rates(days=90)
        sym_rates = all_rates.get("by_symbol", {}).get(symbol)
        if sym_rates:
            win_rates = {"symbol": sym_rates, "overall": all_rates.get("overall", {})}
        else:
            win_rates = {"overall": all_rates.get("overall", {})}
    except Exception:
        logger.debug("intel_hub: win rates context failed for %s", symbol)

    paper_win_rates = {}
    try:
        paper_win_rates = get_paper_trade_win_rates(days=90)
    except Exception:
        logger.debug("intel_hub: paper win rates failed")

    return {
        "symbol": symbol,
        "fundamentals": fundamentals,
        "sr_levels": sr_levels,
        "weekly_trend": weekly_trend,
        "win_rates": win_rates,
        "paper_win_rates": paper_win_rates,
    }


# ---------------------------------------------------------------------------
# AI Scanner — batch context assembly, AI ranking, symbol parsing
# ---------------------------------------------------------------------------

def assemble_scanner_context(
    symbols: list[str],
    user_id: int | None = None,
) -> list[dict]:
    """Gather context for all watchlist symbols in batch.

    Calls get_all_daily_plans() and get_alerts_today() once each (batch),
    then per-symbol fetches intraday, prior day, and top 5 S/R levels.

    Returns list of dicts with keys: symbol, is_crypto, plan, alerts_today,
    intraday, prior_day, sr_levels.  Skips symbols where fetch_prior_day()
    returns None.
    """
    from alerting.alert_store import get_alerts_today
    from analytics.intraday_data import fetch_intraday, fetch_prior_day
    from config import is_crypto_alert_symbol
    from db import get_all_daily_plans

    session = date.today().isoformat()

    # Batch calls — one DB hit each
    all_plans = get_all_daily_plans(session) or []
    plans_by_sym = {p["symbol"]: p for p in all_plans}

    all_alerts = get_alerts_today(session, user_id=user_id) or []
    alerts_by_sym: dict[str, list[dict]] = {}
    for a in all_alerts:
        alerts_by_sym.setdefault(a.get("symbol", ""), []).append(a)

    results: list[dict] = []
    for sym in symbols:
        try:
            prior = fetch_prior_day(sym)
            if prior is None:
                continue

            # Intraday snapshot
            intra_df = fetch_intraday(sym)
            intraday_info: dict = {}
            if not intra_df.empty:
                cur = float(intra_df["Close"].iloc[-1])
                day_high = float(intra_df["High"].max())
                day_low = float(intra_df["Low"].min())
                prev_close = prior.get("close", cur)
                change_pct = (
                    round((cur - prev_close) / prev_close * 100, 2)
                    if prev_close
                    else 0.0
                )
                intraday_info = {
                    "current_price": round(cur, 2),
                    "day_high": round(day_high, 2),
                    "day_low": round(day_low, 2),
                    "change_pct": change_pct,
                }

            # Prior day subset (keep prompt compact)
            prior_day_info = {
                "close": prior.get("close"),
                "high": prior.get("high"),
                "low": prior.get("low"),
                "ma20": prior.get("ma20"),
                "ma50": prior.get("ma50"),
                "ema20": prior.get("ema20"),
                "ema50": prior.get("ema50"),
                "rsi14": prior.get("rsi14"),
                "pattern": prior.get("pattern"),
                "direction": prior.get("direction"),
            }

            # Top 5 S/R levels
            sr = []
            try:
                sr = get_sr_levels(sym)[:5]
            except Exception:
                logger.debug("scanner: S/R failed for %s", sym)

            # Detect stop invalidation
            sym_alerts = alerts_by_sym.get(sym, [])
            _STOP_TYPES = {"stop_loss_hit", "auto_stop_out"}
            invalidated = any(
                a.get("alert_type") in _STOP_TYPES for a in sym_alerts
            )

            reprojected_plan = None
            if invalidated:
                try:
                    from analytics.signal_engine import reproject_after_stop

                    cur_price = intraday_info.get("current_price") or prior.get("close", 0)
                    plan_data = plans_by_sym.get(sym) or {}
                    broken_stop = plan_data.get("stop", 0)
                    if cur_price and broken_stop:
                        reprojected_plan = reproject_after_stop(
                            current_price=cur_price,
                            broken_stop=broken_stop,
                            prior_low=prior.get("low", 0),
                            ma20=prior.get("ma20"),
                            ma50=prior.get("ma50"),
                            ema20=prior.get("ema20"),
                            ema50=prior.get("ema50"),
                            prior_high=prior.get("high"),
                            pattern=prior.get("pattern") or "normal",
                        )
                except Exception:
                    logger.debug("scanner: reprojection failed for %s", sym)

            results.append({
                "symbol": sym,
                "is_crypto": is_crypto_alert_symbol(sym),
                "plan": plans_by_sym.get(sym),
                "alerts_today": sym_alerts,
                "intraday": intraday_info,
                "prior_day": prior_day_info,
                "sr_levels": sr,
                "invalidated": invalidated,
                "reprojected_plan": reprojected_plan,
            })
        except Exception:
            logger.debug("scanner: context assembly failed for %s", sym)
            continue

    return results


def compute_scanner_rank(blob: dict) -> dict:
    """Compute a deterministic 0-100 scanner rank for a symbol blob.

    Factors: trend (0-30), entry proximity to key MAs (0-35),
    RSI (0-20), setup quality (0-15).

    Returns dict with rank_score, rank_label, factor breakdowns,
    nearest_ma info, and a one-line edge description.
    """
    from config import MEGA_CAP, categorize_symbol

    prior = blob.get("prior_day") or {}
    intra = blob.get("intraday") or {}
    plan = blob.get("plan") or {}
    alerts = blob.get("alerts_today") or []

    price = intra.get("current_price") or prior.get("close") or 0
    if not price:
        return {
            "rank_score": 0, "rank_label": "C",
            "trend_pts": 0, "proximity_pts": 0, "rsi_pts": 0, "setup_pts": 0,
            "nearest_ma": "N/A", "nearest_ma_price": 0,
            "nearest_ma_dist_pct": 0, "edge": "No price data",
        }

    # -- Factor 1: Trend (0-30) --
    ma50 = prior.get("ma50")
    ema50 = prior.get("ema50")
    above_ma50 = ma50 is not None and price > ma50
    above_ema50 = ema50 is not None and price > ema50
    if above_ma50 and above_ema50:
        trend_pts = 30
    elif above_ma50 or above_ema50:
        trend_pts = 15
    else:
        trend_pts = 0

    # -- Factor 2: Entry Proximity to Key MAs (0-35) --
    ma_candidates = [
        ("20 SMA", prior.get("ma20")),
        ("20 EMA", prior.get("ema20")),
        ("50 SMA", ma50),
        ("50 EMA", ema50),
    ]
    nearest_ma = "N/A"
    nearest_ma_price = 0.0
    nearest_ma_dist_pct = 999.0

    for label, ma_val in ma_candidates:
        if ma_val and ma_val > 0:
            dist = abs(price - ma_val) / ma_val * 100
            if dist < nearest_ma_dist_pct:
                nearest_ma = label
                nearest_ma_price = ma_val
                nearest_ma_dist_pct = dist

    # Determine proximity points based on nearest MA
    proximity_pts = 5  # default: farther away
    if nearest_ma_dist_pct <= 999:
        is_20ma = "20" in nearest_ma
        is_50ma = "50" in nearest_ma
        if is_20ma and nearest_ma_dist_pct <= 0.5:
            proximity_pts = 35
        elif is_20ma and nearest_ma_dist_pct <= 1.0:
            proximity_pts = 28
        elif is_50ma and nearest_ma_dist_pct <= 0.5:
            proximity_pts = 30
        elif is_50ma and nearest_ma_dist_pct <= 1.0:
            proximity_pts = 22
        elif nearest_ma_dist_pct <= 2.0:
            proximity_pts = 15

    # -- Factor 3: RSI (0-20) --
    rsi = prior.get("rsi14")
    is_mega = categorize_symbol(blob.get("symbol", "")) == "mega_cap"
    rsi_pts = 5  # default
    if rsi is not None:
        if is_mega and 28 <= rsi <= 35:
            rsi_pts = 20
        elif rsi < 28:
            rsi_pts = 5  # knife-catch
        elif 28 <= rsi <= 35:
            rsi_pts = 15  # non-mega in same band gets normal score
        elif 35 < rsi <= 45:
            rsi_pts = 15
        elif 45 < rsi <= 55:
            rsi_pts = 10
        elif 55 < rsi <= 65:
            rsi_pts = 8
        elif rsi > 70:
            rsi_pts = 3

    # -- Factor 4: Setup Quality (0-15) --
    setup_pts = 0
    pattern = prior.get("pattern") or ""
    if pattern.lower() == "inside":
        setup_pts += 5
    direction = prior.get("direction") or ""
    if direction.lower() in ("up", "bullish"):
        setup_pts += 5
    has_buy_alerts = any(a.get("direction") == "BUY" for a in alerts)
    if has_buy_alerts:
        setup_pts += 5

    # -- Total --
    rank_score = trend_pts + proximity_pts + rsi_pts + setup_pts

    if rank_score >= 85:
        rank_label = "A+"
    elif rank_score >= 70:
        rank_label = "A"
    elif rank_score >= 50:
        rank_label = "B"
    else:
        rank_label = "C"

    # -- Stop invalidation penalty --
    invalidated = blob.get("invalidated", False)
    reprojected = blob.get("reprojected_plan")

    if invalidated:
        if reprojected:
            edge = (
                f"STOPPED OUT — reprojected to "
                f"{reprojected['support_label']} at {reprojected['support']:.2f}"
            )
            rank_score = max(20, rank_score - 30)
        else:
            edge = "STOPPED OUT — no valid support below"
            rank_score = max(0, rank_score - 30)
    else:
        # Richer edge description
        edge_parts = []
        if nearest_ma != "N/A" and nearest_ma_dist_pct < 5:
            trend_word = "uptrend" if trend_pts >= 15 else "downtrend"
            edge_parts.append(
                f"Entry at {nearest_ma} support ({nearest_ma_price:.2f}) "
                f"in {trend_word}"
            )
        if rsi is not None:
            edge_parts.append(f"RSI {rsi:.0f}")
        # R:R from plan
        plan_rr = None
        if plan.get("entry") and plan.get("stop") and plan.get("target_1"):
            p_entry = plan["entry"]
            p_stop = plan["stop"]
            p_t1 = plan["target_1"]
            p_risk = p_entry - p_stop
            if p_risk > 0:
                plan_rr = round((p_t1 - p_entry) / p_risk, 1)
                edge_parts.append(f"{plan_rr}:1 R/R")
        if pattern.lower() == "inside":
            edge_parts.append("Inside day")
        edge = ", ".join(edge_parts) if edge_parts else "No clear edge"

    # Recalculate label after penalty
    if rank_score >= 85:
        rank_label = "A+"
    elif rank_score >= 70:
        rank_label = "A"
    elif rank_score >= 50:
        rank_label = "B"
    else:
        rank_label = "C"

    return {
        "rank_score": rank_score,
        "rank_label": rank_label,
        "trend_pts": trend_pts,
        "proximity_pts": proximity_pts,
        "rsi_pts": rsi_pts,
        "setup_pts": setup_pts,
        "nearest_ma": nearest_ma,
        "nearest_ma_price": round(nearest_ma_price, 2),
        "nearest_ma_dist_pct": round(nearest_ma_dist_pct, 2),
        "edge": edge,
    }
