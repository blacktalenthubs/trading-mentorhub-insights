"""Telegram posting + unified message formatting for the triage agent.

When AGENT_OWNS_TELEGRAM=true on the trade-analytics services, this module
is the SOLE Telegram sender. Output structure:

  LONG SYMBOL $price — alert_type
  Entry · Stop · T1 · T2
  Volume line · CVD line

    [emoji] Agent Verdict: HIGH/NORMAL/MUTE — short reason
    (optional second-line nuance)

    Sector (Group): aligned/counter/isolated — peers
    Index: aligned/counter/no fresh macro
    Cluster: 1st alert in window  /  proximity match ⚠

  [✅ Took It]  [❌ Skip]  [🛑 Exit]   ← inline buttons; same callback_data
                                          as notifier so existing handlers
                                          remain unchanged.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger("triage.tg")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CONVICTION_CHAT_ID = os.environ.get("CONVICTION_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# Chart image rendering (chart-img.com). Optional — when set, HIGH-conviction
# alerts include an inline TradingView-style chart with entry/stop/T1 lines.
# When unset, all alerts fall back to text-only.
CHART_IMG_API_KEY = os.environ.get("CHART_IMG_API_KEY")
CHART_IMG_ENDPOINT = "https://api.chart-img.com/v2/tradingview/advanced-chart"


def _alert_interval(alert_type: str) -> str:
    """Map a Pine alert_type to a chart-img interval enum.
    chart-img valid intervals: 1m, 3m, 5m, 15m, 30m, 45m, 1h, 2h, 3h, 4h, 1D, 1W, 1M.
    """
    if not alert_type:
        return "5m"
    at = alert_type.lower()
    if "_5m" in at or "staged_" in at:
        return "5m"
    if "_15m" in at:
        return "15m"
    if "_1h" in at or "_60m" in at:
        return "1h"
    if "ema21" in at or "ema50" in at:
        return "15m"
    return "5m"


# Symbol → TradingView exchange prefix. Default NASDAQ for unknown US tickers.
# Add to this map as new symbols enter the watchlist.
_EXCHANGE_OVERRIDES = {
    # ETFs — most are AMEX (NYSEARCA), QQQ is NASDAQ
    "SPY": "AMEX", "IWM": "AMEX", "DIA": "AMEX",
    "XLK": "AMEX", "XLE": "AMEX", "XLF": "AMEX", "XLV": "AMEX",
    "XLY": "AMEX", "XLI": "AMEX", "XLB": "AMEX", "XLU": "AMEX",
    "XLP": "AMEX", "XLRE": "AMEX", "XLC": "AMEX",
    # NYSE listings
    "ORCL": "NYSE", "NOW": "NYSE", "TSM": "NYSE",
    "OKLO": "NYSE", "VST": "NYSE",
    "V": "NYSE", "MA": "NYSE", "AXP": "NYSE",
    "IONQ": "NYSE", "RDDT": "NYSE", "SHOP": "NYSE",
    # Crypto (full override — not "EXCHANGE:SYMBOL" pattern)
    "BTC-USD": "COINBASE:BTCUSD",
    "ETH-USD": "COINBASE:ETHUSD",
}


def _tv_symbol(symbol: str) -> str:
    """Convert a watchlist symbol to chart-img's EXCHANGE:SYMBOL format."""
    override = _EXCHANGE_OVERRIDES.get(symbol)
    if override:
        return override if ":" in override else f"{override}:{symbol}"
    return f"NASDAQ:{symbol}"  # default for the bulk of the watchlist


def _hline(price: float, color: str) -> dict:
    """Horizontal line drawing for chart-img v2 advanced-chart.
    Used as fallback when entry/stop/target_1 aren't all present (so we can't
    build a Long/Short Position trade box). chart-img only honors lineColor
    and lineWidth on Horizontal Line — labels aren't supported.
    """
    return {
        "name": "Horizontal Line",
        "input": {"price": float(price)},
        "override": {"lineColor": color, "lineWidth": 2},
    }


