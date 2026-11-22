#!/usr/bin/env python3
"""ETH-USD all-week watch -- body-open reclaim + break system
(Victor, 2026-11-20; ETH only since 2026-11-21; runs every
day since 2026-11-22 -- ETH trades 24/7 and never closes).

Weekend test bed for the reclaim pattern Victor taught on
2026-11-20: sometimes price never wicks the prior 4H candle's
high/low, so the reclaim line set also includes BODY OPENS --
"current 4h wick passing through previous weekly or body"
qualifies. This watch tests that pattern on the two 24/7
crypto names while the equity market is closed. It does NOT
touch the live v4c equity system.

Rules (the simple version, on purpose -- collect live data
first, perfect later, per Victor's 2026-11-18 direction):
  - ACTIVE LINES: while a 4H candle is forming (24h grid, ET
    starts 00/04/08/12/16/20), the lines are the PRIOR
    completed 4H candle's OPEN ("4H body open"), HIGH and
    LOW, plus the PRIOR completed WEEKLY candle's OPEN
    ("Weekly body open"), HIGH and LOW. The body open's
    reclaim/loss confirms on 15m closes; the extremes
    confirm on 10m closes. The prior candle's CLOSE was
    tried as a line on 2026-11-22 and parked the same
    morning (Victor: quality signals only — noise kills
    trust): close-line reclaims are detected in SHADOW
    (15m closes, logged, never delivered) so the data can
    later say whether the close earns a live place next
    to the open. Lines within 0.1%
    of each other merge into one line with a stacked label.
    ENTRY SCOPE (Victor, 2026-11-22 05:05, superseding the
    wider test scope): entries use strictly the last 4H
    candle's lines -- a line that is, or stacks on, a
    prior-4H line. The weekly lines stay on the map as
    information: they name targets and stops (the pair
    geometry) and print as confluence notices when they
    stack on an entry line, but a fire never originates
    at a weekly-only line. The prior candle is the entry
    because that is where the risk/reward is.
    Every fire is tagged with its line's label, so the
    weekend scorecard can split outcomes by line source --
    that data answers Victor's still-open pins (body open
    only vs body open + extremes; which weekly values).
  - FIRE (reclaim only): price wicks through an active line
    and a completed 10m bar closes back across it (Victor,
    2026-11-21: the 5m close whipsaws on crypto; 30m was
    tried next and proved too wide -- the move runs ahead
    before the close confirms -- so 10m; equities keep
    their own confirms). Entry is the line itself; the
    confirming close is only proof.
    The test must approach from the reclaim side: a line is
    armed only once a completed 10m close sits on the
    reclaim side (price residing on the far side since the
    window opened does not arm it -- a later close through
    is a break, not a reclaim). If one 10m close-back
    crosses several lines, only the deepest crossed line
    fires (one move, one call).
  - FIRE (break): a completed 10m bar opens on one side of
    an active line and closes on the other -- price accepts
    through the line (Victor, 2026-11-21 evening: "a break
    on either direction is a good trade"; the reclaim-only
    scope missed the break of the prior 4H low entirely).
    Entry is the line itself -- the entry IS the break:
    on the confirming close the trade is taken, no
    retest wait (Victor: "we dont even wait we buy the
    break"). Volume is what makes a break worth taking;
    it rides on the card as the grade,
    never a gate. A break is the ladder continuing:
    a same-side break at a fresh line fires even while
    an earlier same-side call stands (the rejection at
    the high, then the break of the low under it, are
    two trades). The freshness and
    one-call-per-line-per-side rules still bind it. If
    one bar closes through several lines, only the
    first line crossed fires; the next line is its own
    later fire.
    SCOPE (Victor, 2026-11-22, after a body-open break and
    a Weekly-LOW break fired overnight that he did not
    expect): breaks judge ONLY the prior 4H candle's
    high/low (a stacked label carrying one counts). The
    weekly lines and the body-open lines are RECLAIM
    lines -- a close through them is not a break fire.
    The new candle is traded against the prior candle,
    not against the whole map. (The body open is itself a
    line of the prior candle, so it stays a reclaim entry
    line under the 05:05 entry scope; the weekly lines
    became information-only at the same time.)
  - GEOMETRY: stop = nearest line beyond the entry, target
    = nearest line in the trade direction, from the last
    5 days of completed 4H candles (open/high/low each)
    plus the weekly lines. No line beyond the entry ->
    the call still delivers with "stop: none set" and
    exits on its target only (Victor, 2026-11-20).
  - EXITS: target = a touch; stop = a completed 15m close
    beyond the stop line; within one completed bar the stop
    is judged first; first trigger wins; calls die at CT
    midnight (the log is per CT day).
  - BRAKES REMOVED (Victor, 2026-11-22: "too many
    unnecessary logic killing these signals" -- the
    zone rule, the side-state rule and the chop set are
    GONE from this system). What remains: one call per
    line per side per day (the seen-key dedup), the
    same-bar break collapse, and the freshness window
    below. A reclaim or a break at an active line
    fires; the flip is simply the next fire. The
    scorecard, not a pre-filter, judges what was noise.
  - SAME-MOVE WICK: the wick through the line and the 5m
    close back across it must be the same move -- the wick
    expires 15 minutes after the last bar that wicked
    through, so an old wick can never arm a later close.
  - A candidate is deliverable only while fresh (confirmed
    within FRESH_SECS); older ones are logged skipped_stale.
  - Shorts are allowed on both names (the index-only shorts
    rule is an equity rule about sector duplication).
  - Volume prints on the card as context only, never a
    gate: today's cumulative volume vs the mean cumulative
    at the same clock time over the prior 10 CT days.

Like eth_weekend_watch.py, this script DETECTS, FORMATS and
LOGS state-first into crypto-weekend-<CT date>.jsonl, then
prints JSON actions; the caller (the eth-weekend-signal-
watch cron) posts the cards. A failed post can therefore
never double-fire.

    python3 crypto_weekend_watch.py --scan      # JSON out
    python3 crypto_weekend_watch.py --dry-run   # writes nothing
    python3 crypto_weekend_watch.py --replay YYYY-MM-DD
        # roll one CT day: every fire + simulated exit,
        # nothing logged (scorecard / verification)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
BASE = os.path.dirname(os.path.abspath(__file__))
SYMS = ["ETH-USD"]   # ETH only (Victor, 2026-11-21: focus the
# perfection phase on SPY/QQQ/SMH/IWM + ETH only; BTC dropped)
SUNDAY_SYMS = ["NQ=F"]   # Nasdaq futures join on Sundays
# (Victor, 2026-11-22: "lets add NQ! to our list for
# sunday" -- futures reopen Sunday 17:00 CT)


def days_syms(weekday):
    """Symbols scanned on a CT weekday (Mon=0 .. Sun=6):
    ETH every day (it never closes), NQ futures Sundays."""
    syms = list(SYMS)
    if weekday == 6:
        syms += SUNDAY_SYMS
    return syms
FRESH_SECS = 45 * 60
MERGE_PCT = 0.005          # lines within 0.5% are one zone
ZONE_PCT = 0.005           # one delivered call per zone/day
EPISODE_SECS = 10 * 60     # wick lives its 10m bar + one more
CONFIRM_SECS = 10 * 60     # reclaim confirms on a 10m close
GEO_DAYS = 2               # completed-4H geometry lookback


# ------------------------------------------------------------------ data
def fetch(sym, rng, interval):
    """Yahoo bars as {t,o,h,l,c,v}. Intraday extremes get the
    engine's corrupt-print clamp (1% beyond the bar's own
    open/close envelope); daily/weekly bars are never
    clamped (the 2026-11-18 daily-clamp lesson)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{sym}?range={rng}&interval={interval}"
           f"&includePrePost=true")
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    r = d["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c = (q["open"][i], q["high"][i], q["low"][i],
                      q["close"][i])
        if o is None or c is None:
            continue
        if interval not in ("1d", "1wk"):
            lo_e, hi_e = min(o, c), max(o, c)
            h = min(h, hi_e * 1.01)
            l = max(l, lo_e * 0.99)
        bars.append({"t": t, "o": o, "h": h, "l": l, "c": c,
                     "v": q["volume"][i] or 0})
    return bars


