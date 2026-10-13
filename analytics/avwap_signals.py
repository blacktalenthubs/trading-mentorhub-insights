"""Daily anchored-VWAP defense / rejection signals (2026-10-12, trader).

The three daily anchored-VWAP lines from the "Anchored VWAPs" Pine on the
trader's daily chart — AVWAP (swing-low anchor), AVWAP-H (pivot-high anchor),
AVWAP-R (rolling 150) — computed by analytics.intraday_data.compute_daily_avwaps
and locked for the session. This module holds the two level checks run against
those lines in monitor.py's 1h block: a support DEFENSE (BUY) and a REJECTION
(SHORT), cloned from check_hourly_vp_level / check_ma_reject_htf semantics.

Placement note: the six alert types were authored for the AlertType registry
in analytics/intraday_rules.py, but that file is ~390 KB and the connector
used to ship changes to this repo caps a single file push below that size, so
the types live here as their own str-Enum for now. The whole delivery path
(monitor dedup/gates, alert_store, notifier, pg_notify) keys off
alert_type.value strings, and AlertType itself is a str-Enum, so these
members behave identically end to end. The registry-standard copy (types +
checks inside intraday_rules.py) is preserved with the PR #1631 change record
and can be consolidated from a local clone at any time.
"""

from __future__ import annotations

from enum import Enum

from analytics.intraday_rules import AlertSignal


class AVWAPAlertType(str, Enum):
    AVWAP_SUPPORT = "avwap_support"
    AVWAP_H_SUPPORT = "avwap_h_support"
    AVWAP_R_SUPPORT = "avwap_r_support"
    AVWAP_REJECT = "avwap_reject"
    AVWAP_H_REJECT = "avwap_h_reject"
    AVWAP_R_REJECT = "avwap_r_reject"


def check_avwap_support(
    symbol: str,
    bars,
    level: "float | None",
    label: str,
    alert_type: "AVWAPAlertType",
    prox_pct: float = 0.004,
    stop_off: float = 0.007,
):
    """DAILY anchored-VWAP support hold — check_hourly_vp_level semantics with a
    daily-locked anchored-VWAP line as the level (passed in by the caller from
    compute_daily_avwaps). Fires when the LAST completed hourly bar's LOW actually
    came DOWN to the level (tagged it), CLOSED above it (support defended), AND
    the close is still within prox_pct of the level — so it fires while price is
    AT the entry, not after it bounced away. BUY. Pure over `bars` — never raises."""
    try:
        if bars is None or len(bars) < 10 or level is None or level <= 0:
            return None
        l = float(bars["Low"].iloc[-1])
        c = float(bars["Close"].iloc[-1])
        tagged   = l <= level * (1 + 0.0015)          # the wick reached DOWN to the level
        held     = c > level                          # closed above it → support held
        at_entry = (c - level) / level <= prox_pct    # price still at the level (actionable)
        if not (tagged and held and at_entry):
            return None
        entry = round(level, 2)
        stop = round(level * (1 - stop_off), 2)
        risk = entry - stop
        if risk <= 0:
            return None
        return AlertSignal(
            symbol=symbol, alert_type=alert_type, direction="BUY", price=c,
            entry=entry, stop=stop, target_1=round(entry + 2 * risk, 2),
            target_2=round(entry + 3 * risk, 2), confidence="high",
            message=f"{label} — price defending the {label} as support",
        )
    except Exception:
        return None


def check_avwap_reject(
    symbol: str,
    bars,
    level: "float | None",
    label: str,
    alert_type: "AVWAPAlertType",
    prox_pct: float = 0.006,
    stop_off: float = 0.007,
):
    """DAILY anchored-VWAP REJECTION (SHORT) — check_ma_reject_htf semantics with a
    daily-locked anchored-VWAP line as the level (passed in by the caller from
    compute_daily_avwaps). Fires when the LAST completed hourly bar CLOSED below
    the level, its HIGH came to the level (a touch within prox_pct), and it either
    OPENED below the level (rallied into overhead resistance) or poked above and
    closed back below. Generates for every name; delivery stays index-gated by
    monitor.py (short_not_index) exactly like the other shorts. Pure over `bars`
    — never raises."""
    try:
        if bars is None or len(bars) < 10 or level is None or level <= 0:
            return None
        o = float(bars["Open"].iloc[-1])
        h = float(bars["High"].iloc[-1])
        c = float(bars["Close"].iloc[-1])
        near = abs(h - level) / level <= prox_pct  # the high tagged the level
        rejected = c < level                       # closed back below it
        open_below = o <= level                    # opened under (overhead resistance)
        poked = h > level and c < level            # poked above, closed back below
        if not (rejected and near and (open_below or poked)):
            return None
        entry = round(level, 2)
        stop = round(level * (1 + stop_off), 2)    # stop just above the level
        risk = stop - entry
        if risk <= 0:
            return None
        return AlertSignal(
            symbol=symbol, alert_type=alert_type, direction="SHORT", price=c,
            entry=entry, stop=stop, target_1=round(entry - 2 * risk, 2),
            target_2=round(entry - 3 * risk, 2), confidence="high",
            message=f"{label} — price rejected at the {label} (resistance)",
        )
    except Exception:
        return None
