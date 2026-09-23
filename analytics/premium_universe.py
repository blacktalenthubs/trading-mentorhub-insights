"""Premium Desk universe — the leveraged-ETF options we sell premium on.

Single source of truth for WHICH tickers the Premium Desk scores, and the theme
(mega-cap underlying) behind each. This is the S1 config: everything downstream
(IV snapshot, scoring, feed) iterates `UNIVERSE`, so adding a name is a one-line
edit here — no code changes elsewhere.

We sell options on the LEVERAGED ETF (e.g. NVDL), not the underlying — so IV rank,
RSI and MA reclaims are all computed on the ETF's own price/option chain. The
`underlying` field is the theme label shown in the UI ("Nvidia 2x") and lets us
borrow the mega-cap's trend when the ETF's own history is short.

Extensible by design: single-stock 2x ETFs today; broad 3x index ETFs; sector
ETFs next (the `kind` field tags them so the UI can group/filter). The eventual
goal is any optionable stock — this map is the baseline we start from.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    etf: str            # the ticker we sell options ON (chain + IV live here)
    underlying: str     # the mega-cap / index the ETF tracks (theme, trend borrow)
    theme: str          # human label for the UI
    leverage: float     # 2.0, 3.0 — sizing + risk-tier input
    kind: str           # "single" | "index" | "sector"
    issuer: str = ""    # GraniteShares / Direxion / ProShares — liquidity nuance


# --- Single-stock leveraged ETFs (mega-cap tech, 2x) -------------------------
# GraniteShares 2x long single-stock ETFs. Options exist but are thinner than the
# 3x index names — the IV snapshot skips any symbol whose chain doesn't resolve.
_SINGLE = [
    Instrument("NVDL", "NVDA", "Nvidia 2x", 2.0, "single", "GraniteShares"),
    Instrument("TSLL", "TSLA", "Tesla 2x", 2.0, "single", "Direxion"),
    Instrument("GGLL", "GOOGL", "Alphabet 2x", 2.0, "single", "Direxion"),
    Instrument("AAPU", "AAPL", "Apple 2x", 2.0, "single", "Direxion"),
    Instrument("MSFU", "MSFT", "Microsoft 2x", 2.0, "single", "Direxion"),
    Instrument("METU", "META", "Meta 2x", 2.0, "single", "Direxion"),
    Instrument("AMZU", "AMZN", "Amazon 2x", 2.0, "single", "Direxion"),
]

# --- Broad leveraged index ETFs (3x) — deepest, most liquid option chains -----
_INDEX = [
    Instrument("SOXL", "SOX", "Semis 3x", 3.0, "index", "Direxion"),
    Instrument("TQQQ", "QQQ", "Nasdaq-100 3x", 3.0, "index", "ProShares"),
]

# Sector ETFs land here next (user: "we can add sector etf too"). Left empty so
# the shape is settled; filling it needs no downstream change.
_SECTOR: list[Instrument] = []

UNIVERSE: list[Instrument] = [*_SINGLE, *_INDEX, *_SECTOR]

# Fast lookups.
BY_ETF: dict[str, Instrument] = {i.etf: i for i in UNIVERSE}


def etfs() -> list[str]:
    """The tickers to snapshot / score, in config order."""
    return [i.etf for i in UNIVERSE]


def get(etf: str) -> Instrument | None:
    return BY_ETF.get(etf.upper())
