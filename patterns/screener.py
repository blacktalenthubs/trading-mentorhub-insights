"""Breakout screener — the orchestrator. For each symbol: fetch daily bars, add indicators,
run the pre-filter (counting the funnel), run each enabled detector, and build the Today-tab
row (buy_point / stop / risk / score / reason). Breakouts first, then forming; each by score.

The point is to narrow to a handful worth eyeballing — false negatives are cheap, false
positives waste time. Every threshold lives in config; nothing is hardcoded here.
"""
from __future__ import annotations

import datetime as _dt
import logging

from patterns.config import CONFIG, PatternConfig
from patterns.detect_utils import PREFILTER_GATES, compose_score, prefilter
from patterns.indicators import add_indicators

logger = logging.getLogger("patterns.screener")

# name → module.detect
from patterns import (ascending_triangle, bull_flag, cup_handle, flat_base,  # noqa: E402
                      horizontal_tba, trendline_break)

_DETECTORS = {
    "cup_handle": cup_handle.detect,
    "flat_base": flat_base.detect,
    "ascending_triangle": ascending_triangle.detect,
    "bull_flag": bull_flag.detect,
    "horizontal_tba": horizontal_tba.detect,
    "trendline_break": trendline_break.detect,
}

_STAGE_LABEL = {"cup_handle": "cup & handle", "flat_base": "flat base",
                "ascending_triangle": "ascending triangle", "bull_flag": "bull flag",
                "horizontal_tba": "TBA breakout", "trendline_break": "trendline break"}


def _default_fetch(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="4y", interval="1d")
    return None if df is None or df.empty else df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])


def _earnings_days(sym):  # pragma: no cover - network
    try:
        from analytics.premium_desk_scan import _earnings_days as _ed
        return _ed(sym)
    except Exception:
        return None


def _row(sym, df, hit, cfg):
    last = df.iloc[-1]
    last_close = float(last["Close"])
    bp = hit["buy_point"]
    stop = hit["suggested_stop"]
    score = compose_score(hit["_parts"], df, cfg)
    dist_200 = (last_close - float(last["sma200"])) / float(last["sma200"]) * 100.0 if last["sma200"] else None
    pct_to_buy = (bp - last_close) / last_close * 100.0 if last_close else 0.0
    # Entry = where you'd actually get in: at the trigger for a forming setup, at market for a
    # confirmed breakout. Risk is measured FROM that entry to the stop — the real number to size on.
    entry = last_close if hit["stage"] == "breakout" else bp
    entry_risk = (entry - stop) / entry * 100.0 if entry else None
    near = hit["stage"] == "breakout" or pct_to_buy <= cfg.max_pct_to_trigger
    tight = entry_risk is not None and entry_risk <= cfg.max_setup_risk_pct
    actionable = bool(near and tight)
    if actionable:
        why = "actionable now"
    elif not near:
        why = f"watch — {pct_to_buy:.1f}% below the trigger"
    else:
        why = f"watch — wide {entry_risk:.0f}% stop"
    note = (f"breakout on {hit['rvol']}x volume" if hit["stage"] == "breakout"
            else (f"{pct_to_buy:.1f}% to trigger" if bp > last_close else "at the trigger"))
    return {
        "ticker": sym,
        "pattern": hit["pattern"],
        "stage": hit["stage"],
        "buy_point": bp,
        "last_close": round(last_close, 2),
        "pct_to_buy": round(pct_to_buy, 2) if last_close else None,
        "suggested_stop": stop,
        "risk_pct": round(entry_risk, 2) if entry_risk is not None else None,   # risk from the entry (trigger/market)
        "actionable": actionable,
        "entry_status": why,
        "rvol": hit["rvol"],
        "volume_ok": hit["volume_ok"],
        "base_depth_pct": hit["base_depth_pct"],
        "base_length_days": hit["base_length_days"],
        "rsi14": round(float(last["rsi14"]), 1) if last["rsi14"] == last["rsi14"] else None,
        "dist_from_200sma_pct": round(dist_200, 1) if dist_200 is not None else None,
        "score": score,
        "reason": ", ".join(hit["reason_bits"] + [note]),
        "scanned_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def scan(symbols, cfg: PatternConfig = CONFIG, earnings_filter: bool = False, fetch=None) -> dict:
    fetch = fetch or _default_fetch
    funnel = {"scanned": 0, "no_data": 0, "too_few_bars": 0, "earnings": 0}
    funnel.update({g: 0 for g in PREFILTER_GATES})
    funnel["passed_prefilter"] = 0
    rows = []
    for sym in symbols:
        sym = sym.upper()
        funnel["scanned"] += 1
        try:
            df = fetch(sym)
            if df is None or df.empty:
                funnel["no_data"] += 1
                logger.info("skip %s: no data", sym)
                continue
            if len(df) < cfg.min_bars:
                funnel["too_few_bars"] += 1
                logger.info("skip %s: only %d bars (< %d)", sym, len(df), cfg.min_bars)
                continue
            df = add_indicators(df, cfg)
            gate = prefilter(df, cfg)
            if gate:
                funnel[gate] += 1
                continue
            funnel["passed_prefilter"] += 1
            if earnings_filter:
                ed = _earnings_days(sym)
                if ed is not None and 0 <= ed <= cfg.earnings_block_days:
                    funnel["earnings"] += 1
                    continue
            for name in cfg.patterns_enabled:
                det = _DETECTORS.get(name)
                if det is None:
                    continue
                try:
                    hit = det(df, cfg)
                except Exception:
                    logger.exception("%s detector crashed on %s", name, sym)
                    hit = None
                if not hit:
                    continue
                last_close = float(df["Close"].iloc[-1])
                # Freshness guards (spec: "narrow to a handful; when in doubt, tighten"):
                #  • a "forming" setup whose price is already above the trigger broke out days ago
                #    (a chase, not a setup) — drop it. A genuine breakout is stage="breakout".
                #  • price already below the max stop = the setup is invalidated — drop it.
                if hit["stage"] == "forming" and last_close > hit["buy_point"] * 1.01:
                    continue
                if last_close <= hit["suggested_stop"]:
                    continue
                rows.append(_row(sym, df, hit, cfg))
        except Exception:
            logger.exception("scan failed for %s", sym)

    stage_rank = {"breakout": 0, "forming": 1}
    rows.sort(key=lambda r: (stage_rank.get(r["stage"], 9), -r["score"]))
    logger.info("breakout scan: %s → %d setups", {k: v for k, v in funnel.items() if v}, len(rows))
    return {"rows": rows, "scanned": funnel["scanned"], "funnel": funnel,
            "empty": len(rows) == 0}


def _label(pattern):  # for callers/tests
    return _STAGE_LABEL.get(pattern, pattern)
