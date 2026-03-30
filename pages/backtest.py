"""Backtest Replay — validate rules against historical intraday data."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db import get_watchlist
from analytics.intraday_data import (
    compute_vwap,
    fetch_historical_intraday,
    fetch_prior_day,
)
from analytics.intraday_rules import evaluate_rules, AlertSignal
import ui_theme


def _build_spy_context(spy_bars: pd.DataFrame) -> dict:
    """Build SPY context dict from historical intraday bars for backtest."""
    default = {
        "trend": "neutral", "close": 0.0, "ma20": 0.0,
        "ma5": 0.0, "ma50": 0.0, "regime": "CHOPPY",
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
        "ma5": 0.0,
        "ma50": 0.0,
        "regime": "CHOPPY",
        "intraday_change_pct": round(intraday_change_pct, 2),
        "spy_bouncing": spy_bouncing,
        "spy_intraday_low": round(spy_low, 2),
    }

user = ui_theme.setup_page("backtest")

ui_theme.page_header("Backtest Replay", "Replay historical intraday data through the rule engine to validate signal quality.")

# ── Sidebar Controls ──────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Backtest Settings")

    target_date = st.date_input(
        "Date",
        value=date.today() - timedelta(days=1),
        min_value=date.today() - timedelta(days=59),
        max_value=date.today(),
        help="Select a date within the last 59 days (yfinance limit)",
    )

    symbols_text = st.text_area(
        "Symbols (comma-separated)",
        value=", ".join(get_watchlist(user["id"] if user else None)),
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
    ui_theme.empty_state("Select a date and symbols in the sidebar, then click Run Backtest.")
    st.stop()

if not symbols:
    ui_theme.empty_state("Enter at least one symbol.", icon="warning")
    st.stop()

date_str = target_date.isoformat()
st.markdown(f"### Results for {date_str}")

progress = st.progress(0)
all_results: list[dict] = []

# Fetch SPY context + gate for the backtest date
spy_intra = fetch_historical_intraday("SPY", date_str)
spy_ctx = _build_spy_context(spy_intra)

# Build SPY gate with morning low for backtest
_spy_gate = None
if not spy_intra.empty:
    from analytics.intraday_rules import compute_spy_gate
    from analytics.intraday_data import compute_opening_range
    _spy_vwap = compute_vwap(spy_intra)
    _spy_gate = compute_spy_gate(spy_intra, _spy_vwap)
    _spy_or = compute_opening_range(spy_intra)
    if _spy_or and _spy_or.get("or_complete"):
        _spy_gate["morning_low"] = _spy_or["or_low"]
        _spy_gate["below_morning_low"] = float(spy_intra.iloc[-1]["Close"]) < _spy_or["or_low"]
    else:
        _spy_gate["morning_low"] = 0
        _spy_gate["below_morning_low"] = False

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
        signals = evaluate_rules(symbol, intra, prior, spy_context=spy_ctx, spy_gate=_spy_gate)
        for sig in signals:
            # Check outcome: did subsequent bars hit T1, T2, or Stop?
            outcome = ""
            if sig.entry and sig.direction in ("BUY", "SHORT"):
                is_short = sig.direction == "SHORT"
                # Find the bar where the signal fired (closest price match)
                for bar_idx in range(len(intra)):
                    bar_close = float(intra.iloc[bar_idx]["Close"])
                    if abs(bar_close - sig.price) / sig.price < 0.002:
                        # Scan subsequent bars for outcome
                        for j in range(bar_idx + 1, len(intra)):
                            future = intra.iloc[j]
                            if sig.stop:
                                if is_short and float(future["High"]) >= sig.stop:
                                    outcome = "STOPPED"
                                    break
                                elif not is_short and float(future["Low"]) <= sig.stop:
                                    outcome = "STOPPED"
                                    break
                            if sig.target_2:
                                if is_short and float(future["Low"]) <= sig.target_2:
                                    outcome = "T2 HIT"
                                    break
                                elif not is_short and float(future["High"]) >= sig.target_2:
                                    outcome = "T2 HIT"
                                    break
                            if sig.target_1:
                                if is_short and float(future["Low"]) <= sig.target_1:
                                    outcome = "T1 HIT"
                                    break
                                elif not is_short and float(future["High"]) >= sig.target_1:
                                    outcome = "T1 HIT"
                                    break
                        break
                if not outcome and sig.entry:
                    outcome = "OPEN"

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
                "Outcome": outcome,
                "Message": sig.message[:80],
            })

        # Draw chart with signal overlays
        if signals:
            with st.expander(f"{symbol} — {len(signals)} signal(s)", expanded=True):
                # Gap-free integer x-axis with time labels
                x_int = list(range(len(intra)))
                time_labels = intra.index.strftime("%H:%M")
                step = max(1, len(intra) // 10)
                tick_vals = x_int[::step]
                tick_text = [time_labels[i] for i in tick_vals]

                fig = ui_theme.build_candlestick_fig(
                    intra, x_int, symbol,
                    height=350, tick_vals=tick_vals, tick_text=tick_text,
                )

                # VWAP
                vwap = compute_vwap(intra)
                if not vwap.empty:
                    fig.add_trace(go.Scatter(
                        x=list(range(len(vwap))), y=vwap.values,
                        mode="lines", name="VWAP",
                        line=dict(color="#9b59b6", width=1.5, dash="dash"),
                    ))

                # Session low reference line
                session_low = intra["Low"].min()
                if session_low > 0:
                    ui_theme.add_level_line(
                        fig, session_low, "Session Low", "#f39c12",
                        position="bottom left", dash="dot", width=1.5,
                    )

                # Signal markers
                for sig in signals:
                    if sig.entry:
                        ui_theme.add_level_line(
                            fig, sig.entry, f"{sig.direction}", "#3498db",
                            position="top left",
                        )
                    if sig.stop:
                        ui_theme.add_level_line(
                            fig, sig.stop, "Stop", "#e74c3c",
                            position="bottom left", dash="dot", width=1,
                        )

                st.plotly_chart(fig, use_container_width=True, config=ui_theme.PLOTLY_CONFIG_MINIMAL)

    else:
        # Bar-by-bar replay
        seen: set[tuple[str, str]] = set()
        bar_signals: list[dict] = []

        for i in range(6, len(intra)):
            partial = intra.iloc[: i + 1]
            # Build progressive SPY context for bar-by-bar mode
            spy_partial = spy_intra.iloc[: i + 1] if not spy_intra.empty and i < len(spy_intra) else spy_intra
            spy_ctx_partial = _build_spy_context(spy_partial)
            sigs = evaluate_rules(symbol, partial, prior, spy_context=spy_ctx_partial, spy_gate=_spy_gate)
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
    ui_theme.section_header("All Signals Summary")

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

    # Win rate (entries only)
    entries = [r for r in all_results if r.get("Outcome") in ("T1 HIT", "T2 HIT", "STOPPED", "OPEN")]
    winners = sum(1 for r in entries if r.get("Outcome") in ("T1 HIT", "T2 HIT"))
    losers = sum(1 for r in entries if r.get("Outcome") == "STOPPED")
    win_rate = f" | Win Rate: {winners}/{winners + losers} ({winners / (winners + losers) * 100:.0f}%)" if (winners + losers) > 0 else ""

    st.caption(f"Total: {len(all_results)} | BUY: {buy_count} | SHORT: {short_count} | SELL: {sell_count}{win_rate}")
else:
    ui_theme.empty_state("No signals fired for any symbol on this date.")
