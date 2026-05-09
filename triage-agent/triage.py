"""
Alert Triage Agent — v0.1
─────────────────────────
Reads alerts from the trade-analytics Postgres DB, runs each through
a Claude-based triage agent, and decides HIGH / NORMAL / MUTE.

This is a learning project. It is read-only against the alerts table
and does NOT modify or call into any of the protected business-logic
files in trade-analytics/.

Usage:
  pip install -r requirements.txt
  cp .env.example .env       # fill in ANTHROPIC_API_KEY (DATABASE_URL provided)
  python triage.py --dry-run --since 2026-05-08
  python triage.py --dry-run --last 10

Modes (v0.1):
  --dry-run --since YYYY-MM-DD   triage all alerts from that session_date
  --dry-run --last N             triage the last N alerts in the table

Live mode (post to a separate Telegram channel) is NOT YET IMPLEMENTED.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from anthropic import Anthropic

load_dotenv()

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL      = os.environ.get("DATABASE_URL")
MODEL             = os.environ.get("TRIAGE_MODEL", "claude-haiku-4-5")
MAX_STEPS         = 4

if not ANTHROPIC_API_KEY:
    sys.exit("ANTHROPIC_API_KEY is required. Set it in .env or the environment.")
if not DATABASE_URL:
    sys.exit("DATABASE_URL is required. Set it in .env or the environment.")

client = Anthropic(api_key=ANTHROPIC_API_KEY)


# ──────────────────────────────────────────────────────────────
# TOOLS — what the agent can call
# ──────────────────────────────────────────────────────────────
# Each tool is API-shaped (Chapter 2 of the agentic-ai domain):
#   tight schema, helpful description, narrow scope.
#
# The agent has THREE tools:
#   1. get_recent_alerts  — read recent alerts for a symbol (context)
#   2. get_market_session — equity session right now (premarket / regular / etc.)
#   3. decide             — the agent's final answer (also the stop signal)

TOOLS = [
    {
        "name": "get_recent_alerts",
        "description": (
            "Fetch alerts that fired for a given symbol in the recent past. "
            "Use this to detect duplicates (same alert_type recently fired), "
            "confluence (different alert_types aligning), or noise (many alerts "
            "on the same symbol). Returns a list of "
            "{alert_type, direction, price, score, fired_minutes_ago}. "
            "The current alert is excluded from results so you only see PRIOR alerts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol, e.g. 'SPY' or 'ETH-USD'"
                },
                "lookback_minutes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1440,
                    "default": 60,
                    "description": "How far back to look (default 60, max 1440)"
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_session",
        "description": (
            "Returns the current US equity market session for the given symbol: "
            "'premarket' (4:00-9:30 ET), 'regular' (9:30-16:00 ET), "
            "'afterhours' (16:00-20:00 ET), or 'closed'. "
            "For crypto symbols (e.g. ETH-USD, BTC-USD), returns 'crypto-always-on'. "
            "Useful when deciding whether equity alerts should be muted outside "
            "regular hours."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "decide",
        "description": (
            "Final verdict for this alert. This is the STOP SIGNAL — once you call "
            "this, the loop ends. Use exactly one of: "
            "'HIGH' (high-conviction setup, push prominently), "
            "'NORMAL' (standard alert, push as usual), "
            "'MUTE' (noise — duplicate, spam, off-hours, etc., suppress). "
            "The 'reason' field is shown to the trader on Telegram, so make it "
            "useful — one terse sentence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["HIGH", "NORMAL", "MUTE"]},
                "reason":  {"type": "string"},
            },
            "required": ["verdict", "reason"],
        },
    },
]


# ──────────────────────────────────────────────────────────────
# TOOL EXECUTORS
# ──────────────────────────────────────────────────────────────

def execute_get_recent_alerts(symbol, lookback_minutes=60, *, exclude_id=None,
                              relative_to=None, user_id=None):
    """
    Returns alerts for `symbol` within the last `lookback_minutes`.
    Filters by user_id so we don't count cross-user duplicates as spam.
    relative_to: a datetime to use as "now" (for backtesting historical alerts).
                 If None, uses the current time.
    """
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if relative_to is not None:
                # Historical: count back from the alert's actual fire time.
                # Use (created_at, id) row comparison so ties on timestamp
                # are broken by id — important because many alerts share the
                # same created_at down to the microsecond (batch inserts).
                pivot_id = exclude_id if exclude_id is not None else 2**31
                cur.execute("""
                    SELECT id, alert_type, direction, price, volume_ratio,
                           cvd_diverging, confidence, created_at
                    FROM alerts
                    WHERE symbol = %s
                      AND (created_at, id) < (%s, %s)
                      AND created_at >= %s - (INTERVAL '1 minute' * %s)
                      AND (%s::int IS NULL OR user_id = %s)
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                """, (symbol, relative_to, pivot_id,
                      relative_to, lookback_minutes,
                      user_id, user_id))
            else:
                cur.execute("""
                    SELECT id, alert_type, direction, price, volume_ratio,
                           cvd_diverging, confidence, created_at
                    FROM alerts
                    WHERE symbol = %s
                      AND created_at >= NOW() - (INTERVAL '1 minute' * %s)
                      AND (%s::int IS NULL OR id != %s::int)
                      AND (%s::int IS NULL OR user_id = %s)
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (symbol, lookback_minutes,
                      exclude_id, exclude_id,
                      user_id, user_id))

            rows = cur.fetchall()

    out = []
    pivot = relative_to or datetime.now(timezone.utc)
    if pivot.tzinfo is None:
        pivot = pivot.replace(tzinfo=timezone.utc)

    for r in rows:
        ts = r["created_at"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        mins_ago = round((pivot - ts).total_seconds() / 60, 1)
        out.append({
            "alert_type":   r["alert_type"],
            "direction":    r["direction"],
            "price":        float(r["price"]) if r["price"] is not None else None,
            "volume_ratio": float(r["volume_ratio"]) if r["volume_ratio"] is not None else None,
            "cvd_diverging": bool(r["cvd_diverging"]) if r["cvd_diverging"] is not None else None,
            "confidence":   r["confidence"],
            "fired_minutes_ago": mins_ago,
        })

    return {
        "symbol": symbol,
        "lookback_minutes": lookback_minutes,
        "count": len(out),
        "alerts": out,
    }


def execute_get_market_session(symbol, *, at_timestamp=None):
    """
    Returns the market session for `symbol` at `at_timestamp` (UTC).
    If at_timestamp is None, uses the current time.
    For backtesting historical alerts, the runtime auto-injects the alert's
    created_at — the LLM never has to think about it.
    """
    s = symbol.upper()
    if s.endswith("-USD") or s in {"BTC", "ETH", "SOL", "DOGE"}:
        return {"symbol": symbol, "session": "crypto-always-on",
                "evaluated_at_utc": (at_timestamp or datetime.now(timezone.utc)).isoformat()}

    pivot = at_timestamp or datetime.now(timezone.utc)
    if pivot.tzinfo is None:
        pivot = pivot.replace(tzinfo=timezone.utc)

    # Quick US/Eastern approximation. Doesn't handle DST cutover precisely
    # but good enough for triage. May = EDT = UTC-4.
    et_hour = (pivot.hour - 4) % 24
    et_dow  = pivot.weekday()  # 0=Mon

    if et_dow >= 5:
        session = "closed"
    elif 4 <= et_hour < 9 or (et_hour == 9 and pivot.minute < 30):
        session = "premarket"
    elif (et_hour == 9 and pivot.minute >= 30) or (10 <= et_hour < 16):
        session = "regular"
    elif 16 <= et_hour < 20:
        session = "afterhours"
    else:
        session = "closed"

    return {"symbol": symbol, "session": session,
            "evaluated_at_utc": pivot.isoformat()}


# ──────────────────────────────────────────────────────────────
# THE AGENT LOOP — the heart of it
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an alert triage agent for a stock-market trader.
Your job: classify each incoming alert as HIGH, NORMAL, or MUTE.

Trader's principles (do not violate):
  1. NEVER suppress real valuable alerts. When in doubt, NORMAL.
  2. Low volume is NOT a mute reason — institutions often build positions
     quietly at support before a spike. A fresh signal at low volume can
     be the most valuable signal of the day.
  3. Same alert_type at a NEW PRICE LEVEL is a NEW SETUP, not a duplicate.

Pine signal fields you'll see for each alert:
- volume_ratio: relative volume vs average. Use it to ELEVATE to HIGH;
  never use it to MUTE.
- cvd_diverging: 1 = cumulative volume delta diverging from price
  (institutional flow flag — never suppress when this is on).
- confidence: Pine's own confidence (low / medium / high).
- entry, stop, target_1: setup levels.

You will also see a PROXIMITY DEDUP block at the top of each alert. This
field is pre-computed by the runtime — trust it.

────────────────────────────────────────────────────────────────────
RULES — apply in priority order:
────────────────────────────────────────────────────────────────────

NEVER MUTE if any of:
  • cvd_diverging=true on the current alert
  • confidence=high
  • This is the first alert of (symbol, alert_type) in the last 60 min
  • PROXIMITY DEDUP block says "no match"

HIGH (push prominently) if any of:
  • 2+ DIFFERENT alert types fired on this symbol in the last 15 minutes
    — a flip (rejection → break at similar price) counts as confluence
  • volume_ratio >= 3.0 AND not a proximity match
  • cvd_diverging AND first-of-type today
  • Sector ALIGNED (peers in same sector firing same bias) — this is your
    most important new signal. A symbol breaking with sector tailwind is
    high-conviction; isolated breaks are not.
  • Index ALIGNED — SPY/QQQ/XLK/XLE/XLF/XLV/IWM/DIA fired bias-matching
    alerts in the last 10min. Macro tailwind raises conviction.

MUTE (suppress) ONLY if ALL of these are true:
  • PROXIMITY DEDUP block says "match"
  • cvd_diverging is false on the current alert
  • confidence is not "high"
  • Sector is NOT aligned (no peer support)
  • Index is NOT aligned

NORMAL — the default. Use this when the rules above don't push you to HIGH
or MUTE. Counter-flow vs sector or index is a CAUTION but not a MUTE — the
trader still wants to see it; flag it in your reason.

────────────────────────────────────────────────────────────────────

Market session is INFORMATIONAL ONLY. Do NOT mute on session alone.

How to use tools:
- ALWAYS call get_recent_alerts(symbol, lookback_minutes=60) FIRST. Use this
  to detect cross-type confluence (different alert_type within 15min).
- Call get_market_session(symbol) only if you want session context.
- Then call decide() exactly once.

Be terse but specific in the reason field — cite the proximity delta, prior
fire timing, volume_ratio, or confluence partner when relevant. The reason
shows up on the trader's Telegram.

Bias: the cost of one missed signal is much higher than one extra push.
The deterministic safety net will catch obvious duplicates the rules above
are designed to mute — your job is to recognize the cases that need to go
through DESPITE a proximity match (cvd_diverging, confluence, first-of-day).
"""


# ──────────────────────────────────────────────────────────────
# PROXIMITY DEDUP — derived from the IONQ + SNOW lessons
# ──────────────────────────────────────────────────────────────
#
# The rule: MUTE the new alert only if all of the following are true:
#   A) Same (symbol, alert_type, direction, user_id) fired in last 6 hours
#   B) Current price is within 1.5% of the prior fire's price
#   C) Current alert does NOT have cvd_diverging=true
#   D) Agent didn't find a confluence override (different alert_type within 15min)
#
# Rationale:
#   - Identity-only dedup (current 60-min window) misses same-level chop
#     after the window expires (AAPL fired 3× yesterday at the same level).
#   - Time-only dedup (e.g., once-per-day) suppresses real new setups at
#     a different level (IONQ fired at $46.32, $46.41, then $49.25 — the
#     third was a real new breakout, not a repeat).
#   - Volume-based dedup is wrong — low volume at support is exactly when
#     the alert SHOULD fire (the calm before the spike).
#
# Conjunction matters: ALL of A+B+C+D must be true to MUTE. If any one is
# false, the alert fires.

PROXIMITY_WINDOW_HOURS = 6
PROXIMITY_PCT_THRESHOLD = 1.5  # percent

# ── Sector + Index enrichment knobs ─────────────────────────────────
SECTOR_LOOKBACK_MINUTES = 15        # peers in same sector firing recently
INDEX_LOOKBACK_MINUTES  = 10        # SPY/QQQ/XLK alerts in same window
INDEX_GROUP_NAME = "Macro"          # group containing SPY/QQQ/XLK/etc.

# alert_type → bias mapping (how each alert "votes" bullish/bearish)
def alert_bias(alert_type, direction):
    """Returns 'bull', 'bear', or 'neutral' based on alert_type + direction."""
    at = (alert_type or "").lower()
    d  = (direction or "").upper()
    if d == "BUY":  return "bull"
    if d == "SHORT": return "bear"
    if "rejection" in at or "failed" in at:
        return "bear" if d != "BUY" else "neutral"
    if "break" in at or "reclaim" in at or "bounce" in at:
        return "bull" if d != "SHORT" else "neutral"
    return "neutral"


def compute_proximity_match(alert, user_id):
    """Returns the prior matching fire (if any) plus the proximity verdict.

    A 'match' means: same (symbol, alert_type, direction) for this user_id
    fired within PROXIMITY_WINDOW_HOURS, and current price is within
    PROXIMITY_PCT_THRESHOLD of that prior fire's price.
    """
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, price, cvd_diverging, created_at
                FROM alerts
                WHERE symbol = %s AND alert_type = %s AND direction = %s
                  AND (created_at, id) < (%s, %s)
                  AND created_at >= %s - (INTERVAL '1 hour' * %s)
                  AND (%s::int IS NULL OR user_id = %s)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            """, (alert['symbol'], alert['alert_type'], alert['direction'],
                  alert['created_at'], alert['id'],
                  alert['created_at'], PROXIMITY_WINDOW_HOURS,
                  user_id, user_id))
            prior = cur.fetchone()

    if prior is None:
        return {"match": False, "reason": "no prior same-identity fire in window"}

    cur_px   = float(alert['price'])
    prior_px = float(prior['price'])
    pct = abs(cur_px - prior_px) / prior_px * 100.0
    minutes_ago = (alert['created_at'] - prior['created_at']).total_seconds() / 60.0

    if pct > PROXIMITY_PCT_THRESHOLD:
        return {"match": False,
                "reason": f"price moved {pct:.2f}% from prior fire — different setup",
                "prior": {"id": prior['id'], "price": prior_px,
                          "minutes_ago": round(minutes_ago, 1),
                          "pct_delta": round(pct, 2)}}

    return {
        "match": True,
        "reason": f"identity match: same setup at {pct:.2f}% from prior fire ({minutes_ago:.0f}min ago)",
        "prior": {
            "id": prior['id'],
            "price": prior_px,
            "minutes_ago": round(minutes_ago, 1),
            "pct_delta": round(pct, 2),
            "cvd_diverging": bool(prior['cvd_diverging']) if prior['cvd_diverging'] is not None else False,
        },
    }


