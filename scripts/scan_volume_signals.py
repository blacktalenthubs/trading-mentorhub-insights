"""Validate the volume-profile signals against live data — NO scanner changes.

Runs the standalone engine (analytics/volume_profile_signals.py) over a list of
symbols and prints which ones are AT each setup right now, so you can eyeball the
hits against your charts before we wire it into the scanner.

Usage:
    PYTHONPATH=. python3 scripts/scan_volume_signals.py                 # default focus list
    PYTHONPATH=. python3 scripts/scan_volume_signals.py NBIS LRCX COHR  # specific names
"""
from __future__ import annotations

import sys

from analytics.market_data import fetch_ohlc
from analytics.volume_profile_signals import detect_signals

# Short signals only for the index/short universe (matches the gap scanner rule).
try:
    from alert_config import SHORT_UNIVERSE
except Exception:
    SHORT_UNIVERSE = {"SPY", "QQQ", "SMH", "DRAM"}

DEFAULT = [
    "NBIS", "LRCX", "COHR", "DRAM", "AAOI", "QCOM", "MU", "SNDK", "GOOGL", "META",
    "AVGO", "CRDO", "AMD", "NVDA", "SMH", "SPY", "QQQ", "TSLA", "AMZN", "MSFT",
    "AAPL", "PLTR", "MSTR", "HOOD", "ARM", "ASML", "TSM", "MRVL", "SOXL", "WDC",
]

KIND_LABEL = {
    "poc_reclaim":  "POC reclaim  (long)",
    "val_bounce":   "VAL bounce   (long)",
    "vah_breakout": "VAH breakout (long)",
    "vwap_reclaim": "VWAP reclaim (long)",
    "vwap_loss":    "VWAP loss    (short)",
}


def main() -> int:
    symbols = [s.upper() for s in sys.argv[1:]] or DEFAULT
    print(f"Scanning {len(symbols)} symbols for volume-profile setups "
          f"(last completed daily bar)\n" + "=" * 68)

    hits_by_kind: dict[str, list[str]] = {}
    no_data: list[str] = []
    total_hits = 0

    for sym in symbols:
        df = fetch_ohlc(sym, period="1y", interval="1d")
        if df is None or df.empty or len(df) < 30:
            no_data.append(sym)
            continue
        sigs = detect_signals(df, sym, short_ok=sym in SHORT_UNIVERSE)
        if not sigs:
            continue
        price = float(df["Close"].iloc[-1])
        print(f"\n{sym}  ${price:,.2f}")
        for s in sigs:
            total_hits += 1
            hits_by_kind.setdefault(s.kind, []).append(sym)
            conf = f"  ⭐ confluence: {', '.join(s.confluence)}" if s.confluence else ""
            print(f"   {KIND_LABEL.get(s.kind, s.kind):22} {s.level_name} @ ${s.level:,.2f}{conf}")

    print("\n" + "=" * 68)
    print(f"{total_hits} signal(s) across {sum(len(v) for v in hits_by_kind.values()) and len({s for v in hits_by_kind.values() for s in v})} symbol(s)")
    for kind, syms in hits_by_kind.items():
        print(f"  {KIND_LABEL.get(kind, kind):22} {len(syms):2}  {', '.join(syms)}")
    if no_data:
        print(f"\n  no/short data: {', '.join(no_data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
