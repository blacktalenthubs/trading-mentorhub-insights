"""AI Coach — Best Setups of the Day.

On-demand scanner: user clicks "Analyze my watchlist" and gets two ranked
lists of symbols currently NEAR key entry levels:
  - day_trade_picks  (intraday levels: VWAP, session H/L, PDH/PDL, prior close)
  - swing_trade_picks (daily levels: 20/50/100/200 MA+EMA, weekly/monthly H/L)

No R:R math — the goal is to surface symbols positioned at meaningful levels
right now. Proximity gate: entry must be within 2% of current price.
SHORT picks are allowed on SPY only (consistent with the rest of the system).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SONNET

logger = logging.getLogger(__name__)

MAX_SYMBOLS = 25
MAX_PROXIMITY_PCT = 2.0  # entry must be within 2% of current price

_CONVICTION_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclass
class EntryCandidate:
    symbol: str
    timeframe: str              # "day" or "swing"
    direction: str              # LONG / SHORT
    setup_type: str
    entry: float
    stop: Optional[float]
    t1: Optional[float]
    t2: Optional[float]
    conviction: str             # HIGH / MEDIUM / LOW
    confluence: list[str]
    why_now: str
    current_price: float
    distance_to_entry_pct: float


@dataclass
class BestSetupsResult:
    generated_at: str
    watchlist_size: int
    day_trade_picks: list[dict] = field(default_factory=list)
    swing_trade_picks: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# ── Validation ───────────────────────────────────────────────────────


def _coerce_optional_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _validate_pick(
    pick: dict, current_price: float, symbol: str, timeframe: str
) -> tuple[bool, Optional[str]]:
    """Lightweight validation: direction, SHORT-SPY-only, entry proximity.

    Returns (ok, skip_reason).
    """
    direction = (pick.get("direction") or "").upper()
    if direction not in ("LONG", "SHORT"):
        return False, f"unknown direction: {direction}"

    if direction == "SHORT" and symbol.upper() != "SPY":
        return False, "SHORT only allowed on SPY"

    try:
        entry = float(pick.get("entry") or 0)
    except (TypeError, ValueError):
        return False, "entry not numeric"
    if entry <= 0:
        return False, "missing entry"

    if current_price <= 0:
        return False, "no current price"

    distance_pct = abs(entry - current_price) / current_price * 100
    if distance_pct > MAX_PROXIMITY_PCT:
        return False, f"entry {distance_pct:.1f}% from price (>{MAX_PROXIMITY_PCT}%)"

    if timeframe not in ("day", "swing"):
        return False, f"unknown timeframe: {timeframe}"

    return True, None


# ── Response parser ──────────────────────────────────────────────────


def _parse_ai_response(text: str) -> tuple[list[dict], list[dict]]:
    """Parse JSON object with day_trade_picks + swing_trade_picks arrays."""
    if not text:
        return [], []
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        logger.warning("best_setups: no JSON object found in response")
        return [], []
    snippet = text[start : end + 1]
    try:
        obj = json.loads(snippet)
    except json.JSONDecodeError:
        logger.warning("best_setups: JSON decode failed")
        return [], []
    day = obj.get("day_trade_picks") or []
    swing = obj.get("swing_trade_picks") or []
    if not isinstance(day, list):
        day = []
    if not isinstance(swing, list):
        swing = []
    return day, swing


# ── Prompt builder ───────────────────────────────────────────────────


def _build_batch_prompt(symbols_data: list[dict]) -> str:
    """Build a single Sonnet prompt with all symbols' data."""
    prompt = (
        "You are a trading analyst scanning a watchlist for symbols NEAR KEY\n"
        "ENTRY LEVELS right now. For each symbol, decide if price is within 2%\n"
        "of a meaningful level and output up to two picks per symbol:\n"
        "  - one day_trade pick (intraday levels)\n"
        "  - one swing_trade pick (daily levels)\n\n"
        "DAY TRADE LEVELS (intraday):\n"
        "- Session VWAP\n"
        "- Session high / low\n"
        "- Prior day high / low (PDH / PDL)\n"
        "- Prior close\n\n"
        "SWING TRADE LEVELS (daily):\n"
        "- 20 / 50 / 100 / 200 day MA\n"
        "- 20 / 50 / 100 / 200 day EMA\n"
        "- Weekly high / low\n"
        "- Monthly high / low\n\n"
        "SKIP symbols that are mid-range (no level within 2% of current price).\n"
        "SHORT policy: only recommend SHORT on SPY. Skip SHORT for other symbols.\n"
        "Setups should be LONG bounces at support, or (SPY only) SHORT rejections at resistance.\n\n"
        "OUTPUT — strict JSON object with two arrays:\n"
        "{\n"
        '  "day_trade_picks": [\n'
        "    {\n"
        '      "symbol": "<str>",\n'
        '      "direction": "LONG" | "SHORT",\n'
        '      "setup_type": "<free-text, 3-8 words: e.g. VWAP bounce, PDH reclaim>",\n'
        '      "entry": <number within 2% of current price>,\n'
        '      "stop": <number or null>,\n'
        '      "t1": <number or null>,\n'
        '      "t2": <number or null>,\n'
        '      "conviction": "HIGH" | "MEDIUM" | "LOW",\n'
        '      "confluence": ["<level1>", "<level2>"],\n'
        '      "why_now": "<1 short sentence>"\n'
        "    }\n"
        "  ],\n"
        '  "swing_trade_picks": [ <same shape> ]\n'
        "}\n"
        "- entry MUST be within 2% of current price\n"
        "- stop/t1/t2 optional — include only when obvious, else null\n"
        "- rank each array: HIGH conviction first, then closest-to-entry first\n"
        "- return empty arrays if no symbols qualify\n"
        "- output ONLY the JSON object. No prose, no code fences.\n\n"
        "[WATCHLIST DATA]\n"
    )

    for d in symbols_data:
        sym = d["symbol"]
        price = d.get("current_price", 0)
        pd_ = d.get("prior_day") or {}
        bars = d.get("bars_5m") or []

        parts = [f"\n--- {sym} ---", f"Current price: ${price:.2f}"]

        # Intraday anchors
        intraday = []
        vwap = d.get("vwap")
        if vwap:
            intraday.append(f"VWAP ${vwap:.2f}")
        sh = d.get("session_high")
        sl = d.get("session_low")
        if sh:
            intraday.append(f"SessHi ${sh:.2f}")
        if sl:
            intraday.append(f"SessLo ${sl:.2f}")
        for key, label in [("high", "PDH"), ("low", "PDL"), ("close", "PrevClose")]:
            v = pd_.get(key)
            if v:
                intraday.append(f"{label} ${v:.2f}")
        if intraday:
            parts.append("Intraday: " + " · ".join(intraday))

        # Daily MAs/EMAs
        ma_parts = []
        for key, label in [
            ("ma20", "20MA"), ("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
            ("ema20", "20EMA"), ("ema50", "50EMA"),
            ("ema100", "100EMA"), ("ema200", "200EMA"),
        ]:
            v = pd_.get(key)
            if v:
                ma_parts.append(f"{label} ${v:.2f}")
        if ma_parts:
            parts.append("Daily MAs: " + " · ".join(ma_parts))

        # Weekly / monthly
        wm = []
        for key, label in [
            ("prior_week_high", "WeekHi"), ("prior_week_low", "WeekLo"),
            ("prior_month_high", "MonHi"), ("prior_month_low", "MonLo"),
        ]:
            v = pd_.get(key)
            if v:
                wm.append(f"{label} ${v:.2f}")
        if wm:
            parts.append("Weekly/Monthly: " + " · ".join(wm))

        rsi = pd_.get("rsi14")
        if rsi is not None:
            parts.append(f"RSI14: {rsi:.1f}")

        if bars:
            parts.append(f"Last {min(len(bars), 10)} × 5m bars:")
            for b in bars[-10:]:
                parts.append(
                    f"  O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                    f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
                )

        prompt += "\n".join(parts) + "\n"

    return prompt


# ── Data fetching ────────────────────────────────────────────────────


def _fetch_symbol_data(symbol: str) -> Optional[dict]:
    """Fetch current price + prior_day + last 10 × 5m bars + session VWAP/H/L."""
    from analytics.intraday_data import fetch_prior_day, fetch_intraday, fetch_intraday_crypto
    from config import is_crypto_alert_symbol

    try:
        is_crypto = is_crypto_alert_symbol(symbol)
        prior = fetch_prior_day(symbol, is_crypto=is_crypto)
        bars_df = (
            fetch_intraday_crypto(symbol, interval="5m")
            if is_crypto else fetch_intraday(symbol, interval="5m")
        )
        if bars_df is None or (hasattr(bars_df, "empty") and bars_df.empty):
            return None
        current_price = float(bars_df.iloc[-1]["Close"])
        bars = [
            {
                "open": float(r["Open"]), "high": float(r["High"]),
                "low": float(r["Low"]), "close": float(r["Close"]),
                "volume": float(r["Volume"]),
            }
            for _, r in bars_df.tail(10).iterrows()
        ]

        # Session stats from today's full 5m bar set (not just last 10)
        session_high = float(bars_df["High"].max()) if len(bars_df) > 0 else None
        session_low = float(bars_df["Low"].min()) if len(bars_df) > 0 else None
        vwap: Optional[float] = None
        try:
            tp = (bars_df["High"] + bars_df["Low"] + bars_df["Close"]) / 3.0
            vol = bars_df["Volume"]
            total_vol = float(vol.sum())
            if total_vol > 0:
                vwap = float((tp * vol).sum() / total_vol)
        except Exception:
            vwap = None

        return {
            "symbol": symbol,
            "current_price": current_price,
            "prior_day": prior or {},
            "bars_5m": bars,
            "session_high": session_high,
            "session_low": session_low,
            "vwap": vwap,
        }
    except Exception:
        logger.exception("best_setups: fetch failed for %s", symbol)
        return None


# ── Anthropic call ───────────────────────────────────────────────────


def _call_sonnet(prompt: str, api_key: str) -> str:
    """Single Sonnet call. Returns text, raises on failure."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    start = time.time()
    response = client.messages.create(
        model=CLAUDE_MODEL_SONNET,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
        timeout=30.0,
    )
    elapsed = time.time() - start
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost = (tokens_in * 3 + tokens_out * 15) / 1_000_000
    logger.info(
        "best_setups sonnet: %.1fs tokens=%d/%d cost=$%.4f",
        elapsed, tokens_in, tokens_out, cost,
    )
    return response.content[0].text.strip()


# ── Cache (module-level, 15-min TTL) ─────────────────────────────────


_cache: dict[tuple[int, str], tuple[datetime, BestSetupsResult]] = {}
_CACHE_TTL_SEC = 900


def _cache_get(user_id: int, wl_hash: str) -> Optional[BestSetupsResult]:
    key = (user_id, wl_hash)
    entry = _cache.get(key)
    if not entry:
        return None
    ts, result = entry
    if (datetime.now() - ts).total_seconds() > _CACHE_TTL_SEC:
        del _cache[key]
        return None
    return result


def _cache_set(user_id: int, wl_hash: str, result: BestSetupsResult) -> None:
    _cache[(user_id, wl_hash)] = (datetime.now(), result)


def _watchlist_hash(symbols: list[str]) -> str:
    import hashlib
    sorted_s = ",".join(sorted(s.upper() for s in symbols))
    return hashlib.md5(sorted_s.encode()).hexdigest()[:12]


# ── Pick enrichment ──────────────────────────────────────────────────


def _enrich_picks(
    raw: list[dict],
    timeframe: str,
    price_by_symbol: dict[str, float],
    failed: list[dict],
) -> list[dict]:
    """Validate + normalize raw AI picks for one timeframe."""
    out: list[dict] = []
    for p in raw:
        sym = (p.get("symbol") or "").upper()
        cur = price_by_symbol.get(sym)
        if cur is None:
            failed.append({"symbol": sym, "reason": "not in fetched data"})
            continue
        ok, reason = _validate_pick(p, cur, sym, timeframe)
        if not ok:
            failed.append({"symbol": sym, "reason": f"[{timeframe}] {reason}"})
            continue
        entry = float(p["entry"])
        enriched = asdict(EntryCandidate(
            symbol=sym,
            timeframe=timeframe,
            direction=(p.get("direction") or "").upper(),
            setup_type=(p.get("setup_type") or "")[:120],
            entry=entry,
            stop=_coerce_optional_float(p.get("stop")),
            t1=_coerce_optional_float(p.get("t1")),
            t2=_coerce_optional_float(p.get("t2")),
            conviction=(p.get("conviction") or "MEDIUM").upper(),
            confluence=list(p.get("confluence") or [])[:5],
            why_now=(p.get("why_now") or "")[:300],
            current_price=cur,
            distance_to_entry_pct=round(abs(entry - cur) / cur * 100, 2),
        ))
        out.append(enriched)

    out.sort(key=lambda x: (
        _CONVICTION_ORDER.get(x["conviction"], 3),
        x["distance_to_entry_pct"],
    ))
    return out


# ── Main orchestrator ────────────────────────────────────────────────


def generate_best_setups(user_id: int, sync_session_factory) -> BestSetupsResult:
    """Load user's watchlist, call AI, validate picks, return ranked result."""
    if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0", "no"):
        return BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=0,
            error="feature disabled",
        )

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        return BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=0,
            error="no anthropic key",
        )

    from sqlalchemy import select
    from app.models.watchlist import WatchlistItem

    # 1. Load watchlist
    with sync_session_factory() as db:
        rows = db.execute(
            select(WatchlistItem.symbol).where(WatchlistItem.user_id == user_id)
        ).all()
    symbols = [r[0] for r in rows]

    # Cap + cache check
    if len(symbols) > MAX_SYMBOLS:
        logger.warning("best_setups: watchlist %d symbols, capping at %d", len(symbols), MAX_SYMBOLS)
        symbols = symbols[:MAX_SYMBOLS]

    wl_hash = _watchlist_hash(symbols)
    cached = _cache_get(user_id, wl_hash)
    if cached:
        logger.info("best_setups: cache hit user=%d", user_id)
        return cached

    if not symbols:
        result = BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=0,
        )
        _cache_set(user_id, wl_hash, result)
        return result

    # 2. Parallel fetch
    fetched: list[dict] = []
    failed: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_fetch_symbol_data, s): s for s in symbols}
        for fut in as_completed(futures, timeout=20):
            sym = futures[fut]
            try:
                data = fut.result(timeout=15)
                if data:
                    fetched.append(data)
                else:
                    failed.append({"symbol": sym, "reason": "no data"})
            except Exception:
                failed.append({"symbol": sym, "reason": "fetch timeout"})

    if not fetched:
        result = BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=len(symbols),
            skipped=failed,
            error="no data for any symbol",
        )
        _cache_set(user_id, wl_hash, result)
        return result

    # 3. Build prompt
    prompt = _build_batch_prompt(fetched)

    # 4. Call Sonnet
    try:
        ai_text = _call_sonnet(prompt, api_key)
    except Exception as e:
        logger.exception("best_setups: sonnet call failed")
        return BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=len(symbols),
            skipped=failed,
            error=f"AI call failed: {str(e)[:80]}",
        )

    # 5. Parse → two arrays
    raw_day, raw_swing = _parse_ai_response(ai_text)

    # 6. Validate + enrich
    price_by_symbol = {d["symbol"]: d["current_price"] for d in fetched}
    day_picks = _enrich_picks(raw_day, "day", price_by_symbol, failed)
    swing_picks = _enrich_picks(raw_swing, "swing", price_by_symbol, failed)

    result = BestSetupsResult(
        generated_at=datetime.now().isoformat(),
        watchlist_size=len(symbols),
        day_trade_picks=day_picks,
        swing_trade_picks=swing_picks,
        skipped=failed,
    )
    _cache_set(user_id, wl_hash, result)
    logger.info(
        "best_setups: user=%d wl=%d day=%d swing=%d skipped=%d",
        user_id, len(symbols), len(day_picks), len(swing_picks), len(failed),
    )
    return result
