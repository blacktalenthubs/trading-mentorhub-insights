"""Backtest Replay — validate rules against historical intraday data."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import DEFAULT_WATCHLIST
from analytics.intraday_data import (
    compute_vwap,
    fetch_historical_intraday,
    fetch_prior_day,
)
from analytics.intraday_rules import evaluate_rules, AlertSignal


def _build_spy_context(spy_bars: pd.DataFrame) -> dict:
    """Build SPY context dict from historical intraday bars for backtest."""
    default = {
        "trend": "neutral", "close": 0.0, "ma20": 0.0,
        "intraday_change_pct": 0.0, "spy_bouncing": False, "spy_intraday_low": 0.0,
    }
    if spy_bars.empty or len(spy_bars) < 2:
        return default

    spy_open = spy_bars["Open"].iloc[0]
    spy_current = spy_bars["Close"].iloc[-1]
    spy_low = spy_bars["Low"].min()

    intraday_change_pct = (spy_current - spy_open) / spy_open * 100 if spy_open > 0 else 0
    spy_bounce_pct = (spy_current - spy_low) / spy_low * 100 if spy_low > 0 else 0
    spy_bouncing = spy_bounce_pct >= 0.3 and spy_current > spy_open

    return {
        "trend": "bullish" if spy_current > spy_open else "bearish",
        "close": round(spy_current, 2),
        "ma20": 0.0,
        "intraday_change_pct": round(intraday_change_pct, 2),
        "spy_bouncing": spy_bouncing,
        "spy_intraday_low": round(spy_low, 2),
    }

st.set_page_config(
    page_title="Backtest Replay",
    page_icon="⚡",
    layout="wide",
)

st.title("Backtest Replay")
st.caption("Replay historical intraday data through the rule engine to validate signal quality.")

# ── Sidebar Controls ──────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Backtest Settings")

    target_date = st.date_input(
        "Date",
        value=date.today() - timedelta(days=1),
        min_value=date.today() - timedelta(days=59),
        max_value=date.today() - timedelta(days=1),
        help="Select a date within the last 59 days (yfinance limit)",
    )

    symbols_text = st.text_area(
        "Symbols (comma-separated)",
        value=", ".join(DEFAULT_WATCHLIST),
        height=80,
    )
    symbols = [s.strip().upper() for s in symbols_text.split(",") if s.strip()]

    mode = st.radio(
        "Replay Mode",
        ["End-of-day", "Bar-by-bar"],
        help="End-of-day: run rules once on full day. Bar-by-bar: simulate real-time scanning.",
    )

    run = st.button("Run Backtest", type="primary", use_container_width=True)

# ── Main ──────────────────────────────────────────────────────────────────

if not run:
    st.info("Select a date and symbols in the sidebar, then click **Run Backtest**.")
    st.stop()

if not symbols:
    st.warning("Enter at least one symbol.")
    st.stop()

date_str = target_date.isoformat()
st.markdown(f"### Results for {date_str}")

progress = st.progress(0)
all_results: list[dict] = []

# Fetch SPY context for the backtest date (used for bounce correlation)
spy_intra = fetch_historical_intraday("SPY", date_str)
spy_ctx = _build_spy_context(spy_intra)

for idx, symbol in enumerate(symbols):
    progress.progress((idx + 1) / len(symbols), text=f"Processing {symbol}...")

    intra = fetch_historical_intraday(symbol, date_str)
    if intra.empty:
        st.caption(f"{symbol}: no intraday data for {date_str}")
        continue

    prior = fetch_prior_day(symbol)
    if prior is None:
        st.caption(f"{symbol}: no prior day data")
        continue

    if mode == "End-of-day":
        # Feed full day's bars at once
        signals = evaluate_rules(symbol, intra, prior, spy_context=spy_ctx)
        for sig in signals:
            all_results.append({
                "Symbol": sig.symbol,
                "Type": sig.alert_type.value.replace("_", " ").title(),
                "Direction": sig.direction,
                "Price": sig.price,
                "Entry": sig.entry,
                "Stop": sig.stop,
                "T1": sig.target_1,
                "T2": sig.target_2,
                "Score": sig.score,
                "Grade": sig.score_label,
                "Confidence": sig.confidence,
                "Message": sig.message[:80],
            })

        # Draw chart with signal overlays
        if signals:
            with st.expander(f"{symbol} — {len(signals)} signal(s)", expanded=True):
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=intra.index.strftime("%H:%M"),
                    open=intra["Open"], high=intra["High"],
                    low=intra["Low"], close=intra["Close"],
                    name=symbol,
                    increasing_line_color="#2ecc71",
                    decreasing_line_color="#e74c3c",
                ))

                # VWAP
                vwap = compute_vwap(intra)
                if not vwap.empty:
                    fig.add_trace(go.Scatter(
                        x=intra.index.strftime("%H:%M"), y=vwap.values,
                        mode="lines", name="VWAP",
                        line=dict(color="#9b59b6", width=1.5, dash="dash"),
                    ))

                # Signal markers
                for sig in signals:
                    if sig.entry:
                        fig.add_hline(
                            y=sig.entry, line_dash="dash", line_color="#3498db",
                            line_width=1, annotation_text=f"{sig.direction} ${sig.entry:,.2f}",
                            annotation_font=dict(size=9),
                        )
                    if sig.stop:
                        fig.add_hline(
                            y=sig.stop, line_dash="dot", line_color="#e74c3c", line_width=1,
                        )

                fig.update_layout(
                    height=350, xaxis_rangeslider_visible=False,
                    title=f"{symbol} — {date_str}",
                    margin=dict(l=40, r=20, t=40, b=30),
                )
                st.plotly_chart(fig, use_container_width=True)

    else:
        # Bar-by-bar replay
        seen: set[tuple[str, str]] = set()
        bar_signals: list[dict] = []

        for i in range(6, len(intra)):
            partial = intra.iloc[: i + 1]
            # Build progressive SPY context for bar-by-bar mode
            spy_partial = spy_intra.iloc[: i + 1] if not spy_intra.empty and i < len(spy_intra) else spy_intra
            spy_ctx_partial = _build_spy_context(spy_partial)
            sigs = evaluate_rules(symbol, partial, prior, spy_context=spy_ctx_partial)
            for sig in sigs:
                key = (sig.symbol, sig.alert_type.value)
                if key in seen:
                    continue
                seen.add(key)
                bar_signals.append({
                    "Bar": partial.index[-1].strftime("%H:%M"),
                    "Symbol": sig.symbol,
                    "Type": sig.alert_type.value.replace("_", " ").title(),
                    "Direction": sig.direction,
                    "Price": sig.price,
                    "Score": sig.score,
                    "Grade": sig.score_label,
                })

        if bar_signals:
            with st.expander(f"{symbol} — {len(bar_signals)} signal(s) (bar-by-bar)", expanded=True):
                st.dataframe(
                    pd.DataFrame(bar_signals),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Price": st.column_config.NumberColumn(format="$%.2f"),
                    },
                )
            all_results.extend(bar_signals)
        else:
            st.caption(f"{symbol}: no signals fired")

progress.empty()

# ── Summary Table ─────────────────────────────────────────────────────────

if all_results:
    st.divider()
    st.subheader("All Signals Summary")

    df = pd.DataFrame(all_results)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Entry": st.column_config.NumberColumn(format="$%.2f"),
            "Stop": st.column_config.NumberColumn(format="$%.2f"),
            "T1": st.column_config.NumberColumn(format="$%.2f"),
            "T2": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    # Quick stats
    buy_count = sum(1 for r in all_results if r.get("Direction") == "BUY")
    sell_count = sum(1 for r in all_results if r.get("Direction") == "SELL")
    short_count = sum(1 for r in all_results if r.get("Direction") == "SHORT")
    st.caption(f"Total: {len(all_results)} | BUY: {buy_count} | SELL: {sell_count} | SHORT: {short_count}")
else:
    st.info("No signals fired for any symbol on this date.")
