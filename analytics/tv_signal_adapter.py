"""Phase 5a (2026-04-25) — TradingView webhook payload → internal AlertSignal.

TradingView Premium delivers JSON to a webhook URL when an alert fires. This
adapter parses TV's payload format (interval as single letters, prices as
strings, ISO 8601 timestamps), validates required fields, and converts to
the internal `AlertSignal` shape used by the rest of the alerting pipeline.

Sample TV payload (validated live 2026-04-25):
    {
      "symbol": "ETHUSD",
      "exchange": "COINBASE",
      "interval": "D",
      "price": "2311.30",
      "high": "2323.79",
      "low": "2301.18",
      "volume": "21065.37478612",
      "rule": "rsi_below_57_71",
      "direction": "BUY",
      "fired_at": "2026-04-25T18:05:14Z"
    }

Per the user's design choice (2026-04-25), `direction` is an EXPLICIT field
the Pine Script must include — no inference from rule name. Defaults to
"NOTICE" if absent so a misconfigured Pine Script can't silently fire as
LONG / SHORT.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from analytics.intraday_rules import AlertSignal, AlertType

logger = logging.getLogger(__name__)


# TradingView interval string → our internal canonical interval label.
# TV uses single-letter codes for D/W/M and minute counts for intraday.
INTERVAL_MAP: dict[str, str] = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "45": "45m",
    "60": "1h",
    "120": "2h",
    "180": "3h",
    "240": "4h",
    "D": "1d",
    "1D": "1d",
    "W": "1w",
    "1W": "1w",
    "M": "1mo",
    "1M": "1mo",
}


# Map direction strings from TV payload to internal direction values used by
# the rule engine. "NOTICE" is the safe fallback so misconfigured Pine
# Scripts surface as informational rather than tradable signals.
_VALID_DIRECTIONS = {"BUY", "LONG", "SHORT", "SELL", "NOTICE"}


class TVAdapterError(ValueError):
    """Raised when a TV payload cannot be converted into an AlertSignal."""


def normalize_symbol(symbol: str, exchange: str = "") -> str:
    """Strip exchange prefix from TV ticker if present.

    Examples:
        normalize_symbol("COINBASE:ETHUSD") -> "ETHUSD"
        normalize_symbol("ETHUSD", "COINBASE") -> "ETHUSD"
        normalize_symbol("NASDAQ:AAPL") -> "AAPL"
    """
    if not symbol:
        raise TVAdapterError("symbol is required")
    sym = symbol.strip().upper()
    if ":" in sym:
        sym = sym.split(":", 1)[1]
    return sym


def normalize_interval(interval: str) -> str:
    """Map TV interval code → canonical label. Falls back to the raw value."""
    if not interval:
        return ""
    key = interval.strip().upper()
    return INTERVAL_MAP.get(key, key.lower())


def parse_fired_at(value: str) -> datetime | None:
    """Parse TV's ISO 8601 timestamp (`2026-04-25T18:05:14Z`).

    Returns None on parse failure rather than raising, since the timestamp
    is informational only — alert routing doesn't depend on it.
    """
    if not value:
        return None
    try:
        # TV always sends UTC with `Z` suffix; convert to fromisoformat-friendly.
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        logger.debug("TV adapter: could not parse fired_at=%r", value)
        return None


def _to_float(value: Any, field: str) -> float:
    """Cast TV's stringified numeric to float. Raises if conversion fails."""
    if value is None:
        raise TVAdapterError(f"{field} is required")
    try:
        return float(value)
    except (ValueError, TypeError) as e:
        raise TVAdapterError(f"{field} must be numeric, got {value!r}") from e


def _to_float_optional(value: Any) -> float | None:
    """Cast to float; return None if value is missing/blank/invalid."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def normalize_direction(value: str) -> str:
    """Validate direction against allowed set. Returns 'NOTICE' on bad input.

    Per Phase 5a design, direction is EXPLICIT in the payload — Pine Script
    must include `"direction": "BUY"` (or SHORT, NOTICE). Bad/missing
    values fall through to NOTICE so they show up as heads-ups, never as
    actionable LONG/SHORT alerts.
    """
    if not value:
        return "NOTICE"
    upper = str(value).strip().upper()
    if upper in _VALID_DIRECTIONS:
        # Canonicalize: BUY/LONG → BUY, SHORT/SELL → SHORT
        if upper == "LONG":
            return "BUY"
        if upper == "SELL":
            return "SHORT"
        return upper
    logger.warning("TV adapter: invalid direction %r — coercing to NOTICE", value)
    return "NOTICE"


def payload_to_alert_signal(payload: dict[str, Any]) -> AlertSignal:
    """Convert a parsed TV webhook JSON payload into an AlertSignal.

    Required fields: symbol, price, rule.
    Optional: exchange, interval, high, low, volume, direction, fired_at,
              entry, stop, target_1, target_2.

    If direction is NOTICE (default) or no entry/stop supplied, the signal
    fires as informational. If entry/stop are provided, the helper does NOT
    compute targets here — the route invokes _targets_for_long/_short with
    prior_day data after the AlertSignal is built.

    Raises TVAdapterError on missing required fields or non-numeric prices.
    """
    if not isinstance(payload, dict):
        raise TVAdapterError("payload must be a JSON object")

    symbol = normalize_symbol(
        payload.get("symbol", ""),
        payload.get("exchange", ""),
    )
    rule = (payload.get("rule") or "").strip()
    if not rule:
        raise TVAdapterError("rule is required")

    price = _to_float(payload.get("price"), "price")
    direction = normalize_direction(payload.get("direction", ""))
    interval_label = normalize_interval(payload.get("interval", ""))

    # Optional numerics
    high = _to_float_optional(payload.get("high"))
    low = _to_float_optional(payload.get("low"))
    volume = _to_float_optional(payload.get("volume"))
    entry = _to_float_optional(payload.get("entry"))
    stop = _to_float_optional(payload.get("stop"))
    target_1 = _to_float_optional(payload.get("target_1"))
    target_2 = _to_float_optional(payload.get("target_2"))

    # If Pine Script didn't supply entry/stop and direction is BUY/SHORT,
    # we use price as entry and let the route compute stop+targets via
    # Phase 4a structural targets (stop = price ± risk pct as fallback).
    if direction in ("BUY", "SHORT") and entry is None:
        entry = price

    fired_at = parse_fired_at(payload.get("fired_at", ""))

    # Build the message — keep it explicit so the user sees the rule name.
    msg_parts = [f"[TV] {rule}"]
    if interval_label:
        msg_parts.append(f"({interval_label})")
    if direction == "NOTICE":
        msg_parts.append("— heads-up only")
    message = " ".join(msg_parts)

    sig = AlertSignal(
        symbol=symbol,
        alert_type=AlertType.TV_WEBHOOK,
        direction=direction,
        price=price,
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence="medium",  # TV alerts default to medium; route can boost
        message=message,
        volume_label="",
        score=50,  # neutral baseline; HTF gate / confluence can adjust
    )
    # Stash extra TV metadata on the signal for downstream use (notifier,
    # alerts.source column, debug logging). AlertSignal is a regular dataclass
    # so attribute attachment works.
    sig._tv_rule = rule  # type: ignore[attr-defined]
    sig._tv_high = high  # type: ignore[attr-defined]
    sig._tv_low = low  # type: ignore[attr-defined]
    sig._tv_volume = volume  # type: ignore[attr-defined]
    sig._tv_interval = interval_label  # type: ignore[attr-defined]
    sig._tv_fired_at = fired_at  # type: ignore[attr-defined]
    sig._source = "tradingview"  # type: ignore[attr-defined]

    return sig