def build_4h(bars15):
    """Aggregate 15m bars into 4H candles on the uniform 24h
    grid (ET starts 00/04/08/12/16/20). Returns candles as
    {start (ET datetime), o,h,l,c} sorted by start."""
    def cstart(dt):
        return dt.replace(hour=(dt.hour // 4) * 4, minute=0,
                          second=0, microsecond=0)
    cand = {}
    for b in bars15:
        dt = datetime.fromtimestamp(b["t"], ET)
        k = cstart(dt)
        if k not in cand:
            cand[k] = {"start": k, "o": b["o"], "h": b["h"],
                       "l": b["l"], "c": b["c"]}
        else:
            cand[k]["h"] = max(cand[k]["h"], b["h"])
            cand[k]["l"] = min(cand[k]["l"], b["l"])
            cand[k]["c"] = b["c"]
    return [cand[k] for k in sorted(cand)]


def prior_weekly(weekly_bars, now_ts):
    """The most recent COMPLETED weekly candle (o/h/l/c)."""
    done = None
    for b in weekly_bars:
        if b["t"] + 7 * 86400 <= now_ts:
            done = b
    return done


def active_lines(candles, weekly, now_ts):
    """(lines, activation_ts): the prior completed 4H
    candle's close/high/low + the prior weekly candle's
    open/high/low, near-duplicates merged with stacked
    labels. Lines activate when the 4H candle
    completes and stay active until the next one
    completes."""
    completed = [c for c in candles
                 if c["start"].timestamp() + 4 * 3600 <= now_ts]
    if not completed or weekly is None:
        return [], None
    last = completed[-1]
    raw = [(last["o"], "4H body open"),
           (last["h"], "4H HIGH"),
           (last["l"], "4H LOW"),
           (weekly["o"], "Weekly body open"),
           (weekly["h"], "Weekly HIGH"),
           (weekly["l"], "Weekly LOW")]
    lines = []
    for value, label in sorted(raw):
        if lines and abs(value - lines[-1]["value"]) \
                <= MERGE_PCT * value:
            if label not in lines[-1]["label"]:
                lines[-1]["label"] += " + " + label
        else:
            lines.append({"value": value, "label": label})
    return lines, int(last["start"].timestamp() + 4 * 3600)


def range_lines(candles, now_ts):
    """(lines, activation_ts): the MOTHER candle — an older
    completed 4H candle whose high and low were never
    broken, with every candle since built inside her
    (Victor, 2026-11-22: the range is important context —
    entries inside it are sold quicker, at the frame's
    lines, and a break of the range may mean a bigger
    move, so her edges are entry lines too). Walk back
    over the last 10 completed candles: an older candle
    that fully contains every candle after it is the
    mother. Her HIGH / LOW are the RANGE lines; they
    activate when her first inside candle completed and
    stay until a completed candle's extremes escape her
    (then the walk finds no mother). Mirrors the
    prior-4h-lines Pine walk (v2026.11.22.20)."""
    completed = [c for c in candles
                 if c["start"].timestamp() + 4 * 3600 <= now_ts]
    if len(completed) < 2:
        return [], None
    win = completed[-10:]
    acc_hi = win[-1]["h"]
    acc_lo = win[-1]["l"]
    mother = None
    for i in range(len(win) - 2, -1, -1):
        c = win[i]
        if c["h"] >= acc_hi and c["l"] <= acc_lo:
            mother = i
            acc_hi = c["h"]
            acc_lo = c["l"]
        else:
            break
    if mother is None:
        return [], None
    m = win[mother]
    act = int(win[mother + 1]["start"].timestamp()
              + 4 * 3600)
    lines = [{"value": m["h"], "label": "RANGE HIGH"},
             {"value": m["l"], "label": "RANGE LOW"}]
    return lines, act


def geometry_values(candles, weekly, now_ts):
    """Stop/target map: opens/highs/lows of completed 4H
    candles from the last GEO_DAYS days + the weekly
    lines. Values only (geometry lines carry no labels)."""
    vals = set()
    cutoff = now_ts - GEO_DAYS * 86400
    for c in candles:
        st = c["start"].timestamp()
        if st + 4 * 3600 <= now_ts and st >= cutoff:
            vals.update((round(c["o"], 2),
                         round(c["h"], 2), round(c["l"], 2)))
    if weekly is not None:
        vals.update((round(weekly["o"], 2), round(weekly["h"], 2),
                     round(weekly["l"], 2)))
    return sorted(vals)


def pair_geometry(vals, value, side):
    """(stop, target): nearest geometry value beyond the
    entry (stop) / in the trade direction (target),
    skipping anything within 0.05% of the entry."""
    stop = target = None
    for v in vals:
        if abs(v - value) <= 0.0005 * value:
            continue
        if side == "LONG":
            if v < value and (stop is None or v > stop):
                stop = v
            if v > value and (target is None or v < target):
                target = v
        else:
            if v > value and (stop is None or v < stop):
                stop = v
            if v < value and (target is None or v > target):
                target = v
    return stop, target


# ------------------------------------------------------------------ detect
def build_30m(bars5, secs=None):
    """Aggregate 5m bars into clock-aligned bars of `secs`
    (default CONFIRM_SECS — the name is historical)."""
    secs = secs or CONFIRM_SECS
    out = {}
    for b in bars5:
        start = b["t"] - (b["t"] % secs)
        cur = out.get(start)
        if cur is None:
            out[start] = {"t": start, "o": b["o"],
                          "h": b["h"], "l": b["l"],
                          "c": b["c"], "v": b["v"]}
        else:
            cur["h"] = max(cur["h"], b["h"])
            cur["l"] = min(cur["l"], b["l"])
            cur["c"] = b["c"]
            cur["v"] += b["v"]
    return [out[k] for k in sorted(out)]


def detect_reclaims(bars30, lines, activation_ts, now_ts,
                    confirm_secs=None, episode_secs=None,
                    only_open=False):
    """Reclaim fires at the prior 4H candle's lines: armed
    once a completed close sits on the reclaim side, then
    a wick through the line and a completed bar closing
    back across it. Returns fire dicts {level, label, side,
    confirm_ts, test_extreme, entry_close, confirm_secs}.
    Per confirm bar only the deepest crossed line fires.
    The extremes (high/low) confirm on 10m closes; the
    BODY OPEN line confirms on 15m closes (Victor,
    2026-11-22 10:05: "a reclaim or loss base on 15mins")
    — call with only_open=True, confirm_secs=900 for that
    pass, and the default pass skips pure open lines.
    ENTRY SCOPE (Victor, 2026-11-22 05:05): entries use
    strictly the last 4H candle's lines -- a line that IS
    or stacks on a prior-4H line (high, low, body open).
    The CLOSE was tried the morning of 2026-11-22 and
    parked the same morning: quality only — it comes back
    only if the open-line data says the noise allows it.
    Weekly lines are information only: targets, stops and
    confluence notices on the card, never entry lines --
    the prior candle is where the risk/reward is.
    RANGE lines (added 2026-11-22, Victor): the mother
    candle's unbroken HIGH / LOW are entry lines on the
    same terms as the 4H extremes — they arrive in their
    own list with their own activation (see range_lines),
    never in the frame list this filter usually sees."""
    confirm_secs = confirm_secs or CONFIRM_SECS
    episode_secs = episode_secs or EPISODE_SECS

    def _is_open_line(label):
        return "body open" in label and "HIGH" not in label \
            and "LOW" not in label

    if only_open:
        lines = [ln for ln in lines if "4H" in ln["label"]
                 and _is_open_line(ln["label"])]
    else:
        lines = [ln for ln in lines
                 if ("4H" in ln["label"]
                     or "RANGE" in ln["label"])
                 and not _is_open_line(ln["label"])]
    done = [b for b in bars30
            if b["t"] >= activation_ts
            and b["t"] + confirm_secs <= now_ts]
    prev = [b for b in bars30
            if b["t"] + confirm_secs <= activation_ts]
    prev_close = prev[-1]["c"] if prev else None
    fires = []
    for ln in lines:
        lv = ln["value"]
        for side in ("LONG", "SHORT"):
            # reclaim side: above the line for LONG, below
            # for SHORT. Armed = the last completed close
            # (before the window, then bar by bar) sits on
            # the reclaim side.
            if prev_close is None:
                armed = True
            elif side == "LONG":
                armed = prev_close > lv
            else:
                armed = prev_close < lv
            wicked = False
            extreme = None
            last_wick_t = None
            for b in done:
                if wicked and last_wick_t is not None \
                        and b["t"] - last_wick_t > episode_secs:
                    wicked = False
                    extreme = None
                    last_wick_t = None
                if side == "LONG":
                    if not armed:
                        if b["c"] > lv:
                            armed = True
                        continue
                    if b["l"] < lv:
                        wicked = True
                        last_wick_t = b["t"]
                        extreme = b["l"] if extreme is None \
                            else min(extreme, b["l"])
                    if wicked and b["c"] > lv:
                        fires.append({
                            "level": lv, "label": ln["label"],
                            "side": side, "kind": "reclaim",
                            "confirm_ts": b["t"] + confirm_secs,
                            "confirm_secs": confirm_secs,
                            "test_extreme": extreme,
                            "entry_close": b["c"]})
                        break
                else:
                    if not armed:
                        if b["c"] < lv:
                            armed = True
                        continue
                    if b["h"] > lv:
                        wicked = True
                        last_wick_t = b["t"]
                        extreme = b["h"] if extreme is None \
                            else max(extreme, b["h"])
                    if wicked and b["c"] < lv:
                        fires.append({
                            "level": lv, "label": ln["label"],
                            "side": side, "kind": "reclaim",
                            "confirm_ts": b["t"] + confirm_secs,
                            "confirm_secs": confirm_secs,
                            "test_extreme": extreme,
                            "entry_close": b["c"]})
                        break
    by_confirm = {}
    for f in fires:
        by_confirm.setdefault(f["confirm_ts"], []).append(f)
    out = []
    for ts in sorted(by_confirm):
        group = by_confirm[ts]
        longs = [f for f in group if f["side"] == "LONG"]
        shorts = [f for f in group if f["side"] == "SHORT"]
        if longs:
            out.append(min(longs, key=lambda f: f["level"]))
        if shorts:
            out.append(max(shorts, key=lambda f: f["level"]))
    return out


def detect_breaks(bars30, lines, activation_ts, now_ts):
    """Break fires at the active lines (Victor, 2026-11-21):
    a completed 10m bar opens on one side of a line and
    closes on the other -- acceptance through the line.
    Entry is the line itself. Returns fire dicts like
    detect_reclaims, with kind 'break' and test_extreme =
    the confirming bar's far extreme in the break
    direction. If one bar closes through several lines,
    only the first line crossed fires (the lowest crossed
    going up, the highest going down); the next line is
    its own later fire -- the ladder. SCOPE (Victor,
    2026-11-22): only the prior 4H candle's high/low are
    break lines (a stacked label carrying one counts);
    weekly and body-open lines are reclaim-only. RANGE
    HIGH / LOW (the mother candle's unbroken edges) are
    break lines too (Victor, 2026-11-22: a break of the
    range may mean a bigger move)."""
    lines = [ln for ln in lines
             if "4H HIGH" in ln["label"]
             or "4H LOW" in ln["label"]
             or "RANGE HIGH" in ln["label"]
             or "RANGE LOW" in ln["label"]]
    done = [b for b in bars30
            if b["t"] >= activation_ts
            and b["t"] + CONFIRM_SECS <= now_ts]
    fires = []
    for b in done:
        up = [ln for ln in lines if b["o"] <= ln["value"] < b["c"]]
        dn = [ln for ln in lines if b["o"] >= ln["value"] > b["c"]]
        if up:
            ln = min(up, key=lambda x: x["value"])
            fires.append({
                "level": ln["value"], "label": ln["label"],
                "side": "LONG", "kind": "break",
                "confirm_ts": b["t"] + CONFIRM_SECS,
                "test_extreme": b["h"],
                "entry_close": b["c"]})
        if dn:
            ln = max(dn, key=lambda x: x["value"])
            fires.append({
                "level": ln["value"], "label": ln["label"],
                "side": "SHORT", "kind": "break",
                "confirm_ts": b["t"] + CONFIRM_SECS,
                "test_extreme": b["l"],
                "entry_close": b["c"]})
    return fires


def simulate_exit(call, bars15, end_ts):
    """First trigger wins on the 15m tape after the confirm:
    target = a touch; stop = a completed 15m close beyond
    the stop line, judged before the target within the same
    completed bar. No stop line -> target only. Returns
    {exit_kind, exit_price, exit_ts} or None while open."""
    lv_side = call["side"]
    for b in bars15:
        if b["t"] + 900 <= call["confirm_ts"]:
            continue
        if b["t"] > end_ts:
            break
        completed = b["t"] + 900 <= end_ts
        if completed and call["stop"] is not None:
            if lv_side == "LONG" and b["c"] < call["stop"]:
                return {"exit_kind": "stopped",
                        "exit_price": b["c"],
                        "exit_ts": b["t"] + 900}
            if lv_side == "SHORT" and b["c"] > call["stop"]:
                return {"exit_kind": "stopped",
                        "exit_price": b["c"],
                        "exit_ts": b["t"] + 900}
        if call["target"] is not None:
            if lv_side == "LONG" and b["h"] >= call["target"]:
                return {"exit_kind": "target",
                        "exit_price": call["target"],
                        "exit_ts": b["t"] + 900}
            if lv_side == "SHORT" and b["l"] <= call["target"]:
                return {"exit_kind": "target",
                        "exit_price": call["target"],
                        "exit_ts": b["t"] + 900}
    return None


def stop_crossed(side, stop, bars15, from_ts, to_ts):
    """True when a completed 15m bar ending in (from_ts,
    to_ts] closed beyond `stop` -- a delivered call's
    invalidation. No stop line -> never crossed."""
    if stop is None:
        return False
    for b in bars15:
        end = b["t"] + 900
        if end <= from_ts:
            continue
        if end > to_ts:
            break
        if side == "LONG" and b["c"] < stop:
            return True
        if side == "SHORT" and b["c"] > stop:
            return True
    return False


def side_blocked(delivered, side, confirm_ts, bars15):
    """Victor's side-state rule (2026-11-21): the symbol's
    side is set by its latest delivered call at or before
    the candidate. A same-side candidate is blocked while
    that call stands -- freed only by a completed 15m
    close beyond its stop line before the candidate. A
    target hit never frees the side."""
    prior = [r for r in delivered
             if r["confirm_ts"] <= confirm_ts]
    if not prior:
        return False
    last = max(prior, key=lambda r: r["confirm_ts"])
    if last["side"] != side:
        return False
    return not stop_crossed(last["side"], last.get("stop"),
                            bars15, last["confirm_ts"],
                            confirm_ts)


def volume_context(bars5, confirm_ts):
    """(rvol, cumulative) for the card's Vol line: today's
    (CT) cumulative 5m volume through the confirm vs the
    mean cumulative at the same clock time over the prior
    10 CT days in the feed. (None, cum) when no baseline."""
    def day_of(b):
        return datetime.fromtimestamp(b["t"], CT).date()

    def cum(d, cutoff_ts):
        return sum(b["v"] for b in bars5
                   if day_of(b) == d and b["t"] + 300 <= cutoff_ts)

    day = datetime.fromtimestamp(confirm_ts, CT).date()
    cum_today = cum(day, confirm_ts)
    if not cum_today:
        return None, 0
    tod = datetime.fromtimestamp(confirm_ts, CT).time()
    prior = sorted({day_of(b) for b in bars5 if day_of(b) < day})
    base = []
    for d in prior[-10:]:
        c = cum(d, datetime.combine(d, tod,
                                    CT).timestamp())
        if c > 0:
            base.append(c)
    rvol = round(cum_today / (sum(base) / len(base)), 2) \
        if base else None
    return rvol, cum_today


# ------------------------------------------------------------------ cards
def grade(fire, rvol):
    """Strong / Average / Weak from the setup and the volume pace
    (Victor, 2026-11-21). Setup: a stacked line (the label carries
    a '+') or a sweep that wicked >= 0.10% past the line is a
    manipulation-grade setup. Volume: >= 2x usual pace confirms the
    move; under 1x is thin. The grade is a label only — it never
    holds a card back."""
    lv = fire["level"]
    sweep_pct = abs(fire["test_extreme"] - lv) / lv * 100.0
    strong_setup = ("+" in fire["label"]) or sweep_pct >= 0.10
    if strong_setup or (rvol is not None and rvol >= 2.0):
        return "Strong"
    if rvol is not None and rvol < 1.0:
        return "Weak"
    return "Average"


def entry_card(sym, fire, stop, target, rvol, cum):
    d = fire["side"]
    stop_word = "below" if d == "LONG" else "above"
    back_word = "above" if d == "LONG" else "below"
    lv = fire["level"]
    line = f"{sym} {d} {lv:.2f} — entry {lv:.2f}"
    if target is not None:
        line += f" · target {target:.2f}"
    if stop is not None:
        line += f" · stop: 15m close {stop_word} {stop:.2f}"
    else:
        line += " · stop: none set"
    if fire.get("kind") == "break":
        line += (f"\nReason: Break at {fire['label']} {lv:.2f} — "
                 f"a 10m bar closed through it at "
                 f"{fire['entry_close']:.2f}")
    else:
        cm = fire.get("confirm_secs", CONFIRM_SECS) // 60
        line += (f"\nReason: Reclaim at {fire['label']} {lv:.2f} — "
                 f"wicked to {fire['test_extreme']:.2f}, then a "
                 f"{cm}m close back {back_word} it")
    line += f"\nGrade: {grade(fire, rvol)}"
    if rvol is not None:
        line += f"\nVol: {rvol:.1f}x usual pace"
    return line


def exit_card(rec, ex):
    d = rec["side"]
    if ex["exit_kind"] == "target":
        return (f"{rec['symbol']} {d} {rec['level']:.2f} — "
                f"target hit {ex['exit_price']:.2f}")
    stop_word = "below" if d == "LONG" else "above"
    return (f"{rec['symbol']} {d} {rec['level']:.2f} — stopped: "
            f"15m close {stop_word} {rec['stop']:.2f} at "
            f"{ex['exit_price']:.2f}")


# ------------------------------------------------------------------ state
def log_path(day_ct):
    return os.path.join(BASE, f"crypto-weekend-{day_ct}.jsonl")


def read_log(path):
    recs = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return recs


def append_log(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def load_symbol(sym):
    bars15 = fetch(sym, "10d", "15m")
    bars5 = fetch(sym, "12d", "5m")
    weekly = fetch(sym, "3mo", "1wk")
    return bars15, bars5, weekly


# ------------------------------------------------------------------ scan
def scan(dry_run=False):
    now = int(time.time())
    today_ct = datetime.fromtimestamp(now, CT).strftime("%Y-%m-%d")
    path = log_path(today_ct)
    recs = read_log(path)
    # A zone-skipped reclaim is NOT final when a break has
    # since delivered at the same level: the reclaim is then
    # the flip -- the failed break is the manipulation -- and
    # the zone check exempts it, so it must be re-judged, not
    # buried by its own skip record (2026-11-22: the ETH
    # rejection at 1720.47 was zone-skipped at 15:19, one
    # minute before the LONG break at the same level
    # confirmed; the break delivered at 15:49 but the skip's
    # seen key kept the short from ever being re-judged).
    brk_levels = {}
    for r in recs:
        if r.get("type") == "signal" and r.get("kind") == "break":
            brk_levels.setdefault(r["symbol"], set()).add(
                round(r["level"], 2))
    seen_keys = set()
    for r in recs:
        if "key" not in r:
            continue
        if r.get("type") == "skipped_zone" and any(
                abs(round(r["level"], 2) - b) <= 0.0005 * b
                for b in brk_levels.get(r["symbol"], set())):
            continue
        seen_keys.add(r["key"])
    exited_keys = {r["for_key"] for r in recs
                   if r.get("type") == "exit"}
    actions = {"date_ct": today_ct, "signals": [], "exits": [],
               "notes": []}

    for sym in days_syms(
            datetime.fromtimestamp(now, CT).weekday()):
        bars15, bars5, weekly_bars = load_symbol(sym)
        candles = build_4h(bars15)
        weekly = prior_weekly(weekly_bars, now)
        lines, activation = active_lines(candles, weekly, now)
        # RANGE lines: the mother candle's unbroken edges.
        # An edge that coincides with a frame line stacks
        # onto its label (the Pine draws one merged line
        # the same way); a distinct edge keeps its own
        # activation — when the range first existed.
        rlines, range_act = range_lines(candles, now)
        range_extra = []
        for rl in rlines:
            hit = None
            for ln in lines:
                # stack onto a frame line only when it is
                # the SAME level (0.1%, the Pine's merge
                # tolerance) — the watcher's 0.5% zone
                # tolerance would swallow the range edge
                # into the frame line and the range break
                # would never get its own fire
                if abs(rl["value"] - ln["value"]) \
                        <= 0.001 * rl["value"]:
                    hit = ln
                    break
            if hit is not None:
                if "RANGE" not in hit["label"]:
                    hit["label"] += " + " + rl["label"]
            else:
                range_extra.append(rl)
        if dry_run:
            pretty = ", ".join(
                f"{ln['label']} {ln['value']:.2f}"
                for ln in lines)
            actions["notes"].append(
                f"{sym} active lines: {pretty or 'none'}")
            if rlines:
                rpretty = ", ".join(
                    f"{ln['label']} {ln['value']:.2f}"
                    for ln in rlines)
                actions["notes"].append(
                    f"{sym} range lines: {rpretty}")
        if not lines:
            continue
        geo = geometry_values(candles, weekly, now)

        # ---- exits for this symbol's open delivered calls
        open_recs = [r for r in recs
                     if r.get("type") == "signal"
                     and r["symbol"] == sym
                     and r["key"] not in exited_keys]
        for r in open_recs:
            ex = simulate_exit(r, bars15, now)
            if ex is None:
                continue
            card = exit_card(r, ex)
            actions["exits"].append({"key": r["key"],
                                     "card": card})
            if not dry_run:
                append_log(path, {
                    "type": "exit", "for_key": r["key"],
                    "exit_kind": ex["exit_kind"],
                    "exit_price": ex["exit_price"],
                    "exit_ts": ex["exit_ts"], "logged_ts": now})
            exited_keys.add(r["key"])

        # ---- new fires at the active lines: reclaims and
        # breaks (Victor, 2026-11-21: breaks were the miss --
        # the reclaim-only scope never evaluated a close
        # through a line)
        delivered = [r for r in recs if r.get("type") == "signal"
                     and r["symbol"] == sym]
        delivered_all = list(delivered)
        delivered_keys = {r["key"] for r in delivered}
        sides_by_level = {}
        for r in delivered:
            sides_by_level.setdefault(round(r["level"], 2),
                                      set()).add(r["side"])
        chop = {lv for lv, ss in sides_by_level.items()
                if len(ss) > 1}
        # zones are spent by RECLAIM deliveries only -- a
        # break does not spend a reclaim zone (parity with
        # the equity sweep; Victor, 2026-11-21/22)
        zones_today = [round(r["level"], 2) for r in delivered
                       if r.get("kind", "reclaim") == "reclaim"]
        break_levels_today = {
            round(r["level"], 2) for r in delivered
            if r.get("kind") == "break"}

        # current window + the previous one, so a fire that
        # confirmed just before a 4H close (between cron
        # runs) is still caught while it is fresh; the
        # seen-key dedup keeps either window from posting
        # the same call twice.
        bars_c = build_30m(bars5)
        bars_o = build_30m(bars5, 900)
        fires = detect_reclaims(bars_c, lines, activation, now)
        fires += detect_reclaims(bars_o, lines, activation, now,
                                 confirm_secs=900, episode_secs=900,
                                 only_open=True)
        fires += detect_breaks(bars_c, lines, activation, now)
        # shadow: the prior candle's CLOSE, 15m closes —
        # logged, never delivered (Victor, 2026-11-22)
        _prev_c = [c for c in candles
                   if c["start"].timestamp() + 4 * 3600 <= now]
        if _prev_c:
            sh_seen = {(round(r["level"], 2), r["side"],
                        r["confirm_ts"]) for r in recs
                       if r.get("type") == "shadow_close"}
            sh = detect_reclaims(
                bars_o,
                [{"value": _prev_c[-1]["c"],
                  "label": "4H CLOSE (shadow)"}],
                activation, now, confirm_secs=900,
                episode_secs=900)
            for f in sh:
                if (round(f["level"], 2), f["side"],
                        f["confirm_ts"]) in sh_seen:
                    continue
                if not dry_run:
                    append_log(path, {
                        "type": "shadow_close", "symbol": sym,
                        "level": f["level"], "side": f["side"],
                        "confirm_ts": f["confirm_ts"],
                        "test_extreme": f["test_extreme"],
                        "entry_close": f["entry_close"],
                        "logged_ts": now})
        prev_lines, prev_act = active_lines(
            candles, weekly, activation - 1)
        if prev_lines and prev_act is not None:
            fires += detect_reclaims(bars_c, prev_lines,
                                     prev_act, activation)
            fires += detect_reclaims(bars_o, prev_lines,
                                     prev_act, activation,
                                     confirm_secs=900,
                                     episode_secs=900,
                                     only_open=True)
            fires += detect_breaks(bars_c, prev_lines,
                                   prev_act, activation)
        # RANGE edges: one continuous window from the
        # range's own activation — they do not roll with
        # the frame, and the seen-key dedup keeps runs
        # from posting the same call twice.
        if range_extra and range_act is not None:
            fires += detect_reclaims(bars_c, range_extra,
                                     range_act, now)
            fires += detect_breaks(bars_c, range_extra,
                                   range_act, now)
        for f in sorted(fires, key=lambda f: f["confirm_ts"]):
            lv_r = round(f["level"], 2)
            key = (f"{today_ct}|{sym}|{lv_r:.2f}|{f['side']}")
            if key in seen_keys or key in delivered_keys:
                continue
            if now - f["confirm_ts"] > FRESH_SECS:
                if not dry_run:
                    append_log(path, {
                        "type": "skipped_stale", "key": key,
                        "symbol": sym, "level": f["level"],
                        "side": f["side"],
                        "confirm_ts": f["confirm_ts"],
                        "logged_ts": now})
                seen_keys.add(key)
                continue
            stop, target = pair_geometry(geo, f["level"],
                                         f["side"])
            rvol, cum = volume_context(bars5, f["confirm_ts"])
            card = entry_card(sym, f, stop, target, rvol, cum)
            actions["signals"].append({
                "key": key, "card": card, "symbol": sym,
                "direction": f["side"], "level": f["level"],
                "target": target})
            rec_new = {
                "type": "signal", "key": key, "symbol": sym,
                "level": f["level"], "label": f["label"],
                "side": f["side"], "kind": f.get("kind", "reclaim"),
                "stop": stop,
                "target": target,
                "confirm_ts": f["confirm_ts"],
                "test_extreme": f["test_extreme"],
                "card": card, "logged_ts": now}
            if not dry_run:
                append_log(path, rec_new)
            delivered_all.append(rec_new)
            delivered_keys.add(key)
            seen_keys.add(key)
            if f.get("kind", "reclaim") == "reclaim":
                zones_today.append(lv_r)
            if f.get("kind") == "break":
                break_levels_today.add(lv_r)
            sides_by_level.setdefault(lv_r, set()).add(f["side"])
            if len(sides_by_level[lv_r]) > 1:
                chop.add(lv_r)

    print(json.dumps(actions, indent=1))


def replay(date_str):
    """Roll one CT day: rebuild each 4H window's active
    lines as they were, list every reclaim fire with its
    pair geometry and simulated exit. Nothing is logged."""
    day = datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=CT)
    day_start = int(day.timestamp())
    day_end = int((day + timedelta(days=1)).timestamp())
    out = {"date_ct": date_str, "fires": []}
    for sym in days_syms(day.weekday()):
        bars15, bars5, weekly_bars = load_symbol(sym)
        candles = build_4h(bars15)
        weekly = prior_weekly(weekly_bars, day_end)
        geo = geometry_values(candles, weekly, day_end)
        zones_seen = []
        break_levels_seen = set()
        delivered_r = []
        starts = sorted({c["start"] for c in candles
                         if day_start - 4 * 3600
                         <= c["start"].timestamp() < day_end})
        for st in starts:
            act = int(st.timestamp() + 4 * 3600)
            if act >= day_end:
                continue
            win_end = min(act + 4 * 3600, day_end)
            # lines as of this window: prior candle + weekly
            lines, _ = active_lines(candles, weekly, act + 1)
            if not lines:
                continue
            bars_c = build_30m(bars5)
            bars_o = build_30m(bars5, 900)
            fires = detect_reclaims(bars_c, lines, act, win_end)
            fires += detect_reclaims(bars_o, lines, act,
                                     win_end, confirm_secs=900,
                                     episode_secs=900,
                                     only_open=True)
            fires += detect_breaks(bars_c, lines, act, win_end)
            for f in sorted(fires,
                            key=lambda f: f["confirm_ts"]):
                if not (day_start <= f["confirm_ts"] < day_end):
                    continue
                lv_r = round(f["level"], 2)
                if f.get("kind") != "break" \
                        and lv_r not in break_levels_seen \
                        and any(
                        abs(lv_r - z) <= ZONE_PCT * z
                        for z in zones_seen):
                    continue
                stop, target = pair_geometry(geo, f["level"],
                                             f["side"])
                if f.get("kind") != "break" and side_blocked(
                        delivered_r, f["side"],
                        f["confirm_ts"], bars15):
                    continue
                if f.get("kind", "reclaim") == "reclaim":
                    zones_seen.append(lv_r)
                if f.get("kind") == "break":
                    break_levels_seen.add(lv_r)
                delivered_r.append({
                    "side": f["side"], "stop": stop,
                    "confirm_ts": f["confirm_ts"]})
                call = {"side": f["side"],
                        "confirm_ts": f["confirm_ts"],
                        "stop": stop, "target": target}
                ex = simulate_exit(call, bars15, day_end)
                out["fires"].append({
                    "symbol": sym, "side": f["side"],
                    "kind": f.get("kind", "reclaim"),
                    "level": round(f["level"], 2),
                    "label": f["label"],
                    "confirm_ct": datetime.fromtimestamp(
                        f["confirm_ts"], CT).strftime("%H:%M"),
                    "wicked_to": round(f["test_extreme"], 2),
                    "stop": stop, "target": target,
                    "exit": (ex["exit_kind"] if ex else "open"),
                    "exit_price": (round(ex["exit_price"], 2)
                                   if ex else None)})
    out["fires"].sort(key=lambda f: (f["confirm_ct"],
                                     f["symbol"]))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    if "--replay" in sys.argv:
        replay(sys.argv[sys.argv.index("--replay") + 1])
    else:
        scan(dry_run="--dry-run" in sys.argv)
