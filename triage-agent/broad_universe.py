"""Curated thematic LEADERS universe — the pool the swing scanner + universe research draw from.

Philosophy (user 2026-07-12): we do NOT want all 500 S&P names. We want the TOPS + the strongest names
in the key sectors moving the markets — AI / technology / growth and the strong "AI-proof" sectors —
large AND mid cap, momentum-tilted. A ~100-150 baseline is enough to find setups most days. Selection is
handled downstream by the relative-strength filter (swing_scan._rs_rank / SWING_RS_TOPN) and by the strong
entry/exit rules, so this list just has to be the RIGHT pool, not exhaustive. Organized by theme so it's
easy to prune/extend as leadership rotates.

Unioned in swing_scan.main() with the master watchlist + LTF finders + IBD 50 / Sector Leaders, then
RS-filtered to the top performers.
"""

THEMES = {
    "AI / Software / Data": [
        "NVDA", "MSFT", "GOOGL", "META", "AMZN", "PLTR", "NOW", "CRWD", "PANW", "ZS",
        "FTNT", "NET", "SNOW", "DDOG", "MDB", "APP", "DUOL", "RDDT", "AI", "INOD",
        "ZETA", "ADBE", "CRM", "ORCL", "INTU", "WDAY", "HUBS", "TWLO", "OKTA", "MNDY",
        "GTLB", "CFLT", "ESTC", "TEAM", "S", "FROG", "TOST",
    ],
    "Semis / Chips / Hardware": [
        "AVGO", "AMD", "TSM", "ASML", "MU", "MRVL", "LRCX", "AMAT", "KLAC", "ARM",
        "QCOM", "TXN", "ADI", "NXPI", "MCHP", "ON", "ALAB", "CRDO", "COHR", "LITE",
        "AEHR", "ACMR", "ONTO", "NVMI", "RMBS", "SITM", "UCTT", "SMCI", "DELL", "ANET",
        "CIEN", "STX", "WDC", "SNDK", "INTC", "TER", "ENTG", "KEYS", "MPWR", "POET",
    ],
    "AI Power / Nuclear / Energy infra": [
        "VST", "CEG", "GEV", "OKLO", "SMR", "NNE", "TLN", "VRT", "POWL", "ETN",
        "PWR", "NRG", "BE", "BWXT", "FIX",
    ],
    "Space / Defense / Autonomy": [
        "RKLB", "ASTS", "LUNR", "RDW", "KTOS", "AXON", "LMT", "RTX", "GD", "NOC",
        "PL", "ACHR", "JOBY", "OUST",
    ],
    "Quantum": [
        "IONQ", "RGTI", "QBTS", "QUBT",
    ],
    "Fintech / Crypto": [
        "COIN", "HOOD", "AFRM", "SOFI", "DAVE", "SEZL", "NU", "MSTR", "PYPL", "FI",
        "MARA", "RIOT", "CLSK", "IREN", "CRWV", "NBIS", "WULF",
    ],
    "Healthcare / Biotech leaders (AI-proof)": [
        "LLY", "VRTX", "ISRG", "ARGX", "REGN", "AMGN", "GILD", "CRSP", "NTLA", "TGTX",
        "HIMS", "ALNY", "NBIX", "EXEL", "KRYS", "RXRX", "TEM",
    ],
    "Consumer / Retail momentum": [
        "COST", "WMT", "ANF", "ONON", "CAVA", "CELH", "DECK", "CMG", "DASH", "ABNB",
        "BKNG", "RCL", "SG", "WING",
    ],
    "Industrials / Infrastructure leaders": [
        "CAT", "DE", "PH", "HWM", "GE", "URI",
    ],
    "Mega-cap anchors": [
        "AAPL", "TSLA", "NFLX",
    ],
}

BROAD_UNIVERSE = sorted({s for names in THEMES.values() for s in names})