def compute_sector_confluence(alert, user_id):
    """Return what other symbols in the alert's sector fired recently.

    Uses the user's watchlist_group to find the sector. If the symbol is
    ungrouped, returns an empty result (the agent will see "no sector").
    """
    if user_id is None:
        return {"in_sector": False, "reason": "no user_id passed"}

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Find the symbol's sector (group_id + name)
            cur.execute("""
                SELECT g.id, g.name
                FROM watchlist w
                LEFT JOIN watchlist_group g ON g.id = w.group_id
                WHERE w.user_id = %s AND w.symbol = %s
                LIMIT 1
            """, (user_id, alert['symbol']))
            row = cur.fetchone()

            if not row or not row['id']:
                return {"in_sector": False,
                        "reason": f"{alert['symbol']} not in any sector group"}

            group_id   = row['id']
            group_name = row['name']

            # 2. List peers in the same sector (excluding this symbol)
            cur.execute("""
                SELECT symbol FROM watchlist
                WHERE user_id = %s AND group_id = %s AND symbol != %s
            """, (user_id, group_id, alert['symbol']))
            peers = [r['symbol'] for r in cur.fetchall()]

            if not peers:
                return {"in_sector": True, "sector": group_name,
                        "peers": [], "reason": f"sector '{group_name}' has only this symbol"}

            # 3. Find peer alerts in the lookback window before this alert
            cur.execute("""
                SELECT symbol, alert_type, direction, created_at
                FROM alerts
                WHERE user_id = %s AND symbol = ANY(%s)
                  AND created_at < %s
                  AND created_at >= %s - (INTERVAL '1 minute' * %s)
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id, peers, alert['created_at'],
                  alert['created_at'], SECTOR_LOOKBACK_MINUTES))
            peer_alerts = cur.fetchall()

    own_bias = alert_bias(alert['alert_type'], alert['direction'])

    bull_peers, bear_peers = [], []
    for pa in peer_alerts:
        b = alert_bias(pa['alert_type'], pa['direction'])
        mins = (alert['created_at'] - pa['created_at']).total_seconds() / 60.0
        entry = f"{pa['symbol']} ({pa['alert_type']}, {round(mins,0):.0f}m ago)"
        if b == "bull": bull_peers.append(entry)
        elif b == "bear": bear_peers.append(entry)

    aligned = (own_bias == "bull" and bull_peers) or (own_bias == "bear" and bear_peers)
    counter = (own_bias == "bull" and bear_peers) or (own_bias == "bear" and bull_peers)

    return {
        "in_sector": True,
        "sector": group_name,
        "own_bias": own_bias,
        "peers_count": len(peers),
        "bull_peers": bull_peers,
        "bear_peers": bear_peers,
        "aligned": bool(aligned),
        "counter_flow": bool(counter),
        "lookback_minutes": SECTOR_LOOKBACK_MINUTES,
    }


def compute_index_alignment(alert, user_id):
    """Check what the index/macro group did in a tighter window before this alert."""
    if user_id is None:
        return {"checked": False, "reason": "no user_id"}

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.symbol, a.alert_type, a.direction, a.created_at
                FROM alerts a
                JOIN watchlist w
                  ON w.user_id = a.user_id AND w.symbol = a.symbol
                JOIN watchlist_group g ON g.id = w.group_id
                WHERE a.user_id = %s AND g.name = %s
                  AND a.created_at < %s
                  AND a.created_at >= %s - (INTERVAL '1 minute' * %s)
                ORDER BY a.created_at DESC
                LIMIT 10
            """, (user_id, INDEX_GROUP_NAME, alert['created_at'],
                  alert['created_at'], INDEX_LOOKBACK_MINUTES))
            macro = cur.fetchall()

    own_bias = alert_bias(alert['alert_type'], alert['direction'])
    aligned, counter, neutral = [], [], []
    for m in macro:
        mb = alert_bias(m['alert_type'], m['direction'])
        mins = (alert['created_at'] - m['created_at']).total_seconds() / 60.0
        entry = f"{m['symbol']} {m['alert_type']} ({round(mins,0):.0f}m ago)"
        if mb == own_bias and own_bias != "neutral":
            aligned.append(entry)
        elif mb != own_bias and mb != "neutral" and own_bias != "neutral":
            counter.append(entry)
        else:
            neutral.append(entry)

    return {
        "checked": True,
        "own_bias": own_bias,
        "aligned_with_index": aligned,
        "counter_flow_index": counter,
        "lookback_minutes": INDEX_LOOKBACK_MINUTES,
        "any_macro_fire": bool(macro),
    }


