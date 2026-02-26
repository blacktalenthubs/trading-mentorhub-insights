"""Constants and stock category definitions."""

from __future__ import annotations

import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "trades.db")

# Default admin credentials (for data migration — set via env vars or use defaults)
DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@tradesignal.local")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

# Account numbers
ACCOUNTS = {
    "145610192": "Main Brokerage",
    "496636044": "Recurring Investment",
    "818537748": "Options Account",
    "145610192C": "Crypto",
}

RECURRING_ACCOUNT = "496636044"

# The individual trading account to focus dashboard on
FOCUS_ACCOUNT = "145610192"

# Stock categorization
MEGA_CAP = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "AVGO", "BRK.B", "LLY", "JPM", "V", "UNH", "XOM", "MA", "JNJ",
    "PG", "COST", "HD", "ABBV", "NFLX", "CRM", "BAC", "ORCL", "AMD",
    "KO", "MRK", "PEP", "TMO", "ACN", "WMT", "LIN", "ADBE", "MCD",
    "CSCO", "QCOM", "INTC",
}

SPECULATIVE = {
    "RGTI", "AEVA", "BKSY", "DWAVE", "DM", "DWAV", "JOBY", "SERV",
    "SOUN", "TXG", "VSAT", "BULL", "AFRM", "SOFI", "HOOD", "SMR",
    "CRSP", "ABAT", "PLTR", "FIG", "COIN", "RKT", "TEM",
}

INDEX_ETF = {
    "SPY", "QQQ", "VTI", "IWB", "RSP", "SPXL", "TQQQ",
    "XLF", "XLE", "XLI", "XLP", "XLK", "XLV", "XLY", "XLB", "XLU",
    "XLRE", "XLC",
}

CRYPTO_SYMBOLS = {"BTC", "ETH", "DOGE", "SOL", "ADA", "XRP"}

# Holding period thresholds (days)
DAY_TRADE_MAX = 0  # bought and sold same day
SWING_TRADE_MAX = 30

# Recommended stop loss % by holding period (support/resistance style)
STOP_LOSS_PCT = {
    "day_trade": 1.5,   # tight stop for intraday
    "swing": 2.5,       # moderate stop for multi-day
    "position": 4.0,    # wider stop for longer holds
    "unknown": 2.5,     # default to swing-style
}

# Loss severity thresholds (% of trade value)
LOSS_ACCEPTABLE_PCT = 2.0    # small, disciplined loss
LOSS_CAUTION_PCT = 5.0       # getting too large
# Above LOSS_CAUTION_PCT = danger zone

# Strategy tags for trade annotation
STRATEGY_TAGS = [
    "support_bounce",
    "ma_bounce",
    "key_level",
    "breakout",
    "pullback_buy",
    "gap_play",
    "momentum",
    "earnings",
    "other",
]


def categorize_symbol(symbol: str) -> str:
    """Return category for a ticker symbol."""
    sym = symbol.upper().strip()
    if sym in CRYPTO_SYMBOLS:
        return "crypto"
    if sym in INDEX_ETF:
        return "index_etf"
    if sym in MEGA_CAP:
        return "mega_cap"
    if sym in SPECULATIVE:
        return "speculative"
    return "other"


def classify_holding_period(days: Optional[int]) -> str:
    """Classify trade by holding period."""
    if days is None:
        return "unknown"
    if days <= DAY_TRADE_MAX:
        return "day_trade"
    if days <= SWING_TRADE_MAX:
        return "swing"
    return "position"


# --- Signal Scanner constants ---

DEFAULT_WATCHLIST = [
    "LRCX", "PLTR", "ONDS", "META", "TSLA", "NVDA", "GOOGL", "SPY", "AAPL", "AMD",
]

ALERT_WATCHLIST = DEFAULT_WATCHLIST.copy()

QUICK_PICKS = {
    "Index ETFs": ["SPY", "QQQ", "IWB", "RSP", "XLK", "XLF", "XLE"],
    "Mega-Cap": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA"],
    "Tech": ["NVDA", "AMD", "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "QCOM"],
    "Speculative": ["PLTR", "SOFI", "HOOD", "COIN", "RGTI", "SOUN", "AFRM"],
}

# Scoring weights (each factor 0-25, total 0-100)
SIGNAL_WEIGHTS = {
    "candle_pattern": 25,
    "ma_position": 25,
    "support_proximity": 25,
    "volume": 25,
}

SCORE_THRESHOLDS = {
    "BUY": 75,    # >= 75
    "WAIT": 50,   # 50-74
    "AVOID": 0,   # < 50
}

DEFAULT_POSITION_SIZE = 150_000

CUSIP_TO_SYMBOL = {
    "007903107": "AMD", "00827B106": "AFRM", "00835Q202": "AEVA",
    "02079K305": "GOOGL", "023135106": "AMZN", "02451V309": "ABAT",
    "037833100": "AAPL", "04626A103": "ALAB", "09263B207": "BKSY",
    "11135F101": "AVGO", "19260Q107": "COIN", "26740W109": "DWAVE",
    "30303M102": "META", "349381103": "FIG", "46137V357": "RSP",
    "464287622": "IWB", "512807306": "LRCX", "594918104": "MSFT",
    "64110L106": "NFLX", "67066G104": "NVDA", "67079K100": "SMR",
    "68389X105": "ORCL", "69608A108": "PLTR", "74347X831": "TQQQ",
    "76655K103": "RGTI", "770700102": "HOOD", "77311W101": "RKT",
    "78462F103": "SPY", "81369Y308": "XLP", "81369Y506": "XLE",
    "81369Y605": "XLF", "81369Y704": "XLI", "81758H106": "SERV",
    "833445109": "SNOW", "83406F102": "SOFI", "836100107": "SOUN",
    "88023B103": "TEM", "88025U109": "TXG", "88160R101": "TSLA",
    "922908769": "VTI", "92552V100": "VSAT", "25459W862": "SPXL",
    "74347W601": "UGL",
    "G65163100": "JOBY", "G9572D103": "BULL", "H17182108": "CRSP",
}


def detect_asset_type(description: str, symbol: str) -> str:
    """Detect whether a security is stock, option, ETF, or crypto."""
    desc_upper = description.upper()
    sym_upper = symbol.upper()
    # Check for option keywords - be specific to avoid false positives
    if "CALL" in desc_upper or "PUT" in desc_upper:
        return "option"
    # Check symbol pattern for options: "AAPL 11/14/25 C 260.000"
    import re
    if re.search(r"[A-Z]+\s+\d{2}/\d{2}/\d{2}\s+[CP]\s+[\d.]+", sym_upper):
        return "option"
    if sym_upper in CRYPTO_SYMBOLS or "BITCOIN" in desc_upper or "CRYPTO" in desc_upper:
        return "crypto"
    if sym_upper in INDEX_ETF or "ETF" in desc_upper or "TRUST" in desc_upper or "SPDR" in desc_upper:
        return "etf"
    return "stock"
