#!/usr/bin/env python3
"""VP node signal watch (Victor, 2026-11-22).

A SEPARATE signal lane alongside the 4H system, built exactly to
Victor's spec: a signal based on ANY volume-profile line — POC,
VAH, VAL and every HVN / LVN, from the daily profile (trailing 150
daily bars) and the weekly profile (trailing 150 completed weeks)
— with the settled reclaim system applied to those lines:

  reclaim   wick through a line, completed 15m close back across
  rejection the mirror from below
  break     a completed 15m bar opens one side, closes the other
  entry     = the line itself
  stop      = next node line beyond the entry; exit on a 15m
              close beyond it (no stop line -> still delivered,
              judged on target / close only)
  target    = next node line in the trade direction (a touch)
  cap       = ONE signal per symbol per day — the first fire

Universe: SPY, QQQ, NVDA, MU, META, AMZN. RTH only; calls die at
the 16:00 ET close. Target exits are recorded in the log, never
posted (Victor's general rule, 2026-11-21); only stop exits are
delivered.

Each run re-derives the day from the day's 15m bars (idempotent)
and diffs against vp-signal-state-<CT date>.json; new entries and
stop exits print as JSON actions for the routing agent:
  {"signals": [{key, card, symbol, direction, level, target}],
   "exits":   [{key, text, symbol}]}
Deliveries and outcomes append to vp-signals-<CT date>.jsonl.

--replay YYYY-MM-DD prints the day's fire and outcome for every
symbol and writes nothing.
"""
import importlib.util
import json
import os
import sys
from datetime import datetime, time as dtime

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "bt", os.path.join(HERE, "backtest_vp_nodes.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
vp = bt.vp
ET = vp.ET
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")

SYMS = ["SPY", "QQQ", "NVDA", "MU", "META", "AMZN"]


def day_maps(sym, day):
    daily = vp.fetch("5y", "1d", sym)
    for b in daily:
        b["d"] = datetime.fromtimestamp(b["t"], ET).date()
    daily.sort(key=lambda b: b["d"])
    weeks = {}
    for b in daily:
        wk = bt.monday_of(b["d"])
        if wk not in weeks:
            weeks[wk] = {"h": b["h"], "l": b["l"], "v": 0}
        w = weeks[wk]
        w["h"] = max(w["h"], b["h"])
        w["l"] = min(w["l"], b["l"])
        w["v"] += b["v"]
    wk_keys = sorted(weeks)
    past_d = [b for b in daily if b["d"] < day][-150:]
    dprof = vp.profile([(b["h"], b["l"], b["v"]) for b in past_d])
    mon = bt.monday_of(day)
    past_w = [weeks[k] for k in wk_keys if k < mon][-150:]
    wprof = vp.profile([(w["h"], w["l"], w["v"]) for w in past_w])
    if not dprof or not wprof:
        return None
    return bt.merged_map(dprof, wprof)


def day_bars(sym, day):
    bars15 = vp.fetch("5d", "15m", sym, prepost=True)
    out = []
    for b in bars15:
        dt = datetime.fromtimestamp(b["t"], ET)
        if dt.date() == day and dtime(9, 30) <= dt.time() < dtime(16, 0):
            out.append((dt, b))
    return out


def card_for(sym, f):
    side_word = "below" if f["side"] == "LONG" else "above"
    tgt = f"target {f['target']:.2f}" if f["target"] is not None \
        else "target: none"
    if f["stop"] is not None:
        stop_txt = f"stop: 15m close {side_word} {f['stop']:.2f}"
    else:
        stop_txt = "stop: none set"
    line1 = (f"{sym} {f['side']} {f['level']:.2f} — entry "
             f"{f['entry_close']:.2f} · {tgt} · {stop_txt}")
    if f["kind"] == "reclaim":
        why = (f"VP reclaim — wick below {f['label']} "
               f"{f['level']:.2f}, 15m close back above")
    elif f["kind"] == "rejection":
        why = (f"VP rejection — poke above {f['label']} "
               f"{f['level']:.2f}, 15m close back below")
    else:
        why = (f"VP break — 15m close through {f['label']} "
               f"{f['level']:.2f}")
    return line1 + "\nReason: " + why


def scan(day, dry_run=False):
    state_path = os.path.join(HERE, f"vp-signal-state-{day}.json")
    log_path = os.path.join(HERE, f"vp-signals-{day}.jsonl")
    state = {}
    if os.path.exists(state_path) and not dry_run:
        with open(state_path) as fh:
            state = json.load(fh)
    now_ct = datetime.now(CT)
    day_over = now_ct.date() > day or (
        now_ct.date() == day and now_ct.time() >= dtime(15, 0))
    actions = {"signals": [], "exits": []}

    def log(rec):
        if not dry_run:
            with open(log_path, "a") as fh:
                fh.write(json.dumps(rec) + "\n")

    for sym in SYMS:
        lines = day_maps(sym, day)
        bars = day_bars(sym, day)
        if not lines or not bars:
            continue
        f = bt.run_day(lines, bars)
        if f is None:
            continue
        kind_o, price, odt = f["outcome"]
        open_now = kind_o == "close" and not day_over
        key = (f"vp|{sym}|{day}|{f['level']:.2f}|{f['side']}")
        st = state.setdefault(sym, {})
        if st.get("entry_key") != key:
            card = card_for(sym, f)
            rec = {"type": "signal", "key": key, "symbol": sym,
                   "side": f["side"], "kind": f["kind"],
                   "level": round(f["level"], 2),
                   "label": f["label"],
                   "stop": round(f["stop"], 2) if f["stop"] else None,
                   "target": round(f["target"], 2)
                   if f["target"] else None,
                   "confirm_time_et": f["time"], "card": card}
            log(rec)
            actions["signals"].append({
                "key": key, "card": card, "symbol": sym,
                "direction": f["side"],
                "level": round(f["level"], 2),
                "target": round(f["target"], 2) if f["target"] else None})
            st.update({"entry_key": key, "exit_key": None,
                       "final": None})
        if not open_now and st.get("final") != kind_o:
            st["final"] = kind_o
            log({"type": "outcome", "key": key, "symbol": sym,
                 "outcome": kind_o, "exit_price": round(price, 2),
                 "exit_time_et": f"{odt:%H:%M}"})
            if kind_o == "stopped":
                side_word = "below" if f["side"] == "LONG" else "above"
                text = (f"{sym} VP stopped: 15m close {side_word} "
                        f"{f['stop']:.2f} at {price:.2f}")
                actions["exits"].append({"key": key + "|stop",
                                          "text": text, "symbol": sym})
                st["exit_key"] = key + "|stop"
    if not dry_run:
        with open(state_path, "w") as fh:
            json.dump(state, fh, indent=1)
    print(json.dumps(actions, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--replay":
        day = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
        for sym in SYMS:
            lines = day_maps(sym, day)
            bars = day_bars(sym, day)
            f = bt.run_day(lines, bars) if lines and bars else None
            if f is None:
                print(f"{sym}: no fire")
            else:
                kind_o, price, odt = f["outcome"]
                print(f"{sym}: {f['time']} ET {f['side']} "
                      f"{f['kind']} {f['label']} {f['level']:.2f} "
                      f"-> {kind_o} {price:.2f} at {odt:%H:%M}")
    else:
        scan(datetime.now(CT).date())
