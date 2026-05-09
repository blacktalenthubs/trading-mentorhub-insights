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
import logging
import os

import requests

logger = logging.getLogger("triage.tg")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CONVICTION_CHAT_ID = os.environ.get("CONVICTION_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


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


def _sector_line(sec):
    if not sec.get("in_sector"):
        return f"  Sector: {_e(sec.get('reason', '—'))}"
    name = _e(sec.get("sector"))
    own_bias = sec.get("own_bias") or "neutral"
    if sec.get("aligned"):
        peers = sec.get("bull_peers" if own_bias == "bull" else "bear_peers") or []
        return f"  Sector ({name}): ALIGNED — {_e(', '.join(peers))}"
    if sec.get("counter_flow"):
        opp = sec.get("bear_peers" if own_bias == "bull" else "bull_peers") or []
        return f"  Sector ({name}): COUNTER-FLOW ⚠ — {_e(', '.join(opp))}"
    lookback = sec.get("lookback_minutes", 15)
    return f"  Sector ({name}): no peers firing in {lookback}min — isolated"


def _index_line(idx):
    if not idx.get("checked"):
        return "  Index: not checked"
    if not idx.get("any_macro_fire"):
        return f"  Index: no SPY/QQQ/XL* alerts in last {idx.get('lookback_minutes', 10)}min"
    if idx.get("aligned_with_index"):
        return f"  Index: ALIGNED — {_e(', '.join(idx['aligned_with_index']))}"
    if idx.get("counter_flow_index"):
        return f"  Index: COUNTER-FLOW ⚠ — {_e(', '.join(idx['counter_flow_index']))}"
    return "  Index: macro alerts present but neutral"


def _cluster_line(result):
    if result.get("proximity_match"):
        return "  Cluster: ⚠ proximity match — same setup recently"
    return "  Cluster: 1st alert in window"


def format_unified(alert, result):
    """Single integrated message — Pine-shape body + agent verdict + context.

    Verdict line is presented FIRST after the alert essentials (per user
    feedback: verdict is the headline, supporting context follows).
    """
    sym       = _e(alert.get("symbol"))
    direction = (alert.get("direction") or "").upper()
    dir_label = ("LONG" if direction in ("BUY", "LONG")
                 else "SHORT" if direction == "SHORT"
                 else direction or "ALERT")
    rule      = _e(alert.get("alert_type") or "tv_alert")
    price     = alert.get("price")

    # ── Header + setup levels ────────────────────────────────────────
    parts = [f"<b>{dir_label} {sym} ${price:.2f}</b> — <i>{rule}</i>"]

    levels = []
    if alert.get("entry") is not None:    levels.append(f"Entry ${alert['entry']:.2f}")
    if alert.get("stop") is not None:     levels.append(f"Stop ${alert['stop']:.2f}")
    if alert.get("target_1") is not None: levels.append(f"T1 ${alert['target_1']:.2f}")
    if alert.get("target_2") is not None: levels.append(f"T2 ${alert['target_2']:.2f}")
    if levels:
        parts.append(" · ".join(levels))

    # Volume line — same wording as existing Pine notifier so it's familiar
    vr = alert.get("volume_ratio")
    if vr is not None:
        if vr < 1.5:
            parts.append(f"⚠️ Low volume on fire bar ({vr:.2f}× avg)")
        elif vr >= 2.0:
            parts.append(f"✅ Strong volume ({vr:.2f}× avg)")
        else:
            parts.append(f"Volume: {vr:.2f}× avg")

    # CVD line
    cvd_div = alert.get("cvd_diverging")
    if cvd_div is not None:
        if cvd_div:
            parts.append("⚠️ CVD diverging — order flow not confirming")
        else:
            parts.append("✅ CVD confirming move")

    # ── Agent block — verdict first, supporting context after ────────
    verdict = (result.get("verdict") or "NORMAL").upper()
    reason  = _e(result.get("reason") or "")
    parts.append("")
    parts.append(f"  {_verdict_emoji(verdict)} <b>Agent Verdict: {verdict}</b> — {reason}")

    parts.append(_sector_line(result.get("sector") or {}))
    parts.append(_index_line(result.get("index") or {}))
    parts.append(_cluster_line(result))

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
    return _send(text, reply_markup=buttons, chat_id=chat_id)


# Backwards-compat shim — older callers may still import this
def send_high(alert, result):
    return send_verdict(alert, result, mode="high_only")
