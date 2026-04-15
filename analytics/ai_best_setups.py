"""AI Coach — Best Setups of the Day (Spec 40).

One call, one ranked list of tradeable setups across the user's watchlist.
AI decides what qualifies; code validates R:R, geometry, staleness, and the
SPY-only SHORT policy.
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
MIN_RR = 1.5
STALE_THRESHOLD = 0.5            # rejected if progress to T1 >= 50%
MAX_ENTRY_OUTLIER_PCT = 5.0      # reject if entry > 5% from current price


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclass
class BestSetup:
    symbol: str
    direction: str
    setup_type: str
    entry: float
    stop: float
    t1: float
    t2: Optional[float]
    risk_per_share: float
    reward_per_share: float
    rr_ratio: float
    conviction: str
    confluence: list[str]
    why_now: str
    current_price: float
    distance_to_entry_pct: float


@dataclass
class BestSetupsResult:
    generated_at: str
    watchlist_size: int
    setups_found: int
    picks: list[dict]
    skipped: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# ── R:R math ─────────────────────────────────────────────────────────


def _compute_rr(entry: float, stop: float, t1: float) -> float:
    """Risk-to-reward ratio. Always positive."""
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("zero risk (entry == stop)")
    reward = abs(t1 - entry)
    return reward / risk


# ── Validation ───────────────────────────────────────────────────────


def _validate_pick(pick: dict, current_price: float, symbol: str) -> tuple[bool, Optional[str]]:
    """Apply geometry, R:R, staleness, SPY-SHORT, outlier rules.

    Returns (ok, skip_reason).
    """
    direction = (pick.get("direction") or "").upper()
    try:
        entry = float(pick.get("entry") or 0)
        stop = float(pick.get("stop") or 0)
        t1 = float(pick.get("t1") or 0)
    except (TypeError, ValueError):
        return False, "entry/stop/t1 not numeric"

    if entry <= 0 or stop <= 0 or t1 <= 0:
        return False, "missing entry/stop/t1"

    # Directional geometry
    if direction == "LONG":
        if not (stop < entry < t1):
            return False, f"bad LONG geometry: stop<entry<t1 expected ({stop}/{entry}/{t1})"
    elif direction == "SHORT":
        if not (stop > entry > t1):
            return False, f"bad SHORT geometry: stop>entry>t1 expected"
        if symbol.upper() != "SPY":
            return False, "SHORT only allowed on SPY"
    else:
        return False, f"unknown direction: {direction}"

    # R:R
    try:
        rr = _compute_rr(entry, stop, t1)
    except ValueError as e:
        return False, str(e)
    if rr < MIN_RR:
        return False, f"R:R {rr:.2f} below {MIN_RR}"

    # Outlier check (AI hallucinated a price far from current)
    if current_price > 0:
        distance_pct = abs(entry - current_price) / current_price * 100
        if distance_pct > MAX_ENTRY_OUTLIER_PCT:
            return False, f"entry {distance_pct:.1f}% from current — outlier"

    # Staleness: progress to T1
    try:
        if direction == "LONG":
            progress = (current_price - entry) / (t1 - entry)
        else:
            progress = (entry - current_price) / (entry - t1)
    except ZeroDivisionError:
        progress = 0
    if progress > STALE_THRESHOLD:
        return False, f"stale: {int(progress*100)}% to T1"

    return True, None


# ── Response parser ──────────────────────────────────────────────────


def _parse_ai_response(text: str) -> list[dict]:
    """Tolerant JSON array parser. Returns [] on malformed response."""
    if not text:
        return []
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    # Find the first [ and last ]
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0 or end <= start:
        logger.warning("best_setups: no JSON array found in response")
        return []
    snippet = text[start : end + 1]
    try:
        arr = json.loads(snippet)
    except Exception as e:
        logger.warning("best_setups: JSON parse failed: %s", e)
        return []
    if not isinstance(arr, list):
        return []
    # Only keep dict entries with at least symbol
    return [p for p in arr if isinstance(p, dict) and p.get("symbol")]


# ── Prompt builder ───────────────────────────────────────────────────


def _build_batch_prompt(symbols_data: list[dict]) -> str:
    """Build a single Sonnet prompt with all symbols' data."""
    prompt = (
        "You are a swing/day trade analyst ranking the best setups across a user's\n"
        "watchlist for the upcoming session.\n\n"
        "Your job: for each symbol, decide if there is a TRADEABLE setup right now\n"
        "at a durable key level. Skip symbols with no clear setup. Rank the winners\n"
        "by risk-to-reward.\n\n"
        "You have FULL discretion on what qualifies. Read the data per symbol (MAs,\n"
        "PDH/PDL, weekly/monthly levels, VWAP, RSI, recent 5-min bars) and identify\n"
        "the best setup — if any. Label it in your own words.\n\n"
        "STRONG SETUP CUES:\n"
        "- Price at durable key level (daily MA, weekly high/low, monthly pivot, PDH/PDL)\n"
        "- Multi-level confluence (price at 2+ levels simultaneously)\n"
        "- RSI extreme at support (<30) or resistance (>70)\n"
        "- Flipped support/resistance (just-broken level being retested)\n"
        "- Higher-low structure at support / lower-high at resistance\n\n"
        "NOT A SETUP:\n"
        "- Price mid-range with no structural level nearby\n"
        "- Level more than 1% away from current price\n"
        "- No confluence, no structure\n\n"
        "SHORT policy: only recommend SHORT on SPY. Skip SHORT setups for other symbols.\n\n"
        "MINIMUM risk/reward: (T1-entry)/(entry-stop) >= 1.5 for LONG, mirror for SHORT.\n"
        "If you can't identify a setup with R:R >= 1.5 at a real level, skip it.\n\n"
        "OUTPUT — strict JSON array, one object per qualifying setup:\n"
        "[\n"
        "  {\n"
        "    \"symbol\": \"<str>\",\n"
        "    \"direction\": \"LONG\" | \"SHORT\",\n"
        "    \"setup_type\": \"<free-text label, ~5-10 words>\",\n"
        "    \"entry\": <number>,\n"
        "    \"stop\": <number>,\n"
        "    \"t1\": <number>,\n"
        "    \"t2\": <number or null>,\n"
        "    \"conviction\": \"HIGH\" | \"MEDIUM\" | \"LOW\",\n"
        "    \"confluence\": [\"<level1>\", \"<level2>\"],\n"
        "    \"why_now\": \"<1 sentence>\"\n"
        "  }\n"
        "]\n"
        "Return [] if no symbols have qualifying setups. Order by R:R desc.\n"
        "Output ONLY the JSON array. No prose, no code fences.\n\n"
        "[WATCHLIST DATA]\n"
    )

    for d in symbols_data:
        sym = d["symbol"]
        price = d.get("current_price", 0)
        pd_ = d.get("prior_day") or {}
        bars = d.get("bars_5m") or []

        parts = [f"\n--- {sym} ---", f"Current price: ${price:.2f}"]

        # Daily anchors
        levels_inline = []
        for key, label in [
            ("high", "PDH"), ("low", "PDL"), ("close", "Prior Close"),
        ]:
            v = pd_.get(key)
            if v:
                levels_inline.append(f"{label} ${v:.2f}")

        if levels_inline:
            parts.append(" · ".join(levels_inline))

        # MAs
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
            parts.append(" · ".join(wm))

        rsi = pd_.get("rsi14")
        if rsi is not None:
            parts.append(f"RSI14: {rsi:.1f}")

        if bars:
            parts.append(f"Last {min(len(bars), 10)} × 5m bars:")
            for b in bars[-10:]:
                parts.append(
                    f"  O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} C={b['close']:.2f} V={b.get('volume',0):.0f}"
                )

        prompt += "\n".join(parts) + "\n"

    return prompt