def _trade_box(alert: dict) -> Optional[dict]:
    """Build a TradingView Long/Short Position drawing from alert levels.
    Returns None if entry/stop/target_1 aren't all present.

    Renders the trade structure as a colored zone:
      • Long: green target zone above entry, red stop zone below
      • Short: green target zone below entry, red stop zone above
    Each zone shows a price label, and risk/reward is visually proportional.
    """
    entry  = alert.get("entry")
    stop   = alert.get("stop")
    target = alert.get("target_1")
    if entry is None or stop is None or target is None:
        return None
    direction = (alert.get("direction") or "").upper()
    name = "Short Position" if direction == "SHORT" else "Long Position"

    # Box renders forward from startDatetime to the chart's right edge.
    # Anchor 1h before the alert so the box has visible width on the chart.
    anchor_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    return {
        "name": name,
        "input": {
            "startDatetime": anchor_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "entryPrice":  float(entry),
            "targetPrice": float(target),
            "stopPrice":   float(stop),
        },
    }


def fetch_chart_image(alert: dict) -> Optional[bytes]:
    """Fetch a TradingView-style chart PNG from chart-img.com.
    Returns PNG bytes or None on any failure (caller falls back to text).

    Layout (5 of 5 PRO param budget):
      • VWAP (study)             — session-anchored institutional reference.
                                   Resets each session; bias filter for the day.
      • Long/Short Position      — TradingView trade box on the right edge:
                                   green target zone, gray entry, red stop zone,
                                   risk/reward visually proportional.
      • Entry hline (blue)       — extends back through price history so you
      • Stop hline (red)           can see prior reactions / confluence at each
      • Target hline (green)       level. Labels show on the price axis.
      • Falls back to lines only when entry/stop/T1 aren't all present.
    """
    if not CHART_IMG_API_KEY:
        return None
    symbol = alert.get("symbol")
    if not symbol:
        return None

    payload = {
        "symbol": _tv_symbol(symbol),
        "interval": _alert_interval(alert.get("alert_type") or ""),
        "theme": "dark",
        "width": 1920,
        "height": 1080,
        "studies": [{"name": "VWAP"}],
    }

    drawings = []
    box = _trade_box(alert)
    if box:
        drawings.append(box)
    if alert.get("entry") is not None:
        drawings.append(_hline(alert["entry"], "rgb(91,141,239)"))    # blue
    if alert.get("stop") is not None:
        drawings.append(_hline(alert["stop"], "rgb(240,106,106)"))    # red
    if alert.get("target_1") is not None:
        drawings.append(_hline(alert["target_1"], "rgb(61,220,132)")) # green
    if drawings:
        payload["drawings"] = drawings

    try:
        r = requests.post(
            CHART_IMG_ENDPOINT,
            json=payload,
            headers={"x-api-key": CHART_IMG_API_KEY, "Content-Type": "application/json"},
            timeout=15,
        )
        if r.status_code == 200 and r.content:
            return r.content
        logger.warning("chart-img returned %s for %s: %s",
                       r.status_code, symbol, r.text[:300])
        return None
    except Exception:
        logger.exception("chart-img fetch failed for %s", symbol)
        return None


