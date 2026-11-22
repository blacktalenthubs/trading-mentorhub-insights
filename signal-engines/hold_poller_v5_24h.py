#!/usr/bin/env python3
"""hold_poller_v5_24h.py — Victor's 24h equity engine
(approved 2026-11-21, final go 2026-11-22: "build the 24h
equity engine with Alpaca BOATS overnight data wired in").
Built from proto_24h_v4c.py (the 24h prototype), the live
hold_poller_v4c.py (hook contract, card format, structural
targets, grade) and crypto_weekend_watch.py (the rolling
prior-candle signal rules). v4c stays on disk untouched as
the rollback; this file speaks the same --hook contract so
the manipulation-inbox hook can call it unchanged. Dedupe
state is its OWN file (hold_state_24h.json) — v4c's
hold_state.json is never touched.

THE 24H FRAME: six 4H candles per trading day on the ET
grid (starts 00/04/08/12/16/20). A trading day runs from
20:00 ET the evening before to 20:00 ET (so Monday's day
opens Sunday 20:00 ET — Sunday opens included; the weekend
gap Fri 20:00 -> Sun 20:00 ET belongs to no trading day).

ENTRY LINES (strict scope, Victor 2026-11-22): strictly the
LAST completed 4H candle's HIGH, LOW and body OPEN, rolling
— each newly completed candle re-offers its lines and the
previous candle's lines retire. The body OPEN is
RECLAIM-ONLY (never a break; Victor 2026-11-22 10:05: "use
the open. Not closed. A reclaim or loss base on 15mins").
Breaks judge only HIGH/LOW. ALL judgments — reclaims,
rejections, breaks, stops — are on completed 15m closes.
Confluence lines (PWH / PWL / swing H/L) never originate an
entry: they feed stop geometry and stack onto a 4H line
within 0.1% as a named notice ("4H LOW + PWL").

SETUPS:
- RECLAIM (long): a bar trades below L and a completed 15m
  bar closes back above L -> LONG at L. REJECTION (short)
  mirrors. The wick may cross the stop line; only closes
  judge (the v4c state machine, on 15m bars).
- BREAK: a completed 15m bar opens on one side of a HIGH/
  LOW line and closes on the other -> entry at L in the
  break direction. One bar closing through several lines
  is ONE break, at the first line crossed (the delivery
  sweep collapses the rest).

GEOMETRY:
- STOP (pair rule): the next line beyond the entry in the
  merged line map (extremes + body opens of the last 12
  completed candles + confluence), skipping lines within
  0.05% of the entry (same print). FOR A BREAK the stop
  line is the entry candle's OTHER extreme (settled 24h
  spec, 2026-11-21). Judged only on a completed 15m close
  beyond the stop line. No stop line -> the call still
  delivers with "stop: none set" and exits on its target
  only (Victor, 2026-11-20: no-stop never blocks).
- TARGET: the nearest STRUCTURAL level in the trade
  direction (PDH/PDL, PWH/PWL, PMH/PML, swing H/L, daily
  8/20/50/200 SMA), exactly as v4c picks it; none that way
  = no target on the call. Target exits are computed for
  the ledger but are NEVER part of the deliverable hook
  output (target hits are logged, not posted — Victor,
  2026-11-21); the hook's exit events carry stop exits
  only, exactly as v4c's do.

DELIVERY BRAKES (parity, after the 2026-11-22 brake
removal): one delivered entry per line per side per
trading day; a same-direction fire at a line while a call
from that line is still open is suppressed; a break at
the live target of an open same-direction call is
suppressed (the move completing); the same-bar break
collapse. The FLIP is simply the next fire: an opposite
fire at the same line on a 15m close delivers even while
the first call stands. NO count caps, NO zone rule, NO
chop set. Every card carries the Grade line (Strong /
Average / Weak) and the Vol pace line — labels only,
never gates.

SHORTS — INDEX ONLY (Victor, 2026-11-19): a SHORT is
deliverable only on SPY, QQQ, SMH, SOXL, IWM (or the
day-scoped override's list). Longs unchanged.

DATA — THE POINT OF THE BUILD: Yahoo's 15m feed skips the
overnight session, so on Yahoo alone the 20:00 and 00:00
ET candles never form. v5 merges Alpaca overnight bars
(BOATS feed) into the Yahoo 15m series: bars are deduped
by timestamp, Alpaca wins on overlap inside the overnight
window (20:00-04:00 ET), Yahoo wins elsewhere. Keys are
read at runtime from alpaca_keys.json ({"key", "secret"})
in this folder — never hardcoded, never printed. When the
file is absent the engine runs Yahoo-only (today's v4c
behavior, overnight candles missing) and says so on
stderr. An Alpaca failure likewise falls back to Yahoo
only; the data merge never crashes a hook run.

LIVE CONTRACT (v4c's, unchanged): --hook prints a JSON
array of fresh entry rows + exit events on stdout;
diagnostics to stderr. Entry rows carry the v2 schema plus
engine "v5_24h". Session is reported as "pm" for a confirm
before 09:30 ET and "rth" from 09:30 ET (the v2 schema's
two values; the row's confirm_ts / entry_time_ct carry the
full truth). v5's own ledgers: hold_emitted_24h.jsonl,
exit_state_24h.json, exit_emitted_24h.jsonl, lines5-<day>
.json, last_run_24h.json — its live exits resolve from
evaluated.jsonl rows tagged engine "v5_24h", so nothing
here can see or disturb v4c's book before cutover.

Usage:
    python3 hold_poller_v5_24h.py --hook [--dry] [SYM ...]
    python3 hold_poller_v5_24h.py --dry-run [SYM ...]
    python3 hold_poller_v5_24h.py --lines YYYY-MM-DD [SYM ...]
    python3 hold_poller_v5_24h.py --replay YYYY-MM-DD [SYM ...]
    python3 hold_poller_v5_24h.py --replay2json YYYY-MM-DD [SYM ...]
    (dates are ET trading days: 2026-11-20 = Thu 20:00 ET
    -> Fri 20:00 ET)
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime, timedelta, \
    timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hold_poller import (fetch, CT, ET, FRESH_SECS,  # noqa: E402
                         EVALUATED_PATH, daily_context)

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- universe
# Mirrors hold_poller_v4c.py exactly (replay universes, live
# sections/Zanger sources, the day-scoped override and the
# FOCUS pause), so the two engines never disagree about
# what is being watched.
INDEX = ["BUG", "AMD", "IWM", "QQQ", "SOXL", "SMH", "SPY", "NVDA"]
STRONGEST = ["PANW", "CRWD", "CAKE", "LULU", "MOD", "NET", "ANET",
             "TGT", "AMZN", "AVGO", "VSAT", "SPCX", "P", "GLBE"]
ZANGER_BY_DATE = {
    "2026-11-16": ["LLY", "SQQQ", "FROG", "AAPL", "U", "TOST",
                   "META", "HUM", "GKOS"],
    "2026-11-17": ["LLY", "GKOS", "TOST"],
    "2026-11-18": ["LLY", "CAKE", "VIK"],
}
UNIVERSE_BY_DATE = {
    "2026-11-12": ["SPY", "QQQ"],
}
for _d, _z in ZANGER_BY_DATE.items():
    UNIVERSE_BY_DATE[_d] = list(dict.fromkeys(INDEX + STRONGEST + _z))

SECTIONS_PATH = os.path.expanduser(
    "~/workspace/key-levels-monitor/sections.json")
ZANGER_STATE_PATH = os.path.expanduser(
    "~/workspace/goals/chartpattern-trial-two-week-scorecard/"
    "hidden_files/zanger-morning-poll-state.json")


def zanger_today(day):
    """The day's Zanger morning names from the morning email
    poll's state file — only when the poll's last notified
    date IS `day` (CT). Anything else (stale file, missing
    file) is no names, never a guess."""
    try:
        with open(ZANGER_STATE_PATH) as f:
            st = json.load(f)
    except Exception:
        return []
    if st.get("last_notified_date") != day.isoformat():
        return []
    return [str(t).strip().upper() for t in st.get("tickers", [])
            if str(t).strip()]


OVERRIDE_PATH = os.path.join(BASE, "universe_override.json")


def universe_override(day):
    """A day-scoped universe override (Victor, 2026-11-20).
    universe_override.json: {"date": "YYYY-MM-DD",
    "symbols": [...], "shorts": [...]}. Active only when
    its date equals the session day — it expires on its own
    the next day. Returns the dict or None."""
    try:
        with open(OVERRIDE_PATH) as f:
            ov = json.load(f)
        if ov.get("date") == day.isoformat() and ov.get("symbols"):
            return ov
    except Exception:
        pass
    return None


def short_syms_for(day):
    """Short-eligible symbols for the session: the override's
    list while an override is active, else the standing
    index-only set."""
    ov = universe_override(day)
    if ov:
        return {str(s).strip().upper()
                for s in (ov.get("shorts") or ov["symbols"])}
    return SHORT_SYMS


def live_universe(day=None):
    """INDEX + STRONGEST from the sections sync file, plus
    the day's Zanger morning names; the built-in 2026-11-18
    evening lists are the fallback. A day-scoped
    universe_override.json replaces all of it for that day.
    FOCUS (Victor, 2026-11-21): while the 24h-candle system
    is being perfected, signals focus on SPY, QQQ, SMH and
    IWM only — the sections/Zanger universe below is paused,
    not deleted. Clear FOCUS_SYMS to restore it."""
    day = day or datetime.now(CT).date()
    ov = universe_override(day)
    if ov:
        return [str(s).strip().upper() for s in ov["symbols"]]
    if FOCUS_SYMS:
        return list(FOCUS_SYMS)
    secs = {}
    try:
        with open(SECTIONS_PATH) as f:
            secs = json.load(f)
    except Exception:
        secs = {}
    idx = secs.get("INDEX") or secs.get("MORNING FOCUS") or []
    strong = secs.get("STRONGEST") or []
    syms = []
    for s in list(idx) + list(strong):
        s = str(s).strip().upper()
        if s and s not in syms:
            syms.append(s)
    if len(syms) < 5:
        syms = list(INDEX + STRONGEST)
    for t in zanger_today(day):
        if t not in syms:
            syms.append(t)
    return ["ETH-USD" if s == "ETHUSD" else s for s in syms]


# ---------------------------------------------------------------- constants
SKIP_PCT = 0.05              # lines within 0.05% of entry = same print
STACK_PCT = 0.10             # confluence stack tolerance (~0.1%)
# Shorts are index-only in ALL sessions (Victor, 2026-11-19).
SHORT_SYMS = {"SPY", "QQQ", "SMH", "SOXL", "IWM"}
SHORT_REASON = ("short — index only (SPY/QQQ/SMH/SOXL/IWM) "
                "(Victor, 2026-11-19)")
FOCUS_SYMS = ["SPY", "QQQ", "SMH", "IWM"]
OUT_PREFIX = os.environ.get("V5_PREFIX", "v5")
OUT_DIR = os.environ.get("V5_OUT_DIR", BASE)

# v5's own state / ledgers — v4c's files are never touched.
STATE_PATH_24H = os.path.join(BASE, "hold_state_24h.json")
EMITTED_PATH_24H = os.path.join(BASE, "hold_emitted_24h.jsonl")
LAST_RUN_PATH_24H = os.path.join(BASE, "last_run_24h.json")
EXIT_STATE_PATH_24H = os.path.join(BASE, "exit_state_24h.json")
EXIT_EMITTED_PATH_24H = os.path.join(BASE,
                                     "exit_emitted_24h.jsonl")
# The shared exit ledger telegram_sender.py reads (it skips
# target exits itself). v5 mirrors every recorded exit row
# here as well as to its own ledger, so Telegram stop exits
# keep flowing after cutover (found in the parent review,
# 2026-11-22 — as first built, v5 wrote only its own file
# and its sent entries never reached evaluated.jsonl, which
# would have silently killed live exits and Telegram).
SHARED_EXIT_EMITTED_PATH = os.path.join(BASE,
                                        "exit_emitted.jsonl")
ALPACA_KEYS_PATH = os.path.join(BASE, "alpaca_keys.json")
ALPACA_HOST = "https://data.alpaca.markets"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _fmt(ts):
    return datetime.fromtimestamp(ts, CT).strftime("%I:%M %p CT")


# ---------------------------------------------------------------- trading day

def trading_day(ts):
    """The ET trading-day date containing epoch `ts`: the
    day rolls at 20:00 ET, so an evening timestamp belongs
    to the NEXT date's trading day (Monday's day opens
    Sunday 20:00 ET)."""
    dt = datetime.fromtimestamp(ts, ET)
    if dt.hour >= 20:
        return dt.date() + timedelta(days=1)
    return dt.date()


def day_bounds(day):
    """(start_ts, end_ts) of trading day `day` (an ET date):
    [day-1 20:00 ET, day 20:00 ET)."""
    start = datetime.combine(day - timedelta(days=1),
                             dtime(20, 0), ET)
    return int(start.timestamp()), int(start.timestamp()) \
        + 24 * 3600


# ---------------------------------------------------------------- data

def _overnight(ts):
    """True when epoch `ts` starts inside the overnight
    window 20:00-04:00 ET — the window Alpaca's BOATS feed
    owns in the merge."""
    h = datetime.fromtimestamp(ts, ET).hour
    return h >= 20 or h < 4


def alpaca_bars(sym, start_ts, end_ts):
    """15Min BOATS bars for `sym` in [start_ts, end_ts] from
    Alpaca's Market Data API. Keys are read from
    alpaca_keys.json at call time and never logged. The
    historical end is capped 15 minutes in the past (the
    feed's historical-delay rule). Returns [] when the
    keys file is absent (the caller notes the diagnostic);
    raises on HTTP errors so the caller can fall back."""
    with open(ALPACA_KEYS_PATH) as f:
        keys = json.load(f)
    end_ts = min(end_ts, int(time.time()) - 15 * 60)
    if end_ts <= start_ts:
        return []
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    params = {
        "timeframe": "15Min", "feed": "boats",
        "start": datetime.fromtimestamp(start_ts, timezone.utc)
        .strftime(fmt),
        "end": datetime.fromtimestamp(end_ts, timezone.utc)
        .strftime(fmt),
        "limit": 10000, "sort": "asc", "adjustment": "raw",
    }
    url = (f"{ALPACA_HOST}/v2/stocks/{sym}/bars?"
           + urllib.parse.urlencode(params))
    headers = {"APCA-API-KEY-ID": keys["key"],
               "APCA-API-SECRET-KEY": keys["secret"]}
    bars = []
    while True:
        req = urllib.request.Request(url, headers=headers)
        d = json.loads(urllib.request.urlopen(req, timeout=25)
                       .read())
        for b in d.get("bars") or []:
            t = int(datetime.fromisoformat(
                b["t"].replace("Z", "+00:00")).timestamp())
            o, h, l, c = b["o"], b["h"], b["l"], b["c"]
            # the same corrupt-print clamp Yahoo's 15m feed
            # gets in hold_poller.fetch (1% envelope)
            h = min(h, max(o, c) * 1.01)
            l = max(l, min(o, c) * 0.99)
            bars.append({"t": t, "o": o, "h": h, "l": l,
                         "c": c, "v": b.get("v") or 0})
        token = d.get("next_page_token")
        if not token:
            return bars
        params["page_token"] = token
        url = (f"{ALPACA_HOST}/v2/stocks/{sym}/bars?"
               + urllib.parse.urlencode(params))


def merge_bars(yahoo, alpaca):
    """Dedupe by timestamp: Alpaca wins on overlap inside
    the overnight window (20:00-04:00 ET); Yahoo wins
    elsewhere (an Alpaca bar outside the window only fills
    a timestamp Yahoo lacks)."""
    by_t = {b["t"]: b for b in yahoo}
    for b in alpaca:
        if b["t"] not in by_t or _overnight(b["t"]):
            by_t[b["t"]] = b
    return [by_t[t] for t in sorted(by_t)]


_ALPACA_NOTED = False


def load_symbol(sym, intraday_range="1mo"):
    """Merged 15m bars (Yahoo + Alpaca BOATS overnight) plus
    daily bars. The Alpaca request spans the Yahoo window
    so every overnight session inside it can fill. Without
    alpaca_keys.json the merge is skipped (Yahoo only) with
    a one-time stderr diagnostic; an Alpaca error falls
    back the same way — the merge never crashes a run."""
    global _ALPACA_NOTED
    bars15 = fetch(sym, intraday_range, "15m", prepost=True)
    daily = fetch(sym, "1y", "1d", prepost=False)
    if not bars15:
        raise ValueError("no 15m bars")
    n_alpaca = 0
    if os.path.exists(ALPACA_KEYS_PATH):
        try:
            ab = alpaca_bars(sym, bars15[0]["t"] - 3600,
                             bars15[-1]["t"] + 3600)
            n_alpaca = len(ab)
            bars15 = merge_bars(bars15, ab)
        except Exception as e:  # noqa: BLE001
            log(f"alpaca merge failed {sym}: "
                f"{type(e).__name__}: {e} — Yahoo only")
    elif not _ALPACA_NOTED:
        _ALPACA_NOTED = True
        log("alpaca_keys.json not found — Yahoo-only: the "
            "20:00/00:00 ET overnight candles will be missing")
    return {"bars15": bars15, "daily": daily,
            "alpaca_bars": n_alpaca}


def load_symbol_retry(sym, intraday_range="1mo"):
    try:
        return sym, load_symbol(sym, intraday_range), None
    except Exception as e:  # noqa: BLE001
        time.sleep(1.0)
        try:
            return sym, load_symbol(sym, intraday_range), None
        except Exception as e2:  # noqa: BLE001
            return sym, None, f"{type(e2).__name__}: {e2}"


# ---------------------------------------------------------------- candles

def grid_4h_candles(bars15):
    """4H candles on the 24h grid (ET starts 00/04/08/12/
    16/20), aggregated from ALL 15m bars (pre/post and
    overnight included). Returns {start_ts: {'o','h','l',
    'c','start'}}."""
    out = {}
    for b in sorted(bars15, key=lambda x: x["t"]):
        dt = datetime.fromtimestamp(b["t"], ET)
        start = dt.replace(hour=dt.hour - dt.hour % 4,
                           minute=0, second=0, microsecond=0)
        sts = int(start.timestamp())
        cur = out.get(sts)
        if cur is None:
            out[sts] = {"o": b["o"], "h": b["h"], "l": b["l"],
                        "c": b["c"], "start": sts}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
    return out


def _completed(candles, asof_ts):
    """Grid candles fully completed by `asof_ts`, oldest
    first."""
    return [candles[k] for k in sorted(candles)
            if k + 4 * 3600 <= asof_ts]


# ---------------------------------------------------------------- lines

def confluence_lines(daily, day):
    """The confluence lines for trading day `day` (Victor,
    2026-11-18 22:25): prior week high / low and the last
    confirmed daily swing high / low — pivot 5,5 over
    settled daily bars (ET date < day), exactly as his
    proximity Pine computes them. INFORMATION ONLY since
    2026-11-22: stop/target geometry and named confluence
    on a stacked 4H line, never an entry origin."""
    out = []
    ctx = daily_context(daily, day)
    keys = ctx.get("keys", {})
    if "PWH" in keys:
        out.append({"value": keys["PWH"], "label": "PWH"})
    if "PWL" in keys:
        out.append({"value": keys["PWL"], "label": "PWL"})
    settled = [b for b in daily
               if datetime.fromtimestamp(b["t"], ET).date() < day]
    last_ph = last_pl = None
    for i in range(5, len(settled) - 5):
        win = settled[i - 5:i + 6]
        hs = [b["h"] for b in win]
        if settled[i]["h"] == max(hs) and hs.count(max(hs)) == 1:
            last_ph = settled[i]["h"]
        ls = [b["l"] for b in win]
        if settled[i]["l"] == min(ls) and ls.count(min(ls)) == 1:
            last_pl = settled[i]["l"]
    if last_ph is not None:
        out.append({"value": last_ph, "label": "Swing High"})
    if last_pl is not None:
        out.append({"value": last_pl, "label": "Swing Low"})
    return out


def _merge_conf(lines, conf):
    """Merge confluence lines into a line list: within
    STACK_PCT of an existing line, the confluence label
    stacks onto it ("4H LOW + PWL") as a named notice;
    otherwise the confluence line stands alone in the map.
    STRICT ENTRY SCOPE (Victor, 2026-11-22): a confluence
    line NEVER confers entry eligibility — not standalone,
    and not by stacking onto a geometry-only line."""
    lines = [dict(x) for x in lines]
    for c in conf:
        best = None
        for ln in lines:
            d = abs(ln["value"] - c["value"]) / c["value"] * 100
            if d <= STACK_PCT and (best is None or d < best[0]):
                best = (d, ln)
        if best is not None:
            ln = best[1]
            if c["label"] not in ln["label"].split(" + "):
                ln["label"] += " + " + c["label"]
        else:
            lines.append({"value": c["value"], "label": c["label"],
                          "entry_ok": False, "body": False})
    return sorted(lines, key=lambda x: x["value"])


def line_map(candles, conf, asof_ts):
    """(entry_lines, all_lines, last_candle) as of `asof_ts`.
    all_lines = the merged map of the last 12 completed
    candles' HIGH / LOW / body OPEN plus confluence — the
    pair-geometry map. entry_lines = the subset from the
    LAST completed candle only (its HIGH, LOW and body
    OPEN): the strict entry scope. Same-cent values merge
    into one line (label parts deduped); a merged line is
    entry_ok if ANY component is, and 'body' only if EVERY
    component is (an open value equal to an extreme is the
    extreme's line — v4c's rule)."""
    comp = _completed(candles, asof_ts)[-12:]
    if not comp:
        return [], [], None
    last = comp[-1]
    raw = []
    for cnd in comp:
        is_last = cnd is last
        raw.append({"value": cnd["h"], "label": "4H HIGH",
                    "entry_ok": is_last, "body": False})
        raw.append({"value": cnd["l"], "label": "4H LOW",
                    "entry_ok": is_last, "body": False})
        raw.append({"value": cnd["o"], "label": "4H body open",
                    "entry_ok": is_last, "body": True})
    by_key = {}
    for it in raw:
        k = round(it["value"], 2)
        if k in by_key:
            cur = by_key[k]
            for part in it["label"].split(" + "):
                if part not in cur["label"].split(" + "):
                    cur["label"] += " + " + part
            cur["entry_ok"] = cur["entry_ok"] or it["entry_ok"]
            cur["body"] = cur.get("body", False) and it["body"]
        else:
            by_key[k] = dict(it)
    merged = sorted(by_key.values(), key=lambda x: x["value"])
    merged = _merge_conf(merged, conf)
    entry = [ln for ln in merged if ln["entry_ok"]]
    return entry, merged, last


def structural_targets(daily, day):
    """The day's STRUCTURAL target set (Victor, 2026-11-19
    13:45): PDH/PDL, PWH/PWL, PMH/PML, the last confirmed
    swing high/low, and the daily 8/20/50/200 SMAs — all
    from settled daily bars via hold_poller's daily_context
    plus the swing pivots. Near-duplicates within STACK_PCT
    stack their labels. Returns [{'value', 'label'}]."""
    ctx = daily_context(daily, day)
    raw = []
    for name in ("PDH", "PDL", "PWH", "PWL", "PMH", "PML"):
        if name in ctx.get("keys", {}):
            raw.append({"value": ctx["keys"][name],
                        "label": name})
    for ln in confluence_lines(daily, day):
        if ln["label"].startswith("Swing"):
            raw.append(ln)
    for n in (8, 20, 50, 200):
        if n in ctx.get("smas", {}):
            raw.append({"value": ctx["smas"][n][0],
                        "label": f"{n} SMA"})
    raw.sort(key=lambda x: x["value"])
    out = []
    for ln in raw:
        if out and abs(ln["value"] - out[-1]["value"]) \
                / ln["value"] * 100 <= STACK_PCT:
            if ln["label"] not in out[-1]["label"].split(" + "):
                out[-1]["label"] += " + " + ln["label"]
        else:
            out.append(dict(ln))
    return out


def pick_structural_target(structs, value, side):
    """Nearest structural level in the trade direction,
    skipping anything within SKIP_PCT of the entry (same
    print). None when no structural level sits that way —
    the call then carries no target rather than a fake
    narrow one."""
    best = None
    for ln in structs:
        v = ln["value"]
        if side == "LONG" and v > value:
            if (v - value) / value * 100 <= SKIP_PCT:
                continue
            if best is None or v < best["value"]:
                best = ln
        elif side == "SHORT" and v < value:
            if (value - v) / value * 100 <= SKIP_PCT:
                continue
            if best is None or v > best["value"]:
                best = ln
    return best


def pair_geometry(lines, value, side):
    """(stop_line, t1_line) line objects for an entry at
    `value` from the merged map, or (None, ...) when a side
    of the pair does not exist. Lines within SKIP_PCT of
    the entry are the same print and are skipped."""
    below = [ln for ln in lines
             if ln["value"] < value
             and (value - ln["value"]) / value * 100 > SKIP_PCT]
    above = [ln for ln in lines
             if ln["value"] > value
             and (ln["value"] - value) / value * 100 > SKIP_PCT]
    if side == "LONG":
        stop = max(below, key=lambda x: x["value"]) if below else None
        t1 = min(above, key=lambda x: x["value"]) if above else None
    else:
        stop = min(above, key=lambda x: x["value"]) if above else None
        t1 = max(below, key=lambda x: x["value"]) if below else None
    return stop, t1


# ---------------------------------------------------------------- volume

def volume_context(data, day, confirm_ts, cache):
    """Volume context for a fire confirmed at `confirm_ts`
    (Victor, 2026-11-19: context only, never a gate).
    Computed on the MERGED 15m series (so overnight BOATS
    volume counts): (confirming bar's volume, cumulative
    volume over trading day `day` through the confirming
    bar, relative pace vs the mean cumulative at the same
    elapsed point of the prior 10 trading days in the feed
    — None when no baseline day has volume)."""
    if confirm_ts in cache:
        return cache[confirm_ts]
    bars = data["bars15"]
    day_start, _ = day_bounds(day)

    def cum(d, cutoff_ts):
        ds, de = day_bounds(d)
        return sum(b.get("v") or 0 for b in bars
                   if ds <= b["t"] and b["t"] + 900 <= cutoff_ts
                   and b["t"] < de)

    cum_today = cum(day, confirm_ts)
    bar_vol = None
    for b in bars:
        if b["t"] < confirm_ts <= b["t"] + 900:
            bar_vol = b.get("v") or 0
            break
    elapsed = confirm_ts - day_start
    prior = sorted({trading_day(b["t"]) for b in bars
                    if trading_day(b["t"]) < day})
    base = []
    for d in prior[-10:]:
        ds, _de = day_bounds(d)
        c = cum(d, ds + elapsed)
        if c > 0:
            base.append(c)
    rvol = round(cum_today / (sum(base) / len(base)), 2) \
        if base else None
    out = (bar_vol, cum_today, rvol)
    cache[confirm_ts] = out
    return out


def vol_text(fields):
    """The card's volume line: the pace multiple only
    (Victor, 2026-11-22 — the cumulative shares figure is
    noise on a card; the fields stay on the ledger rows).
    None when no pace was measured."""
    vr = fields.get("vol_rvol")
    if vr is None:
        return None
    return f"Vol: {vr:.1f}x usual pace"


def grade_text(call):
    """Strong / Average / Weak — the same scale as the
    weekend ETH system and v4c (Victor, 2026-11-21; one
    rule set for both systems). Setup: a stacked line (the
    label carries a '+') or a test that travelled >= 0.10%
    past the line is a manipulation-grade setup. Volume:
    >= 2x usual pace confirms; under 1x is thin. A label
    only — it never holds a card back."""
    lv = call["level"]
    te = call.get("test_extreme")
    sweep_pct = abs(te - lv) / lv * 100.0 if te is not None \
        else 0.0
    rvol = call.get("vol_rvol")
    if ("+" in call.get("label", "")) or sweep_pct >= 0.10 \
            or (rvol is not None and rvol >= 2.0):
        return "Strong"
    if rvol is not None and rvol < 1.0:
        return "Weak"
    return "Average"


# ---------------------------------------------------------------- detect

def _session_of(confirm_ts):
    """The v2 schema's session value for a confirm: "pm"
    before 09:30 ET (premarket, overnight included), "rth"
    from 09:30 ET."""
    dt = datetime.fromtimestamp(confirm_ts, ET)
    return "pm" if dt.hour * 60 + dt.minute < 9 * 60 + 30 \
        else "rth"


def detect_24h(sym, data, day):
    """All entry candidates for `sym` on trading day `day`,
    judged bar by bar over the day's merged 15m bars. The
    entry-line set rolls at every 4H grid boundary: each
    window is judged against the candle that completed at
    its start. Returns (candidates, lines_asof_day_end,
    meta). Static suppressions ride as 'pre_reason';
    delivery-time suppressions happen in simulate_24h."""
    candles = grid_4h_candles(data["bars15"])
    conf = confluence_lines(data["daily"], day)
    structs = structural_targets(data["daily"], day)
    day_start, day_end = day_bounds(day)
    bars = [b for b in data["bars15"]
            if day_start <= b["t"] < day_end]
    entry0, all0, _last0 = line_map(candles, conf, day_end)
    if not bars:
        return [], all0, {"alpaca_bars": data.get("alpaca_bars", 0)}
    _vol_cache = {}
    candidates = []

    def add_cand(fire, side, ln, confirm_ts, extreme,
                 entry_close, candle, geo_lines):
        if fire == "break":
            # settled 24h spec: a break's stop line is the
            # entry candle's OTHER extreme
            stop_v = candle["l"] if side == "LONG" \
                else candle["h"]
            stop = None
            if abs(stop_v - ln["value"]) / ln["value"] * 100 \
                    > SKIP_PCT:
                lab = "4H LOW" if side == "LONG" else "4H HIGH"
                for gl in geo_lines:
                    if round(gl["value"], 2) == round(stop_v, 2):
                        lab = gl["label"]
                        break
                stop = {"value": stop_v, "label": lab}
            if stop is None:
                stop, _t1 = pair_geometry(geo_lines,
                                          ln["value"], side)
        else:
            stop, _t1 = pair_geometry(geo_lines, ln["value"],
                                      side)
        t1 = pick_structural_target(structs, ln["value"], side)
        cand = {
            "symbol": sym, "kind": "entry", "fire": fire,
            "side": side, "session": _session_of(confirm_ts),
            "level": round(ln["value"], 2), "label": ln["label"],
            "stop_line": round(stop["value"], 2) if stop else None,
            "stop_label": stop["label"] if stop else None,
            "target": round(t1["value"], 2) if t1 else None,
            "target_label": t1["label"] if t1 else None,
            "confirm_ts": confirm_ts, "time_ct": _fmt(confirm_ts),
            "test_extreme": round(extreme, 2)
            if extreme is not None else None,
            "entry_close": round(entry_close, 2)
            if entry_close is not None else None,
            "confirm_tf": "15m", "pre_reason": None,
            "gap_pct": None,
        }
        vb, vc, vr = volume_context(data, day, confirm_ts,
                                    _vol_cache)
        cand["vol_bar"] = vb
        cand["vol_cum"] = vc
        cand["vol_rvol"] = vr
        candidates.append(cand)
        return cand

    ws = day_start
    while ws < day_end:
        entry_lines, geo_lines, candle = line_map(
            candles, conf, ws)
        if candle is not None and entry_lines:
            win_bars = [b for b in bars
                        if ws <= b["t"] < ws + 4 * 3600]
            state = {}   # rounded value -> {'dip', 'poke'}
            for b in win_bars:
                end = b["t"] + 900
                for ln in entry_lines:
                    L = ln["value"]
                    k = round(L, 2)
                    # BREAK — extremes only; the body open
                    # is reclaim-only (Victor, 2026-11-22)
                    if not ln.get("body"):
                        if b["o"] > L and b["c"] < L:
                            add_cand("break", "SHORT", ln, end,
                                     b["c"], b["c"], candle,
                                     geo_lines)
                        elif b["o"] < L and b["c"] > L:
                            add_cand("break", "LONG", ln, end,
                                     b["c"], b["c"], candle,
                                     geo_lines)
                    # RECLAIM / REJECTION — wick through the
                    # line, completed 15m close back across
                    st = state.setdefault(
                        k, {"dip": None, "poke": None})
                    if b["l"] < L:
                        st["dip"] = b["l"] if st["dip"] is None \
                            else min(st["dip"], b["l"])
                    if b["h"] > L:
                        st["poke"] = b["h"] if st["poke"] is None \
                            else max(st["poke"], b["h"])
                    if st["dip"] is not None and b["c"] > L:
                        add_cand("reclaim", "LONG", ln, end,
                                 st["dip"], b["c"], candle,
                                 geo_lines)
                        st["dip"] = None
                    if st["poke"] is not None and b["c"] < L:
                        add_cand("rejection", "SHORT", ln, end,
                                 st["poke"], b["c"], candle,
                                 geo_lines)
                        st["poke"] = None
        ws += 4 * 3600

    candidates.sort(key=lambda c: c["confirm_ts"])
    return candidates, all0, {"alpaca_bars":
                              data.get("alpaca_bars", 0)}


# ---------------------------------------------------------------- delivery

def simulate_24h(sym, candidates, data, day):
    """Chronological delivery sweep over the trading day's
    15m bars: candidates -> suppressions -> open calls;
    exits judge bar by bar (stop = a completed 15m close
    beyond the stop line, judged before a target touch
    within the same bar; calls die at the day's 20:00 ET
    end). Returns (delivered, suppressed). The remaining
    brakes only (parity, 2026-11-22): per-line+side dedupe
    for the day, the still-open rule, the break-at-live-
    target rule, the same-bar break collapse. The flip —
    an opposite fire at the same line — is a new call."""
    day_start, day_end = day_bounds(day)
    bars = [b for b in data["bars15"]
            if day_start <= b["t"] < day_end]
    short_syms = short_syms_for(day)
    delivered_keys = set()   # (rounded level, side)
    open_calls = []
    delivered = []
    suppressed = []
    ci = 0
    cands = sorted(candidates, key=lambda c: c["confirm_ts"])

    # same-bar break collapse (weekend parity): one bar
    # closing through several lines is ONE break — the
    # first line crossed (lowest for LONG, highest for
    # SHORT) fires; the rest are the same event
    seen_break_bar = {}
    for cand in cands:
        if cand["fire"] != "break" or cand["pre_reason"]:
            continue
        k = (cand["confirm_ts"], cand["side"])
        keep = seen_break_bar.get(k)
        if keep is None:
            seen_break_bar[k] = cand
            continue
        better = (cand["level"] < keep["level"]) \
            if cand["side"] == "LONG" \
            else (cand["level"] > keep["level"])
        loser = keep if better else cand
        if better:
            seen_break_bar[k] = cand
        loser["pre_reason"] = ("same-bar break — first line "
                               "crossed already fires")

    def open_from(entry_line, side):
        return any(c["level"] == entry_line and c["side"] == side
                   for c in open_calls)

    for b in bars:
        end = b["t"] + 900
        # (1) entry candidates confirmed by this bar end
        while ci < len(cands) and cands[ci]["confirm_ts"] <= end:
            cand = cands[ci]
            ci += 1
            if cand["pre_reason"]:
                cand["drop_reason"] = cand["pre_reason"]
                suppressed.append(cand)
                continue
            if cand["side"] == "SHORT" \
                    and sym not in short_syms:
                cand["drop_reason"] = SHORT_REASON
                suppressed.append(cand)
                continue
            if cand["fire"] == "break":
                hit = next(
                    (c for c in open_calls
                     if c["target"] is not None
                     and round(c["target"], 2) == cand["level"]
                     and c["side"] == cand["side"]), None)
                if hit is not None:
                    cand["drop_reason"] = ("break at live T1 of an "
                                           "open call — move "
                                           "completing")
                    suppressed.append(cand)
                    continue
            if open_from(cand["level"], cand["side"]):
                cand["drop_reason"] = ("same-direction call from "
                                       "this line still open")
                suppressed.append(cand)
                continue
            dk = (cand["level"], cand["side"])
            if dk in delivered_keys:
                cand["drop_reason"] = ("already delivered at this "
                                       "line+side today")
                suppressed.append(cand)
                continue
            delivered_keys.add(dk)
            call = dict(cand)
            call.pop("pre_reason", None)
            call["exit"] = {"exit_kind": "open", "exit_price": None,
                            "exit_time_ct": None}
            delivered.append(call)
            open_calls.append(call)
        # (2) exits for calls opened before this bar
        for call in list(open_calls):
            if call["confirm_ts"] >= end:
                continue
            stop, t1v = call["stop_line"], call["target"]
            hit = None
            if call["side"] == "LONG":
                if stop is not None and b["c"] < stop:
                    hit = ("stopped", round(b["c"], 2))
                elif t1v is not None and b["h"] >= t1v:
                    hit = ("target", round(t1v, 2))
            else:
                if stop is not None and b["c"] > stop:
                    hit = ("stopped", round(b["c"], 2))
                elif t1v is not None and b["l"] <= t1v:
                    hit = ("target", round(t1v, 2))
            if hit:
                call["exit"] = {"exit_kind": hit[0],
                                "exit_price": hit[1],
                                "exit_time_ct": _fmt(end)}
                open_calls.remove(call)
    # candidates confirmed after the last bar end (the feed
    # ran out mid-day) still get an outcome so nothing
    # vanishes silently.
    while ci < len(cands):
        cand = cands[ci]
        ci += 1
        cand["drop_reason"] = cand["pre_reason"] or \
            "confirmed after the day's last judged bar"
        suppressed.append(cand)
    for call in delivered:
        call.pop("pre_reason", None)
    return delivered, suppressed


# ---------------------------------------------------------------- live rows
# The v2 hook schema, built from v5's internal calls — the
# same shape as v4c's rows, tagged engine "v5_24h". side is
# SUPPORT (long) / RESISTANCE (short); chat_line is the
# finished card (alert line + Reason + Grade + Vol).

def reason_text(call, source_label):
    tf = call.get("confirm_tf")
    te = call.get("test_extreme")
    if call["fire"] == "reclaim":
        return (f"Reclaim at {source_label} — wicked to "
                f"{te:.2f}, then a {tf} close back above it")
    if call["fire"] == "rejection":
        return (f"Rejection at {source_label} — poked to "
                f"{te:.2f}, close back below it")
    if call["fire"] == "break":
        return (f"Break of {source_label} — 15m close through "
                f"it at {call['entry_close']:.2f}")
    return ""


def build_chat_line(call, source_label):
    d = call["side"]
    level = call["level"]
    stop_word = "below" if d == "LONG" else "above"
    line = f"{call['symbol']} {d} {level:.2f} — entry {level:.2f}"
    if call["target"] is not None:
        line += f" · target {call['target']:.2f}"
    if call["stop_line"] is not None:
        line += (f" · stop: 15m close {stop_word} "
                 f"{call['stop_line']:.2f}")
    else:
        line += " · stop: none set"
    line += "\nReason: " + reason_text(call, source_label)
    line += "\nGrade: " + grade_text(call)
    vt = vol_text(call)
    if vt:
        line += "\n" + vt
    return line


def to_live_row(call, fire_no):
    source_label = f"{call['label']} {call['level']:.2f}"
    if call["stop_line"] is not None:
        conf = (f"stop {call['stop_label']} "
                f"{call['stop_line']:.2f}")
        if call["target"] is not None:
            conf += (f" · target {call['target_label']} "
                     f"{call['target']:.2f}")
        else:
            conf += " · no target line in the set"
    else:
        conf = "no stop line in the set"
        if call["target"] is not None:
            conf += (f" · target {call['target_label']} "
                     f"{call['target']:.2f}")
    chat_line = build_chat_line(call, source_label)
    row = {
        "symbol": call["symbol"], "kind": "level_hold",
        "engine": "v5_24h",
        "side": "SUPPORT" if call["side"] == "LONG"
        else "RESISTANCE",
        "direction": call["side"], "fire": call["fire"],
        "reason": reason_text(call, source_label),
        "level": call["level"], "source_label": source_label,
        "sources": [source_label], "confluence": conf, "fight": "",
        "test_extreme": call["test_extreme"],
        "entry_close": call["entry_close"],
        "entry_time_ct": call["time_ct"], "target": call["target"],
        "stop_line": call["stop_line"],
        "stop_label": call["stop_label"],
        "target_label": call["target_label"],
        "vol": None, "vol_avg": None, "vol_mult": None,
        "vol_trend": None,
        "vol_bar": call.get("vol_bar"),
        "vol_cum": call.get("vol_cum"),
        "vol_rvol": call.get("vol_rvol"),
        "confirm_ts": call["confirm_ts"],
        "confirm_tf": call.get("confirm_tf"),
        "session": call["session"],
        "line_fire_no": fire_no, "sent": True,
        "chat_line": chat_line,
    }
    return row


# ---------------------------------------------------------------- live exits
# v4c's exit contract with v5's own state files: delivered
# calls resolve from evaluated.jsonl rows tagged engine
# "v5_24h" (so v4c's book is invisible here); the stop is a
# completed 15m close beyond the call's STOP LINE (a None
# stop_line means the call was delivered with no stop and
# is never stop-judged); target is a touch (the forming bar
# counts); first trigger wins, stop judged first within a
# completed bar; calls die at the trading day's 20:00 ET
# end. TARGET exits are recorded in exit_emitted_24h.jsonl
# for the scorecard but are NOT returned for delivery —
# only stop exits leave this function as events (Victor,
# 2026-11-21: target hits are logged, never posted).

def _call_key(call):
    return (f"{call['symbol']}|{call['level']:.2f}|{call['side']}|"
            f"{call['confirm_ts']}")


def load_delivered_calls_24h(day):
    calls = {}
    try:
        with open(EVALUATED_PATH) as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if r.get("verdict") != "sent" \
                        or r.get("kind") != "level_hold" \
                        or r.get("engine") != "v5_24h":
                    continue
                cts = r.get("confirm_ts")
                if not cts:
                    continue
                if trading_day(cts) != day:
                    continue
                call = {"symbol": r["symbol"], "side": r["side"],
                        "level": r["level"],
                        "entry_close": r.get("entry_close"),
                        "target": r.get("target"),
                        "stop_line": r.get("stop_line"),
                        "confirm_ts": cts}
                calls[_call_key(call)] = call
    except Exception:
        pass
    return calls


def _load_exit_state():
    try:
        with open(EXIT_STATE_PATH_24H) as f:
            return json.load(f)
    except Exception:
        return {"closed": {}}


def _save_exit_state(state):
    tmp = EXIT_STATE_PATH_24H + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, EXIT_STATE_PATH_24H)


def detect_exits_24h(now_ts, record=True):
    """Stop-exit events for today's delivered v5 calls.
    Target exits are recorded (state + ledger) when
    `record` is set but never returned."""
    day = trading_day(now_ts)
    _ds, day_end = day_bounds(day)
    calls = load_delivered_calls_24h(day)
    if not calls:
        return []
    state = _load_exit_state()
    closed = state.setdefault("closed", {})
    bars_by_sym = {}
    exits = []
    recorded = []
    for key, call in sorted(calls.items(),
                            key=lambda kv: kv[1]["confirm_ts"]):
        if key in closed:
            continue
        sym = call["symbol"]
        if sym not in bars_by_sym:
            try:
                data = load_symbol(sym, intraday_range="7d")
                bars_by_sym[sym] = data["bars15"]
            except Exception:
                bars_by_sym[sym] = []
        stop_ref = call["stop_line"] if "stop_line" in call \
            else call["level"]
        target = call.get("target")
        hit = None
        for b in bars_by_sym[sym]:
            if b["t"] < _ds or b["t"] >= day_end:
                continue
            if b["t"] + 900 <= call["confirm_ts"]:
                continue
            completed = b["t"] + 900 <= now_ts
            if call["side"] == "RESISTANCE":  # short
                if stop_ref is not None and completed \
                        and b["c"] > stop_ref:
                    hit = ("stopped", b, b["c"])
                elif target is not None and b["l"] <= target:
                    hit = ("target", b, target)
            else:  # SUPPORT — long
                if stop_ref is not None and completed \
                        and b["c"] < stop_ref:
                    hit = ("stopped", b, b["c"])
                elif target is not None and b["h"] >= target:
                    hit = ("target", b, target)
            if hit:
                break
        if not hit:
            continue
        kind, b, price = hit
        exit_ts = min(b["t"] + 900, now_ts) if kind == "target" \
            else b["t"] + 900
        ev = {"symbol": sym, "kind": "level_exit",
              "engine": "v5_24h",
              "side": call["side"], "level": call["level"],
              "entry_close": call.get("entry_close"),
              "entry_confirm_ts": call["confirm_ts"],
              "target": target, "stop_line": stop_ref,
              "exit_kind": kind, "exit_price": price,
              "exit_ts": exit_ts,
              "exit_time_ct": datetime.fromtimestamp(
                  exit_ts, CT).strftime("%I:%M %p CT")}
        recorded.append(ev)
        if kind == "stopped":
            exits.append(ev)
        if record:
            closed[key] = {"exit_kind": kind, "exit_ts": exit_ts,
                           "emitted_ts": now_ts}
    if record and recorded:
        _save_exit_state(state)
        with open(EXIT_EMITTED_PATH_24H, "a") as f:
            for ev in recorded:
                f.write(json.dumps(ev) + "\n")
        with open(SHARED_EXIT_EMITTED_PATH, "a") as f:
            for ev in recorded:
                f.write(json.dumps(ev) + "\n")
    return exits


# ---------------------------------------------------------------- lines file

def lines_payload(day, data, asof_ts=None):
    candles = grid_4h_candles(data["bars15"])
    conf = confluence_lines(data["daily"], day)
    _entry, all_lines, _last = line_map(
        candles, conf, asof_ts or day_bounds(day)[1])
    return [{"value": round(ln["value"], 2), "label": ln["label"],
             "entry_ok": ln["entry_ok"], "body": ln["body"]}
            for ln in all_lines]


def write_lines_file(day, per_sym_lines):
    path = os.path.join(BASE, f"lines5-{day.isoformat()}.json")
    with open(path, "w") as f:
        json.dump(per_sym_lines, f, indent=1)
    return path


def lines_cmd(date_str, syms):
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    out = {}
    for sym in syms:
        try:
            data = load_symbol(sym)
        except Exception as e:  # noqa: BLE001
            log(f"lines failed {sym}: {type(e).__name__}: {e}")
            continue
        out[sym] = {"levels": lines_payload(day, data)}
    path = write_lines_file(day, out)
    print(json.dumps(out, indent=1))
    log(f"v5 line list saved to {path}")


# ---------------------------------------------------------------- live hook
# Mirrors v4c's hook_run step for step, with v5's window
# and state: weekend-gap gate -> exit scan over v5's
# evaluated rows -> detect (completed bars only) ->
# freshness filter -> dedupe against hold_state_24h.json
# -> SENT mirror to hold_emitted_24h.jsonl -> combined
# JSON (fresh entries + stop exits) on stdout. Diagnostics
# to stderr. Dry runs mutate no state or ledger; the day's
# lines5 file is refreshed either way.

def _in_window_24h(now_ts):
    """The 24h engine's gate: a trading day is live from
    Sunday 19:55 ET (the 20:00 reopen) through Friday
    20:05 ET. Saturday and the Fri->Sun gap return []."""
    dt = datetime.fromtimestamp(now_ts, ET)
    wd = dt.weekday()  # Mon=0 .. Sun=6
    mins = dt.hour * 60 + dt.minute
    if wd == 5:
        return False
    if wd == 6 and mins < 19 * 60 + 55:
        return False
    if wd == 4 and mins >= 20 * 60 + 5:
        return False
    return True


def _completed_only(data, now_ts):
    return {
        "bars15": [b for b in data["bars15"]
                   if b["t"] + 900 <= now_ts],
        "daily": data["daily"],
        "alpaca_bars": data.get("alpaca_bars", 0),
    }


def _load_hook_state():
    try:
        with open(STATE_PATH_24H) as f:
            return json.load(f)
    except Exception:
        return {"emitted": {}}


def _save_hook_state(state):
    tmp = STATE_PATH_24H + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH_24H)


def hook_run(syms, dry=False, now_ts=None):
    """One live tick. Returns the combined event list (fresh
    entry candidates + stop-exit events) the hook prints
    as JSON."""
    now_ts = now_ts or int(time.time())
    if not _in_window_24h(now_ts):
        return []
    today = trading_day(now_ts)
    exit_events = []
    try:
        exit_events = detect_exits_24h(now_ts, record=not dry)
    except Exception as e:  # noqa: BLE001
        print(f"exit scan failed: {type(e).__name__}: {e}",
              file=sys.stderr)

    def _detect_one(sym):
        data = load_symbol(sym, intraday_range="7d")
        fdata = _completed_only(data, now_ts)
        cands, lines, _meta = detect_24h(sym, fdata, today)
        delivered, _supp = simulate_24h(sym, cands, fdata,
                                        today)
        return sym, delivered, lines

    def _safe_detect(sym):
        try:
            return _detect_one(sym)
        except Exception as e:  # noqa: BLE001
            print(f"detect failed {sym}: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return sym, [], []

    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for r in pool.map(_safe_detect, syms):
            results.append(r)
    per_sym = {}
    calls = []
    for sym, delivered, lines in results:
        per_sym[sym] = {"levels": [
            {"value": round(ln["value"], 2), "label": ln["label"],
             "entry_ok": ln["entry_ok"], "body": ln["body"]}
            for ln in lines]}
        calls.extend(delivered)
    try:
        write_lines_file(today, per_sym)
    except Exception as e:  # noqa: BLE001
        print(f"lines write failed: {type(e).__name__}: {e}",
              file=sys.stderr)
    calls.sort(key=lambda c: c["confirm_ts"])
    fire_counts = {}
    rows = []
    for call in calls:
        k = (call["symbol"], round(call["level"], 2))
        fire_counts[k] = fire_counts.get(k, 0) + 1
        rows.append(to_live_row(call, fire_counts[k]))
    state = _load_hook_state()
    emitted = state.setdefault("emitted", {})
    fresh = []
    for row in rows:
        if now_ts - row["confirm_ts"] > FRESH_SECS:
            continue
        key = (f"{row['symbol']}|{row['level']:.2f}|{row['side']}|"
               f"{row['confirm_ts']}")
        if key in emitted:
            continue
        emitted[key] = row
        fresh.append(row)
    for key in list(emitted):
        if now_ts - emitted[key]["confirm_ts"] > 3 * 86400:
            del emitted[key]
    if not dry:
        if fresh:
            with open(EMITTED_PATH_24H, "a") as f:
                for row in fresh:
                    f.write(json.dumps(row) + "\n")
            # The delivery contract: sent rows land in the
            # shared evaluated.jsonl with verdict "sent" —
            # telegram_sender.py reads its entries there,
            # and v5's own exit loader resolves open calls
            # from the same rows (engine-tagged, so v4c's
            # book stays invisible).
            with open(EVALUATED_PATH, "a") as f:
                for row in fresh:
                    f.write(json.dumps(
                        {**row, "verdict": "sent"}) + "\n")
        _save_hook_state(state)
        tmp = LAST_RUN_PATH_24H + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": now_ts, "mode": "hold5_24h",
                       "events": len(fresh) + len(exit_events)}, f)
        os.replace(tmp, LAST_RUN_PATH_24H)
    return fresh + exit_events


# ---------------------------------------------------------------- replay

def replay_cmd(date_str, syms):
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = dict()
        failures = []
        for sym, data, err in pool.map(load_symbol_retry, syms):
            if data is None:
                failures.append({"symbol": sym, "error": err})
            else:
                loaded[sym] = data
    out = {"date": date_str,
           "universe": syms,
           "failures": failures,
           "lines": {}, "delivered_entries": [],
           "suppressed": [],
           "candidates_total": 0, "notes": {}}
    for sym in syms:
        data = loaded.get(sym)
        if data is None:
            continue
        try:
            cands, lines, meta = detect_24h(sym, data, day)
            delivered, suppressed = simulate_24h(
                sym, cands, data, day)
        except Exception as e:  # noqa: BLE001
            failures.append({"symbol": sym,
                             "error": f"detect: {type(e).__name__}: {e}"})
            continue
        out["lines"][sym] = [
            {"label": ln["label"], "value": round(ln["value"], 2),
             "entry_ok": ln["entry_ok"], "body": ln["body"]}
            for ln in lines]
        out["notes"][sym] = {"alpaca_bars": meta["alpaca_bars"]}
        out["delivered_entries"].extend(delivered)
        out["suppressed"].extend(suppressed)
        out["candidates_total"] += len(cands)
    out["delivered_entries"].sort(key=lambda c: c["confirm_ts"])
    out["suppressed"].sort(key=lambda c: c["confirm_ts"])
    path = os.path.join(OUT_DIR, f"{OUT_PREFIX}-replay-{date_str}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)

    def tally(calls):
        t = sum(1 for c in calls if c["exit"]["exit_kind"] == "target")
        s = sum(1 for c in calls if c["exit"]["exit_kind"] == "stopped")
        o = sum(1 for c in calls if c["exit"]["exit_kind"] == "open")
        return t, s, o
    t, s, o = tally(out["delivered_entries"])
    log(f"{date_str}: candidates {out['candidates_total']} | "
        f"entries {len(out['delivered_entries'])} "
        f"(target {t}, stopped {s}, open {o}) | suppressed "
        f"{len(out['suppressed'])} | failures {len(failures)}")
    log(f"wrote {path}")


def replay2json_cmd(date_str, syms):
    """Full-day detect + delivery: prints one live-schema
    JSON row per candidate — delivered rows with sent=true,
    suppressed rows with sent=false and their drop_reason."""
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = {sym: data for sym, data, _err
                  in pool.map(load_symbol_retry, syms)
                  if data is not None}
    rows = []
    for sym in syms:
        data = loaded.get(sym)
        if data is None:
            continue
        try:
            cands, _l, _m = detect_24h(sym, data, day)
            delivered, suppressed = simulate_24h(
                sym, cands, data, day)
        except Exception as e:  # noqa: BLE001
            log(f"replay2json failed {sym}: "
                f"{type(e).__name__}: {e}")
            continue
        counts = {}
        for call in sorted(delivered,
                           key=lambda c: c["confirm_ts"]):
            k = round(call["level"], 2)
            counts[k] = counts.get(k, 0) + 1
            rows.append(to_live_row(call, counts[k]))
        for cand in suppressed:
            row = to_live_row(
                cand, counts.get(round(cand["level"], 2), 0) + 1)
            row["sent"] = False
            row["drop_reason"] = cand.get("drop_reason") or ""
            rows.append(row)
    rows.sort(key=lambda r: r["confirm_ts"])
    for row in rows:
        print(json.dumps(row))


# ---------------------------------------------------------------- main

def main():
    args = sys.argv[1:]
    if "--hook" in args:
        syms = [a for a in args
                if not a.startswith("--")] or live_universe()
        print(json.dumps(hook_run(syms, dry="--dry" in args)))
        return
    if "--dry-run" in args:
        syms = [a for a in args
                if not a.startswith("--")] or live_universe()
        print(json.dumps(hook_run(syms, dry=True)))
        return
    if args and args[0] == "--lines":
        day = datetime.strptime(args[1], "%Y-%m-%d").date()
        lines_cmd(args[1], args[2:] or live_universe(day))
        return
    if args and args[0] == "--replay2json":
        day = datetime.strptime(args[1], "%Y-%m-%d").date()
        replay2json_cmd(args[1], args[2:] or live_universe(day))
        return
    if args and args[0] == "--replay":
        date_str = args[1]
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
        syms = args[2:] or UNIVERSE_BY_DATE.get(date_str) \
            or live_universe(day)
        replay_cmd(date_str, syms)
        return
    print(__doc__)
    return


if __name__ == "__main__":
    main()