def fetch_prior_summary(alert, user_id, lookback_minutes=60):
    """Used by the safety net — counts how many same-type alerts fired before this one."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) AS n FROM alerts
                WHERE symbol = %s AND alert_type = %s
                  AND (created_at, id) < (%s, %s)
                  AND created_at >= %s - (INTERVAL '1 minute' * %s)
                  AND (%s::int IS NULL OR user_id = %s)
            """, (alert['symbol'], alert['alert_type'],
                  alert['created_at'], alert['id'],
                  alert['created_at'], lookback_minutes,
                  user_id, user_id))
            n = cur.fetchone()['n']
    return {"same_type_in_window": n}


def safety_override(alert, agent_verdict, reason, prior_alerts_summary, proximity):
    """
    Post-decision safety net. Two jobs:
      1. Force MUTE if the proximity rule is satisfied AND no override signal
         on the current alert. This is the deterministic backstop.
      2. Force NORMAL if the agent tried to mute but the alert has a
         never-suppress signal (cvd_diverging, first-of-type).

    Order: the proximity rule is a STRONG signal of duplication, so it
    can downgrade NORMAL→MUTE. But cvd_diverging on the current alert
    or first-of-type override the proximity rule (we never mute those).
    """
    overrides_to_normal = []
    if alert.get("cvd_diverging"):
        overrides_to_normal.append("cvd_diverging=true on current alert")
    if (alert.get("confidence") or "").lower() == "high":
        overrides_to_normal.append("confidence=high")
    # First-of-type override only applies when proximity DIDN'T match.
    # If proximity matched, by definition there IS a prior — so first-of-type
    # would conflict. Trust the proximity verdict in that case.
    if not proximity["match"] and prior_alerts_summary["same_type_in_window"] == 0:
        overrides_to_normal.append(f"first {alert['alert_type']} on {alert['symbol']} in window")

    # ── Path 1: agent said MUTE, but a never-suppress signal is present
    if agent_verdict == "MUTE" and overrides_to_normal:
        new_reason = (f"[safety-upgraded MUTE→NORMAL: {', '.join(overrides_to_normal)}] "
                      f"agent said: {reason}")
        return "NORMAL", new_reason, {"upgraded_to_normal": overrides_to_normal}

    # ── Path 2: proximity rule should force MUTE
    # Only applies when agent said NORMAL or HIGH but the data screams "duplicate"
    if proximity["match"] and not overrides_to_normal and agent_verdict != "MUTE":
        prior = proximity["prior"]
        new_reason = (f"[deterministic-MUTE: proximity rule] "
                      f"same {alert['alert_type']} {alert['direction']} fired "
                      f"{prior['minutes_ago']:.0f}min ago at ${prior['price']:.2f} "
                      f"({prior['pct_delta']:.2f}% away). agent said: {reason}")
        return "MUTE", new_reason, {"forced_to_mute": [proximity["reason"]]}

    return agent_verdict, reason, None