def _send_with_photo(photo_bytes: bytes, caption: str,
                     reply_markup: Optional[dict] = None,
                     chat_id: Optional[str] = None) -> bool:
    """Telegram sendPhoto with optional inline buttons. Returns True on success."""
    if not API_BASE:
        return False
    target = chat_id or CONVICTION_CHAT_ID
    if not target:
        return False
    # Telegram caption limit is 1024 chars
    if len(caption) > 1024:
        caption = caption[:1020] + "…"
    files = {"photo": ("chart.png", photo_bytes, "image/png")}
    data = {
        "chat_id": str(target),
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{API_BASE}/sendPhoto", files=files, data=data, timeout=15)
        if r.status_code != 200:
            logger.warning("sendPhoto non-200: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception:
        logger.exception("sendPhoto failed")
        return False


def _e(s):
    """Escape for HTML parse mode."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# Trade-button callback_data exactly matches alerting/notifier.py:_build_trade_buttons,
# so the existing handler in scripts/telegram_bot.py recognizes them unchanged.
_EXIT_TYPES = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}


def _build_buttons(alert):
    """Replicate alerting/notifier.py:_build_trade_buttons. Same callback_data."""
    alert_id = alert.get("id")
    if alert_id is None:
        return None
    direction = (alert.get("direction") or "").upper()

    if direction in ("BUY", "SHORT"):
        return {"inline_keyboard": [[
            {"text": "✅ Took It", "callback_data": f"ack:{alert_id}"},
            {"text": "❌ Skip",    "callback_data": f"skip:{alert_id}"},
            {"text": "\U0001f6d1 Exit", "callback_data": f"exit:{alert_id}"},
        ]]}

    if direction == "SELL":
        if alert.get("alert_type") in _EXIT_TYPES:
            return {"inline_keyboard": [[
                {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{alert_id}"},
            ]]}
        return {"inline_keyboard": [[
            {"text": "\U0001f4b0 Exited", "callback_data": f"exit:{alert_id}"},
            {"text": "\U0001f4aa Still Holding", "callback_data": f"hold:{alert_id}"},
        ]]}

    return None


def _verdict_emoji(verdict):
    return {"HIGH": "\U0001f525", "NORMAL": "⚪", "MUTE": "\U0001f515"}.get(verdict, "⚪")


def _direction_emoji(direction):
    return {"BUY": "🟢", "LONG": "🟢", "SHORT": "🔴", "SELL": "🟡"}.get(direction, "⚪")


def _fmt_price(p):
    """Format a price with commas; 2 decimals always."""
    if p is None:
        return ""
    return f"${p:,.2f}"


def _pct_diff(a, b):
    """Signed percent change from b → a. Returns None if either side is invalid."""
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100.0


def _fmt_levels_block(alert):
    """Return a <pre> block with entry/stop/T1/T2 aligned in columns,
    each target carrying its % offset from entry and R multiple vs stop.
    """
    entry  = alert.get("entry")
    stop   = alert.get("stop")
    t1     = alert.get("target_1")
    t2     = alert.get("target_2")
    if entry is None:
        return ""

    risk = abs(entry - stop) if stop is not None else None

    def _row(label, price, ref=None, is_target=False):
        if price is None:
            return None
        base = f"{label:<7} {_fmt_price(price):>13}"
        pct  = _pct_diff(price, ref) if ref is not None else None
        if pct is None:
            return base
        arrow = "↑" if pct >= 0 else "↓"
        pct_s = f"{arrow}{abs(pct):.2f}%"
        if is_target and risk and risk > 0:
            r_mult = abs(price - entry) / risk
            return f"{base}   {pct_s:>7}  {r_mult:>4.1f}R"
        return f"{base}   {pct_s:>7}"

    rows = [
        _row("Entry", entry),
        _row("Stop",  stop,  entry, is_target=False),
        _row("T1",    t1,    entry, is_target=True),
        _row("T2",    t2,    entry, is_target=True),
    ]
    rows = [r for r in rows if r]
    return "<pre>" + "\n".join(rows) + "</pre>"


def _fmt_vitals_block(alert):
    """Return a <pre> block with Vol + CVD lines, status flags aligned right."""
    lines = []
    vr = alert.get("volume_ratio")
    if vr is not None:
        if vr < 1.5:
            lines.append(f"Vol     {vr:.2f}× ⚠️ low")
        elif vr >= 2.0:
            lines.append(f"Vol     {vr:.2f}× ✅")
        else:
            lines.append(f"Vol     {vr:.2f}×")
    cvd_div = alert.get("cvd_diverging")
    if cvd_div is True:
        lines.append("CVD     diverging ⚠️")
    elif cvd_div is False:
        lines.append("CVD     confirming ✅")
    if not lines:
        return ""
    return "<pre>" + "\n".join(lines) + "</pre>"


def _fmt_context_block(result):
    """Return a <pre> block for sector / index / cluster — three aligned rows."""
    rows = []

    sec = result.get("sector") or {}
    if not sec.get("in_sector"):
        rows.append(("Sector",  sec.get("reason") or "—"))
    else:
        name = sec.get("sector") or "peers"
        own_bias = sec.get("own_bias") or "neutral"
        if sec.get("aligned"):
            peers = sec.get("bull_peers" if own_bias == "bull" else "bear_peers") or []
            rows.append(("Sector", f"{', '.join(peers)} aligned" if peers else f"{name} aligned"))
        elif sec.get("counter_flow"):
            opp = sec.get("bear_peers" if own_bias == "bull" else "bull_peers") or []
            rows.append(("Sector", f"⚠ counter-flow: {', '.join(opp)}" if opp else f"⚠ counter-flow ({name})"))
        else:
            lookback = sec.get("lookback_minutes", 15)
            rows.append(("Sector", f"{name} peers quiet ({lookback}m)"))

    idx = result.get("index") or {}
    if not idx.get("checked"):
        rows.append(("Index", "not checked"))
    elif not idx.get("any_macro_fire"):
        rows.append(("Index", "no macro"))
    elif idx.get("aligned_with_index"):
        rows.append(("Index", f"{', '.join(idx['aligned_with_index'])} aligned"))
    elif idx.get("counter_flow_index"):
        rows.append(("Index", f"⚠ counter-flow: {', '.join(idx['counter_flow_index'])}"))
    else:
        rows.append(("Index", "neutral"))

    if result.get("proximity_match"):
        rows.append(("Cluster", "⚠ proximity match"))
    else:
        rows.append(("Cluster", "fresh"))

    if not rows:
        return ""
    return "<pre>" + "\n".join(f"{label:<9}{_e(val)}" for label, val in rows) + "</pre>"


# Specific rule → human label mapping. Used for the bold reason line
# at the top of each Telegram message. Mirrors prettyReason() in the
# EOD Report page so UI and Telegram show the same wording.
_REASON_EXACT = {
    "staged_pdh_break":           "PDH break",
    "staged_pdl_reclaim":         "PDL reclaim",
    "staged_pdh_rejection":       "PDH rejection",
    "staged_pdh_failed_short":    "PDH failed (trap short)",
    "staged_pdl_break":           "PDL break",
    "pivot_aligned_break_long":   "1h/4h pivot break ↑",
    "pivot_aligned_break_short":  "1h/4h pivot break ↓",
    "pivot_aligned_reclaim_long": "1h/4h pivot reclaim ↑",
    "pivot_aligned_reject_short": "1h/4h pivot reject ↓",
    "vwap_reclaim_long":          "VWAP reclaim ↑",
    "vwap_reject_short":          "VWAP reject ↓",
    "vwap_support_hold":          "VWAP support hold ✓",
    "open_lost":                  "Lost the open ↓",
    "open_reclaimed":             "Reclaimed the open ↑",
}

def _pretty_reason(alert_type: str) -> str:
    """Convert raw alert_type tag into a readable label for the Telegram
    header. Handles MA bounce / rejection / proximity with EMA or SMA
    level extraction; falls back to a sanitized form for unknown tags.
    """
    if not alert_type:
        return "Alert"
    t = alert_type[3:] if alert_type.startswith("tv_") else alert_type

    # MA bounce — possible single or stacked (ema8_ema21).
    m = re.match(r"^ma_bounce_long_v3_(ema|sma)(\d+)_(ema|sma)(\d+)$", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2)} + {m.group(3).upper()} {m.group(4)} bounce"
    m = re.match(r"^ma_bounce_long_v3_(ema|sma)(\d+)$", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2)} bounce"

    # MA rejection (SHORT)
    m = re.match(r"^ma_rejection_short_v3_(ema|sma)(\d+)$", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2)} rejection"

    # Proximity NOTICEs (still rendered cleanly even though they're muted)
    m = re.match(r"^ma_proximity_long_v3_(ema|sma)(\d+)$", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2)} proximity ↑"
    m = re.match(r"^ma_proximity_short_v3_(ema|sma)(\d+)$", t)
    if m:
        return f"{m.group(1).upper()} {m.group(2)} proximity ↓"

    if t in _REASON_EXACT:
        return _REASON_EXACT[t]

    # Fallback: replace underscores with spaces, leave as-is otherwise
    return t.replace("_", " ")


def format_unified(alert, result):
    """Single integrated Telegram message.

    Layout — scannable top-to-bottom:
      🟢 LONG · SYMBOL · $price
      Reason (bold) · interval

      <pre>  Entry / Stop / T1 / T2 grid with % and R multiples  </pre>
      <pre>  Vol / CVD status lines                              </pre>

      ⚪ VERDICT
      reason (only if present)

      <pre>  Sector / Index / Cluster context                    </pre>
    """
    sym       = _e(alert.get("symbol"))
    direction = (alert.get("direction") or "").upper()
    dir_label = ("LONG" if direction in ("BUY", "LONG")
                 else "SHORT" if direction == "SHORT"
                 else direction or "ALERT")
    dir_emoji = _direction_emoji(direction)
    reason    = _e(_pretty_reason(alert.get("alert_type") or ""))
    price     = alert.get("price")
    interval  = _e(alert.get("interval") or "")

    parts = []

    # ── Header ───────────────────────────────────────────────────────
    # Reason goes FIRST in CAPS so it commands the eye — that's the
    # "what kind of setup is this" answer the trader scans for. Symbol /
    # direction / price come on the second line as supporting metadata.
    reason_line = f"🎯 <b>{reason.upper()}</b>" + (f"  ·  {interval}" if interval else "")
    parts.append(reason_line)
    header = f"{dir_emoji} <b>{dir_label} · {sym} · {_fmt_price(price)}</b>"
    parts.append(header)
    parts.append("")

    # ── Levels grid ──────────────────────────────────────────────────
    levels_block = _fmt_levels_block(alert)
    if levels_block:
        parts.append(levels_block)

    # ── Vitals (vol + CVD) ───────────────────────────────────────────
    vitals_block = _fmt_vitals_block(alert)
    if vitals_block:
        parts.append(vitals_block)

    # ── Verdict + reason ─────────────────────────────────────────────
    verdict = (result.get("verdict") or "NORMAL").upper()
    reason  = (result.get("reason") or "").strip()
    parts.append("")
    parts.append(f"{_verdict_emoji(verdict)} <b>{verdict}</b>")
    if reason:
        parts.append(_e(reason))

    # ── Context (sector / index / cluster) ───────────────────────────
    context_block = _fmt_context_block(result)
    if context_block:
        parts.append(context_block)

    return "\n".join(parts)[:4000]


def format_mute_audit(alert, result):
    """Single-line audit format for log lines (not Telegram)."""
    return (f"[MUTE] #{alert.get('id')} {alert.get('symbol')} "
            f"{alert.get('alert_type')} {alert.get('direction')} "
            f"${alert.get('price')} → {result.get('reason')}")


def _send(text, reply_markup=None, chat_id=None):
    """Low-level Telegram send. Returns True on success, never raises."""
    if not API_BASE:
        logger.warning("telegram bot token not configured — skipping send")
        return False
    target = chat_id or CONVICTION_CHAT_ID
    if not target:
        logger.warning("telegram chat_id not configured — skipping send")
        return False
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(f"{API_BASE}/sendMessage", json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("telegram send non-200: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception:
        logger.exception("telegram send failed")
        return False


def send_verdict(alert, result, mode="all", chat_id=None):
    """Post the agent's verdict to Telegram, respecting the post mode.

    Modes:
      'all'        — post HIGH + NORMAL + MUTE (validation phase, default)
      'high_mute'  — post HIGH + MUTE (skip NORMAL chatter)
      'high_only'  — post HIGH only (steady state, post-trust)

    Returns:
      True  — sent successfully
      None  — skipped per post_mode (not an error)
      False — send failed
    """
    verdict = (result.get("verdict") or "").upper()

    if mode == "high_only" and verdict != "HIGH":
        return None
    if mode == "high_mute" and verdict == "NORMAL":
        return None

    text = format_unified(alert, result)
    buttons = _build_buttons(alert)

    # HIGH-conviction alerts: try to attach a TV-style chart.
    # Falls through to text-only if chart fetch fails or API key missing.
    if verdict == "HIGH" and CHART_IMG_API_KEY:
        chart = fetch_chart_image(alert)
        if chart:
            ok = _send_with_photo(chart, text, reply_markup=buttons, chat_id=chat_id)
            if ok:
                return True
            logger.warning("photo send failed; falling back to text for #%s",
                           alert.get("id"))

    return _send(text, reply_markup=buttons, chat_id=chat_id)


# Backwards-compat shim — older callers may still import this
def send_high(alert, result):
    return send_verdict(alert, result, mode="high_only")