# ── Data fetching ────────────────────────────────────────────────────


def _fetch_symbol_data(symbol: str) -> Optional[dict]:
    """Fetch current price + prior_day + last 10 × 5m bars. None on failure."""
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
        return {
            "symbol": symbol,
            "current_price": current_price,
            "prior_day": prior or {},
            "bars_5m": bars,
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
    # Rough Sonnet 4 cost: $3/M in, $15/M out
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


# ── Main orchestrator ────────────────────────────────────────────────


def generate_best_setups(user_id: int, sync_session_factory) -> BestSetupsResult:
    """Load user's watchlist, call AI, validate picks, return ranked result."""
    if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0", "no"):
        return BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=0, setups_found=0, picks=[],
            error="feature disabled",
        )

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        return BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=0, setups_found=0, picks=[],
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
            watchlist_size=0, setups_found=0, picks=[],
            skipped=[],
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
            watchlist_size=len(symbols), setups_found=0,
            picks=[], skipped=failed,
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
        result = BestSetupsResult(
            generated_at=datetime.now().isoformat(),
            watchlist_size=len(symbols), setups_found=0,
            picks=[], skipped=failed,
            error=f"AI call failed: {str(e)[:80]}",
        )
        return result

    # 5. Parse
    raw_picks = _parse_ai_response(ai_text)

    # 6. Validate + enrich
    price_by_symbol = {d["symbol"]: d["current_price"] for d in fetched}
    valid_picks: list[dict] = []
    for p in raw_picks:
        sym = p.get("symbol", "").upper()
        cur = price_by_symbol.get(sym)
        if cur is None:
            failed.append({"symbol": sym, "reason": "not in fetched data"})
            continue
        ok, reason = _validate_pick(p, cur, sym)
        if not ok:
            failed.append({"symbol": sym, "reason": reason or "validation failed"})
            continue
        entry = float(p["entry"])
        stop = float(p["stop"])
        t1 = float(p["t1"])
        rr = _compute_rr(entry, stop, t1)
        t2 = p.get("t2")
        try:
            t2 = float(t2) if t2 is not None else None
        except (TypeError, ValueError):
            t2 = None
        enriched = asdict(BestSetup(
            symbol=sym,
            direction=(p.get("direction") or "").upper(),
            setup_type=(p.get("setup_type") or "")[:120],
            entry=entry, stop=stop, t1=t1, t2=t2,
            risk_per_share=round(abs(entry - stop), 2),
            reward_per_share=round(abs(t1 - entry), 2),
            rr_ratio=round(rr, 2),
            conviction=(p.get("conviction") or "MEDIUM").upper(),
            confluence=list(p.get("confluence") or [])[:5],
            why_now=(p.get("why_now") or "")[:300],
            current_price=cur,
            distance_to_entry_pct=round(abs(entry - cur) / cur * 100, 2) if cur else 0.0,
        ))
        valid_picks.append(enriched)

    # 7. Sort by R:R desc
    valid_picks.sort(key=lambda x: x["rr_ratio"], reverse=True)

    result = BestSetupsResult(
        generated_at=datetime.now().isoformat(),
        watchlist_size=len(symbols),
        setups_found=len(valid_picks),
        picks=valid_picks,
        skipped=failed,
    )
    _cache_set(user_id, wl_hash, result)
    logger.info(
        "best_setups: user=%d wl=%d picks=%d skipped=%d",
        user_id, len(symbols), len(valid_picks), len(failed),
    )
    return result