def triage(alert, user_id=None):
    """Run the agent loop on one alert. Returns {verdict, reason, steps_used,
    safety_overrides (or None), agent_verdict (pre-safety), proximity,
    sector, index}.
    """
    proximity = compute_proximity_match(alert, user_id)
    sector    = compute_sector_confluence(alert, user_id)
    index     = compute_index_alignment(alert, user_id)

    if proximity["match"]:
        prior = proximity["prior"]
        proximity_block = (
            f"  PROXIMITY DEDUP MATCH: prior identical alert fired "
            f"{prior['minutes_ago']:.0f}min ago at ${prior['price']:.2f} "
            f"(this alert is {prior['pct_delta']:.2f}% from that price).\n"
            f"  Rule: MUTE this unless a never-suppress signal is present "
            f"(cvd_diverging, confidence=high, first-of-type today).\n"
        )
    else:
        proximity_block = f"  proximity_dedup: no match — {proximity['reason']}\n"

    if not sector.get("in_sector"):
        sector_block = f"  sector: {sector['reason']}\n"
    elif not sector.get("bull_peers") and not sector.get("bear_peers"):
        sector_block = (f"  sector: {sector['sector']} ({sector['peers_count']} peers in group); "
                        f"NO peer alerts in last {sector['lookback_minutes']}min — isolated\n")
    else:
        bp = ", ".join(sector["bull_peers"]) or "none"
        bep = ", ".join(sector["bear_peers"]) or "none"
        align_tag = ("ALIGNED" if sector["aligned"]
                     else "COUNTER-FLOW" if sector["counter_flow"]
                     else "MIXED")
        sector_block = (f"  sector: {sector['sector']} ({align_tag}, "
                        f"own_bias={sector['own_bias']})\n"
                        f"    bull peers: {bp}\n"
                        f"    bear peers: {bep}\n")

    if not index.get("checked"):
        index_block = "  index: not checked\n"
    elif not index.get("any_macro_fire"):
        index_block = (f"  index: no SPY/QQQ/XL* alerts in last "
                       f"{index['lookback_minutes']}min — no fresh macro context\n")
    else:
        a = ", ".join(index["aligned_with_index"]) or "none"
        c = ", ".join(index["counter_flow_index"]) or "none"
        index_block = (f"  index: own_bias={index['own_bias']}\n"
                       f"    aligned: {a}\n"
                       f"    counter: {c}\n")

    user_msg = (
        f"New alert fired:\n"
        f"  id:            {alert['id']}\n"
        f"  symbol:        {alert['symbol']}\n"
        f"  alert_type:    {alert['alert_type']}\n"
        f"  direction:     {alert['direction']}\n"
        f"  price:         {alert['price']}\n"
        f"  volume_ratio:  {alert.get('volume_ratio')}\n"
        f"  cvd_diverging: {bool(alert.get('cvd_diverging'))}\n"
        f"  confidence:    {alert.get('confidence')}\n"
        f"  entry/stop/t1: {alert.get('entry')} / {alert.get('stop')} / {alert.get('target_1')}\n"
        f"  fired_at:      {alert['created_at']}\n"
        f"  user_id:       {user_id if user_id is not None else 'all'}\n"
        f"{proximity_block}"
        f"{sector_block}"
        f"{index_block}"
        f"\nClassify this alert. In your reason field, weight the sector "
        f"and index context — confluence is bullish, counter-flow is a caution."
    )

    messages = [{"role": "user", "content": user_msg}]
    relative_to = alert["created_at"]

    for step in range(MAX_STEPS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append the assistant turn to the conversation
        messages.append({"role": "assistant", "content": resp.content})

        # Find any tool calls in the response
        tool_calls = [b for b in resp.content if b.type == "tool_use"]

        if not tool_calls:
            # Agent stopped without calling decide() — safe fallback to NORMAL
            return {
                "verdict": "NORMAL",
                "reason":  "agent did not classify; fallback to NORMAL (safe default)",
                "agent_verdict": "FALLBACK",
                "safety_overrides": None,
                "steps_used": step + 1,
            }

        # Execute each tool call, build up tool_result blocks
        tool_results = []
        for tc in tool_calls:
            if tc.name == "get_recent_alerts":
                result = execute_get_recent_alerts(
                    **tc.input,
                    exclude_id=alert["id"],
                    relative_to=relative_to,
                    user_id=user_id,
                )
            elif tc.name == "get_market_session":
                result = execute_get_market_session(
                    **tc.input,
                    at_timestamp=relative_to,   # auto-inject alert's fire time
                )
            elif tc.name == "decide":
                # STOP signal — agent has decided. Run safety net before returning.
                agent_v = tc.input.get("verdict", "NORMAL")
                agent_r = tc.input.get("reason", "(no reason provided)")
                prior   = fetch_prior_summary(alert, user_id)
                final_v, final_r, overrides = safety_override(
                    alert, agent_v, agent_r, prior, proximity
                )
                return {
                    "verdict": final_v,
                    "reason":  final_r,
                    "agent_verdict": agent_v,
                    "safety_overrides": overrides,
                    "proximity_match": proximity["match"],
                    "sector": sector,
                    "index": index,
                    "steps_used": step + 1,
                }
            else:
                result = {"error": f"unknown tool: {tc.name}"}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": json.dumps(result, default=str),
            })

        # Feed tool results back to the agent for the next turn
        messages.append({"role": "user", "content": tool_results})

    # Hit MAX_STEPS without a decide() — safe emergency stop
    return {
        "verdict": "NORMAL",
        "reason":  f"hit max_steps ({MAX_STEPS}) without deciding; default NORMAL (safe)",
        "agent_verdict": "MAX_STEPS",
        "safety_overrides": None,
        "steps_used": MAX_STEPS,
    }


