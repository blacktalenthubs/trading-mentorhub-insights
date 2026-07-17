"""Fundamentals — watchlist quality/risk ranking + per-stock deep report.

Reads the cached ``fund_*`` tables written by the nightly Fundamentals Engine
(analytics/fundamentals_engine_refresh, EDGAR-sourced). No live API calls here —
the page renders from cache in a few seconds (NFR: performance).

Answers the core question at a glance: "is this profitable / a real value or
just hype?" — quality score, risk score, and the surfaced red/value flags, all
traceable to the source SEC filing.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import ui_theme
from db import _pd_read_sql, get_db, get_watchlist

user = ui_theme.setup_page("fundamentals", tier_required="free")

st.title("📊 Fundamentals Engine")
st.caption(
    "Deep fundamentals from SEC filings — red-flag detection (Staley) + value "
    "screening (Greenblatt / Graham). Updated nightly. Education only, not advice."
)

_SEV_ICON = {"critical": "🚩", "warn": "⚠️", "info": "✅"}
_SEV_RANK = {"critical": 0, "warn": 1, "info": 2}


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def _load_scores(symbols: list[str]) -> pd.DataFrame:
    """Latest score row per symbol. Returns empty DF if the engine hasn't run
    (or the tables don't exist yet locally)."""
    if not symbols:
        return pd.DataFrame()
    ph = _placeholders(len(symbols))
    q = f"""
        SELECT s.symbol, s.quality_score, s.risk_score, s.profitable,
               s.quality_coverage, s.risk_coverage, s.as_of_date, s.latest_period_end
        FROM fund_score s
        JOIN (SELECT symbol, MAX(as_of_date) AS md FROM fund_score
              WHERE symbol IN ({ph}) GROUP BY symbol) l
          ON s.symbol = l.symbol AND s.as_of_date = l.md
    """
    try:
        with get_db() as conn:
            return _pd_read_sql(q, conn, params=symbols)
    except Exception:
        return pd.DataFrame()


def _load_flags(symbols: list[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    ph = _placeholders(len(symbols))
    q = f"""
        SELECT f.symbol, f.code, f.severity, f.label, f.detail, f.metric, f.as_of_date
        FROM fund_flag f
        JOIN (SELECT symbol, MAX(as_of_date) AS md FROM fund_flag
              WHERE symbol IN ({ph}) GROUP BY symbol) l
          ON f.symbol = l.symbol AND f.as_of_date = l.md
    """
    try:
        with get_db() as conn:
            return _pd_read_sql(q, conn, params=symbols)
    except Exception:
        return pd.DataFrame()


watchlist = sorted(set(get_watchlist(user["id"] if user else None)))
if not watchlist:
    st.info("Your watchlist is empty. Add symbols to see their fundamentals here.")
    st.stop()

scores = _load_scores(watchlist)
flags = _load_flags(watchlist)

if scores.empty:
    st.warning(
        "No fundamentals computed yet. The engine runs nightly (03:00 ET) over "
        "your watchlist. Newly-added symbols appear after the next run."
    )
    st.stop()

# Flag chips per symbol (severity-ranked).
flags_by_sym: dict[str, list] = {}
if not flags.empty:
    flags = flags.sort_values("severity", key=lambda s: s.map(lambda x: _SEV_RANK.get(x, 3)))
    for _, r in flags.iterrows():
        flags_by_sym.setdefault(r["symbol"], []).append(r)


def _flag_summary(sym: str) -> str:
    rows = flags_by_sym.get(sym, [])
    if not rows:
        return "—"
    return "  ".join(f"{_SEV_ICON.get(r['severity'], '•')} {r['label']}" for r in rows[:4])


# ── ranking table ────────────────────────────────────────────────────────
tbl = scores.copy()
tbl["profitable"] = tbl["profitable"].map(lambda v: "✅" if v else ("❌" if v is not None else "—"))
tbl["flags"] = tbl["symbol"].map(_flag_summary)
tbl = tbl.rename(columns={
    "symbol": "Symbol", "quality_score": "Quality", "risk_score": "Risk",
    "profitable": "Profitable", "flags": "Flags", "as_of_date": "As of",
})
tbl = tbl.sort_values(["Risk", "Quality"], ascending=[False, True])

st.subheader("Watchlist ranking")
st.caption("Sorted by risk (highest first), then quality (lowest first) — the names to look at.")
st.dataframe(
    tbl[["Symbol", "Quality", "Risk", "Profitable", "Flags", "As of"]],
    use_container_width=True, hide_index=True,
    column_config={
        "Quality": st.column_config.ProgressColumn("Quality", min_value=0, max_value=100, format="%d"),
        "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%d"),
    },
)

uncovered = sorted(set(watchlist) - set(scores["symbol"]))
if uncovered:
    st.caption("No SEC fundamentals (ETF / ADR / recent IPO): " + ", ".join(uncovered))

# ── per-stock drill-down ─────────────────────────────────────────────────
st.divider()
st.subheader("Per-stock report")
sym = st.selectbox("Symbol", sorted(scores["symbol"].tolist()))
if sym:
    row = scores[scores["symbol"] == sym].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Quality score", f"{row['quality_score']:.0f}")
    c2.metric("Risk score", f"{row['risk_score']:.0f}")
    c3.metric("Profitable (TTM GAAP)", "Yes ✅" if row["profitable"] else "No ❌")
    st.caption(
        f"As of {row['as_of_date']} · latest filing period {row['latest_period_end']} · "
        f"data coverage q{row['quality_coverage']:.0%}/r{row['risk_coverage']:.0%}"
    )

    rows = flags_by_sym.get(sym, [])
    if rows:
        st.markdown("**Flags**")
        for r in rows:
            icon = _SEV_ICON.get(r["severity"], "•")
            detail = f" — {r['detail']}" if r["detail"] else ""
            st.markdown(f"{icon} **{r['label']}**{detail}")

    # Metrics (latest period) + financial time series, from cache.
    try:
        with get_db() as conn:
            metrics = _pd_read_sql(
                """SELECT name, value, unit, source_url FROM fund_metric
                   WHERE symbol = ? AND period_end = (
                       SELECT MAX(period_end) FROM fund_metric WHERE symbol = ?)""",
                conn, params=[sym, sym],
            )
            fin = _pd_read_sql(
                """SELECT period_end, form, revenue, gross_profit, operating_income,
                          net_income, operating_cash_flow, inventory, receivables,
                          total_assets, stockholders_equity, shares_diluted, source_url
                   FROM fund_financials WHERE symbol = ? ORDER BY period_end""",
                conn, params=[sym],
            )
    except Exception:
        metrics, fin = pd.DataFrame(), pd.DataFrame()

    if not metrics.empty:
        st.markdown("**Key metrics** (latest period)")
        st.dataframe(metrics, use_container_width=True, hide_index=True)
    if not fin.empty:
        st.markdown("**Financial history** (source: SEC EDGAR — click a source URL to audit)")
        st.dataframe(fin, use_container_width=True, hide_index=True)