# ──────────────────────────────────────────────────────────────
# DRY-RUN DRIVERS
# ──────────────────────────────────────────────────────────────

ALERT_COLUMNS = """id, symbol, alert_type, direction, price,
                   entry, stop, target_1,
                   volume_ratio, cvd_diverging, confidence,
                   user_id, created_at"""

def fetch_alerts_for_session(session_date, user_id=None):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT {ALERT_COLUMNS}
                FROM alerts
                WHERE session_date = %s
                  AND (%s::int IS NULL OR user_id = %s)
                ORDER BY created_at ASC, id ASC
            """, (session_date, user_id, user_id))
            return list(cur.fetchall())


def fetch_last_n_alerts(n, user_id=None):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT {ALERT_COLUMNS}
                FROM alerts
                WHERE (%s::int IS NULL OR user_id = %s)
                ORDER BY id DESC
                LIMIT %s
            """, (user_id, user_id, n))
            return list(reversed(list(cur.fetchall())))


def main():
    p = argparse.ArgumentParser(description="Alert Triage Agent — dry-run backtester.")
    p.add_argument("--dry-run", action="store_true",
                   help="Required for v0.1. Don't post anywhere; just print verdicts.")
    p.add_argument("--since", type=str, metavar="YYYY-MM-DD",
                   help="Triage all alerts from this session_date.")
    p.add_argument("--last", type=int, metavar="N",
                   help="Triage the last N alerts in the table.")
    p.add_argument("--user-id", type=int, default=3,
                   help="Filter alerts to this user_id only (default 3 = primary stream). "
                        "Pass 0 to triage every user's alerts (combined).")
    args = p.parse_args()

    if not args.dry_run:
        sys.exit("v0.1 only supports --dry-run. Pass --dry-run to continue.")

    user_id = args.user_id if args.user_id != 0 else None

    if args.since:
        alerts = fetch_alerts_for_session(args.since, user_id=user_id)
        scope = f"session_date = {args.since}, user_id={user_id}"
    elif args.last:
        alerts = fetch_last_n_alerts(args.last, user_id=user_id)
        scope = f"last {args.last} alerts, user_id={user_id}"
    else:
        sys.exit("Pass either --since YYYY-MM-DD or --last N.")

    if not alerts:
        sys.exit(f"No alerts found for: {scope}")

    print(f"Triaging {len(alerts)} alerts ({scope}) on model={MODEL}")
    print("─" * 130)

    counts = {"HIGH": 0, "NORMAL": 0, "MUTE": 0}
    total_steps = 0
    safety_upgrades = []   # alerts where safety net overrode a MUTE
    muted_alerts   = []   # for the audit at the end

    for a in alerts:
        result = triage(dict(a), user_id=user_id)
        v = result["verdict"]
        counts[v] += 1
        total_steps += result["steps_used"]

        if result.get("safety_overrides"):
            safety_upgrades.append((a, result))
        if v == "MUTE":
            muted_alerts.append((a, result))

        marker = {"HIGH": "[HIGH]  ", "NORMAL": "[NORMAL]", "MUTE": "[MUTE]  "}[v]
        agent_v = result.get("agent_verdict", "")
        agent_tag = f" (agent:{agent_v})" if agent_v and agent_v != v else ""
        vr = a.get('volume_ratio')
        vr_str = f"vr={vr:>4.2f}" if vr is not None else "vr=  - "
        cvd = "cvd!" if a.get('cvd_diverging') else "    "
        prox = "PROX" if result.get("proximity_match") else "    "

        # sector + index tags
        sec = result.get("sector", {})
        idx = result.get("index", {})
        sec_tag = ""
        if sec.get("in_sector"):
            if sec.get("aligned"):
                sec_tag = f"SEC+({sec['sector'][:6]})"
            elif sec.get("counter_flow"):
                sec_tag = f"SEC-({sec['sector'][:6]})"
            else:
                sec_tag = f"sec({sec['sector'][:6]})"
        else:
            sec_tag = "         "

        idx_tag = ""
        if idx.get("aligned_with_index"):
            idx_tag = "IDX+"
        elif idx.get("counter_flow_index"):
            idx_tag = "IDX-"
        else:
            idx_tag = "    "

        print(f"{marker} #{a['id']:>5}  {a['symbol']:<10} "
              f"{a['alert_type']:<35} {vr_str} {cvd} {prox} {sec_tag:<14} {idx_tag} "
              f"-> {result['reason']}{agent_tag}")

    print("─" * 130)
    n = len(alerts)
    print(f"\nVerdict summary across {n} alerts:")
    for v in ("HIGH", "NORMAL", "MUTE"):
        c = counts[v]
        pct = round(100 * c / n, 1) if n else 0
        print(f"  {v:6}  {c:>4}  ({pct}%)")
    avg_steps = round(total_steps / n, 2)
    print(f"\nAvg steps per alert: {avg_steps}  (each step = 1 LLM call)")

    # ── Safety-net audit ─────────────────────────────────────────────
    if safety_upgrades:
        print(f"\n⚠  Safety net upgraded {len(safety_upgrades)} MUTE→NORMAL:")
        for a, r in safety_upgrades:
            print(f"     #{a['id']}  {a['symbol']:<10} {a['alert_type']:<32}  "
                  f"reasons: {', '.join(r['safety_overrides'])}")
        print("    (these would have been false-muted by the agent — net caught them)")

    mute_rate = counts["MUTE"] / n if n else 0
    if mute_rate > 0.50:
        print(f"\n⚠  MUTE rate {mute_rate*100:.0f}% — too aggressive. Review reasons.")
    elif mute_rate > 0.30:
        print(f"\n   MUTE rate {mute_rate*100:.0f}% — moderate. Spot-check the muted list.")
    else:
        print(f"\n   MUTE rate {mute_rate*100:.0f}% — conservative.")


if __name__ == "__main__":
    main()
