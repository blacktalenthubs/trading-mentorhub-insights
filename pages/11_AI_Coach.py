"""AI Intelligence Hub — 5-tab command center for AI-powered trade analysis."""

from __future__ import annotations

import streamlit as st
import pandas as pd

import ui_theme
from ui_theme import (
    CHART_HEIGHTS,
    COLORS,
    PLOTLY_CONFIG,
    add_level_line,
    build_candlestick_fig,
    colored_metric,
    empty_state,
    page_header,
    section_header,
)

from ui_theme import (
    FREE_TIER_LIMITS,
    get_current_tier,
    render_inline_upgrade,
    render_usage_counter,
    check_usage_limit,
)

user = ui_theme.setup_page("ai_coach", tier_required="elite", tier_preview="free")

page_header(
    "AI Intelligence Hub",
    "Symbol-focused intelligence: win rates, fundamentals, weekly trend, AI coach, and scanner",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "coach_messages" not in st.session_state:
    st.session_state["coach_messages"] = []
if "coach_context" not in st.session_state:
    st.session_state["coach_context"] = None

# ---------------------------------------------------------------------------
# Symbol selector — prominent, above tabs
# ---------------------------------------------------------------------------

from db import get_watchlist

_uid = user["id"] if user else None
watchlist = get_watchlist(_uid)
sym_options = watchlist if watchlist else ["SPY"]

# Check for deep link query params (from Telegram alert links)
_qp_symbol = st.query_params.get("symbol", "").strip().upper()
_qp_alert = st.query_params.get("alert", "").strip()

sel_col, custom_col = st.columns([2, 1])
with sel_col:
    _default_idx = 0
    if _qp_symbol and _qp_symbol in sym_options:
        _default_idx = sym_options.index(_qp_symbol)
    selected_sym = st.selectbox(
        "Symbol", sym_options, index=_default_idx, key="hub_symbol_select",
    )
with custom_col:
    custom_sym = st.text_input(
        "Custom symbol", key="hub_custom_sym",
        placeholder="e.g. NVDA",
        value=_qp_symbol if (_qp_symbol and _qp_symbol not in sym_options) else "",
    )
hub_symbol = custom_sym.strip().upper() if custom_sym.strip() else selected_sym

# If deep-linked from a Telegram alert, pre-seed the chat with context
if _qp_alert and "coach_messages" in st.session_state and not st.session_state["coach_messages"]:
    _alert_label = _qp_alert.replace("_", " ").title()
    st.session_state["_deeplink_prompt"] = (
        f"Analyze this {_alert_label} signal for {hub_symbol} — should I take it? "
        f"What's the conviction level and key invalidation price?"
    )

# ---------------------------------------------------------------------------
# Sidebar — context snapshot + controls
# ---------------------------------------------------------------------------

_is_free = get_current_tier() == "free"
_ai_limit = FREE_TIER_LIMITS["ai_queries_per_day"]

with st.sidebar:
    # Usage counter for free users
    if _is_free and user:
        _, _current_usage = check_usage_limit(user["id"], "ai_query", _ai_limit)
        render_usage_counter(_current_usage, _ai_limit, "AI queries")
        st.divider()

    # Clear chat
    if st.button("Clear conversation"):
        st.session_state["coach_messages"] = []
        st.session_state["coach_context"] = None
        st.rerun()

    st.divider()
    st.subheader("Context Snapshot")

    try:
        from analytics.trade_coach import assemble_context

        if st.session_state["coach_context"] is None:
            with st.spinner("Loading market data..."):
                st.session_state["coach_context"] = assemble_context()
        ctx = st.session_state["coach_context"]

        # Open trades
        open_trades = ctx.get("open_trades") or []
        st.metric("Open Trades", len(open_trades))

        # P&L
        stats = ctx.get("trade_stats")
        if stats and stats.get("total_trades", 0) > 0:
            st.metric("Total P&L", f"${stats['total_pnl']:,.2f}")
            st.metric("Win Rate", f"{stats['win_rate']}%")
        else:
            st.metric("Total P&L", "\u2014")
            st.metric("Win Rate", "\u2014")

        # SPY regime
        spy = ctx.get("spy_context")
        if spy:
            st.metric("SPY Regime", spy.get("regime", "\u2014"))
        else:
            st.metric("SPY Regime", "\u2014")

    except Exception:
        st.caption("Could not load context")

    # Position Advisor button (Pro+)
    if not _is_free:
        st.divider()
        if st.button("Check My Positions", use_container_width=True, key="pos_check"):
            st.session_state["_run_position_check"] = True


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

# Position check result (if triggered from sidebar)
if st.session_state.pop("_run_position_check", False):
    with st.expander("Position Check", expanded=True):
        try:
            from analytics.position_advisor import check_positions_stream
            st.write_stream(check_positions_stream())
        except Exception as e:
            st.error(f"Position check failed: {e}")

tab_analysis, tab_fundamentals, tab_weekly, tab_coach, tab_scanner = st.tabs([
    "Trade Analysis", "Fundamentals", "Weekly View", "AI Coach", "Scanner",
])


# ── Tab 1: Trade Analysis ────────────────────────────────────────────────────

with tab_analysis:
    section_header("Alert Win Rates", "Historical signal accuracy")

    lookback = st.selectbox(
        "Lookback period", [30, 60, 90, 180],
        index=2, key="win_rate_lookback",
        format_func=lambda d: f"{d} days",
    )

    try:
        from analytics.intel_hub import get_alert_win_rates

        with st.spinner("Analyzing alerts..."):
            rates = get_alert_win_rates(days=lookback, user_id=_uid)

        overall = rates.get("overall", {})
        if overall.get("total", 0) == 0:
            empty_state("No entry signals found in this period")
        else:
            # KPI row
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                colored_metric("Total Signals", str(overall["total"]), COLORS["blue"])
            with k2:
                wr = overall["win_rate"]
                wr_color = COLORS["green"] if wr >= 50 else COLORS["red"]
                colored_metric("Win Rate", f"{wr}%", wr_color)
            with k3:
                colored_metric("Wins", str(overall["wins"]), COLORS["green"])
            with k4:
                colored_metric("Losses", str(overall["losses"]), COLORS["red"])

            # Win rate by symbol
            by_sym = rates.get("by_symbol", {})
            if by_sym:
                section_header("By Symbol")
                sym_rows = [
                    {"Symbol": sym, "Win Rate": f"{d['win_rate']}%",
                     "Wins": d["wins"], "Losses": d["losses"],
                     "Total": d["total"]}
                    for sym, d in sorted(by_sym.items(),
                                         key=lambda x: x[1]["win_rate"],
                                         reverse=True)
                ]
                st.dataframe(
                    pd.DataFrame(sym_rows),
                    use_container_width=True, hide_index=True,
                )

            # Win rate by setup type
            by_type = rates.get("by_alert_type", {})
            if by_type:
                section_header("By Setup Type")
                type_rows = [
                    {"Setup": at.replace("_", " ").title(),
                     "Win Rate": f"{d['win_rate']}%",
                     "Wins": d["wins"], "Losses": d["losses"],
                     "Total": d["total"]}
                    for at, d in sorted(by_type.items(),
                                        key=lambda x: x[1]["win_rate"],
                                        reverse=True)
                ]
                st.dataframe(
                    pd.DataFrame(type_rows),
                    use_container_width=True, hide_index=True,
                )

            # Win rate by hour
            by_hour = rates.get("by_hour", {})
            if by_hour:
                section_header("By Hour of Day")
                import plotly.graph_objects as go

                hours = list(by_hour.keys())
                wr_vals = [by_hour[h]["win_rate"] for h in hours]
                bar_colors = [
                    COLORS["green"] if w >= 50 else COLORS["red"]
                    for w in wr_vals
                ]
                fig = go.Figure(go.Bar(
                    x=[f"{h}:00" for h in hours],
                    y=wr_vals,
                    marker_color=bar_colors,
                    text=[f"{w}%" for w in wr_vals],
                    textposition="outside",
                ))
                fig.update_layout(
                    height=300,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#c9d1d9", size=11),
                    margin=dict(l=40, r=20, t=30, b=30),
                    yaxis_title="Win Rate %",
                    xaxis_title="Hour (ET)",
                    yaxis=dict(gridcolor="#1e3a5f"),
                )
                st.plotly_chart(fig, use_container_width=True,
                                config={"displayModeBar": False})

            # AI Analysis button
            section_header("AI Analysis")
            _can_ai_1, _cnt_1 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_1:
                render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
            elif st.button("Get AI Analysis", key="ai_win_rate"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    context_lines = [f"Alert win rates ({lookback} days):"]
                    context_lines.append(
                        f"Overall: {overall['win_rate']}% "
                        f"({overall['wins']}W/{overall['losses']}L)"
                    )
                    for sym, d in sorted(
                        by_sym.items(), key=lambda x: x[1]["total"], reverse=True
                    )[:10]:
                        context_lines.append(
                            f"{sym}: {d['win_rate']}% ({d['wins']}W/{d['losses']}L)"
                        )
                    for at, d in by_type.items():
                        context_lines.append(
                            f"{at.replace('_', ' ')}: {d['win_rate']}%"
                        )

                    st.write_stream(ask_ai_insight(
                        "Analyze these alert win rates. Identify patterns: "
                        "which symbols and setups perform best/worst, "
                        "optimal trading hours, and actionable improvements.",
                        "\n".join(context_lines),
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

    except Exception as e:
        st.error(f"Failed to load win rates: {e}")


# ── Tab 2: Fundamentals ──────────────────────────────────────────────────────

with tab_fundamentals:
    section_header(f"Fundamentals \u2014 {hub_symbol}")

    try:
        from analytics.intel_hub import get_fundamentals

        with st.spinner("Loading fundamentals..."):
            fnd = get_fundamentals(hub_symbol)

        if fnd is None:
            empty_state(f"No fundamental data available for {hub_symbol}")
        else:
            if fnd.get("name"):
                st.caption(fnd["name"])

            # Row 1: PE, Market Cap, 52W High, 52W Low
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                pe_val = f"{fnd['pe']:.1f}" if fnd.get("pe") else "N/A"
                colored_metric("P/E Ratio", pe_val, COLORS["blue"])
            with c2:
                colored_metric("Market Cap", fnd.get("market_cap_fmt", "N/A"),
                               COLORS["blue"])
            with c3:
                h52 = f"${fnd['high_52w']:.2f}" if fnd.get("high_52w") else "N/A"
                colored_metric("52W High", h52, COLORS["green"])
            with c4:
                l52 = f"${fnd['low_52w']:.2f}" if fnd.get("low_52w") else "N/A"
                colored_metric("52W Low", l52, COLORS["red"])

            # Row 2: Sector, Beta, Div Yield, Earnings Date
            c5, c6, c7, c8 = st.columns(4)
            with c5:
                colored_metric("Sector", fnd.get("sector") or "N/A",
                               COLORS["purple"])
            with c6:
                beta_val = f"{fnd['beta']:.2f}" if fnd.get("beta") else "N/A"
                colored_metric("Beta", beta_val, COLORS["orange"])
            with c7:
                div_val = (f"{fnd['dividend_yield']:.2%}"
                           if fnd.get("dividend_yield") else "N/A")
                colored_metric("Div Yield", div_val, COLORS["blue"])
            with c8:
                earn_date = fnd.get("earnings_date") or "N/A"
                colored_metric("Earnings Date", earn_date, COLORS["orange"])

            # Earnings proximity warning
            if fnd.get("earnings_date"):
                try:
                    from datetime import date, datetime
                    ed = datetime.strptime(fnd["earnings_date"][:10], "%Y-%m-%d").date()
                    days_until = (ed - date.today()).days
                    if 0 <= days_until <= 5:
                        st.warning(
                            f"Earnings in {days_until} day{'s' if days_until != 1 else ''} "
                            f"({fnd['earnings_date']}). Consider position sizing."
                        )
                except (ValueError, TypeError):
                    pass

            # AI Fundamental Analysis
            section_header("AI Analysis")
            _can_ai_2, _cnt_2 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_2:
                render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
            elif st.button("AI Fundamental Analysis", key="ai_fundamentals"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    context_parts = [f"Fundamentals for {hub_symbol}:"]
                    for k, v in fnd.items():
                        if v is not None and k != "market_cap":
                            context_parts.append(f"  {k}: {v}")

                    st.write_stream(ask_ai_insight(
                        f"Analyze {hub_symbol}'s fundamentals for a day trader. "
                        "How do these metrics affect the trade thesis? "
                        "Flag any risks (earnings, high beta, valuation).",
                        "\n".join(context_parts),
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

    except Exception as e:
        st.error(f"Failed to load fundamentals: {e}")


# ── Tab 3: Weekly View ────────────────────────────────────────────────────────

with tab_weekly:
    section_header(f"Weekly Chart \u2014 {hub_symbol}")

    try:
        from analytics.intel_hub import get_weekly_bars

        with st.spinner("Loading weekly data..."):
            weekly_df, wmas = get_weekly_bars(hub_symbol)

        if weekly_df.empty:
            empty_state(f"No weekly data available for {hub_symbol}")
        else:
            # Price / change metrics
            last_bar = weekly_df.iloc[-1]
            week_close = float(last_bar["Close"])
            week_open = float(last_bar["Open"])
            week_change = week_close - week_open
            week_change_pct = (week_change / week_open * 100) if week_open > 0 else 0

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric(f"{hub_symbol} Weekly Close", f"${week_close:.2f}")
            with m2:
                delta_str = f"{week_change:+.2f} ({week_change_pct:+.1f}%)"
                st.metric("Week Change", delta_str)
            with m3:
                vol = int(last_bar["Volume"]) if pd.notna(last_bar["Volume"]) else 0
                st.metric("Week Volume", f"{vol:,}")

            # --- Weekly Setup Detection ---
            from analytics.intel_hub import analyze_weekly_setup

            setup = analyze_weekly_setup(weekly_df, wmas)

            # Weekly candlestick chart with WMA overlays
            import plotly.graph_objects as go

            n = len(weekly_df)
            x = list(range(n))
            tick_step = max(1, n // 15)
            tick_vals = list(range(0, n, tick_step))
            tick_text = [
                weekly_df.index[i].strftime("%b %Y") for i in tick_vals
            ]

            fig = build_candlestick_fig(
                weekly_df, x, hub_symbol, height=CHART_HEIGHTS["hero"],
            )
            fig.update_xaxes(
                tickvals=tick_vals, ticktext=tick_text,
                row=1, col=1,
            )

            # WMA overlays
            _wma_colors = {10: "#1abc9c", 20: "#f39c12", 50: "#9b59b6"}
            for period in (10, 20, 50):
                if len(weekly_df) >= period:
                    ma_series = weekly_df["Close"].rolling(period).mean()
                    fig.add_trace(go.Scatter(
                        x=x, y=ma_series.values,
                        mode="lines", name=f"WMA{period}",
                        line=dict(color=_wma_colors[period], width=1.5),
                    ), row=1, col=1)

            # Setup level overlays on chart
            if setup["setup_type"] != "NO_SETUP":
                if setup["entry"]:
                    add_level_line(fig, setup["entry"], "Entry", COLORS["blue"], width=1)
                if setup["stop"]:
                    add_level_line(fig, setup["stop"], "Stop", COLORS["red"], width=1)
                if setup["target_1"]:
                    add_level_line(fig, setup["target_1"], "T1", COLORS["green"], width=1)
                if setup["target_2"]:
                    add_level_line(fig, setup["target_2"], "T2", COLORS["green"], dash="dot", width=1)

                # Base range rectangle
                if setup["base_high"] and setup["base_low"]:
                    fig.add_hrect(
                        y0=setup["base_low"], y1=setup["base_high"],
                        fillcolor="rgba(52, 152, 219, 0.12)",
                        line=dict(color="rgba(52, 152, 219, 0.3)", width=1),
                        annotation_text="Base Range",
                        annotation_font=dict(size=9, color="#3498db"),
                        annotation_position="top left",
                        row=1, col=1,
                    )

            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

            # WMA values
            if wmas:
                wma_cols = st.columns(len(wmas))
                for col, (key, val) in zip(wma_cols, wmas.items()):
                    with col:
                        label = key.upper()
                        color = _wma_colors.get(int(key[3:]), COLORS["blue"])
                        colored_metric(label, f"${val:.2f}", color)

            # --- Setup Card ---
            section_header("Weekly Setup")

            if setup["setup_type"] == "NO_SETUP":
                empty_state("No weekly setup detected")
            else:
                _setup_colors = {
                    "BREAKOUT": COLORS["green"],
                    "BASE_FORMING": COLORS["blue"],
                    "PULLBACK": COLORS["orange"],
                }
                setup_color = _setup_colors.get(setup["setup_type"], COLORS["blue"])

                # Setup type badge + score + edge
                s1, s2 = st.columns([1, 2])
                with s1:
                    colored_metric("Setup", setup["setup_type"].replace("_", " "), setup_color)
                with s2:
                    score_color = COLORS["green"] if setup["score"] >= 70 else COLORS["orange"] if setup["score"] >= 55 else COLORS["red"]
                    colored_metric("Score", f"{setup['score_label']} ({setup['score']})", score_color)

                st.caption(setup["edge"])

                # KPI row: base weeks, range, vol contraction, R:R, candle
                k1, k2, k3, k4, k5 = st.columns(5)
                with k1:
                    colored_metric("Base Weeks", str(setup["base_weeks"]) if setup["base_weeks"] else "\u2014", COLORS["blue"])
                with k2:
                    range_str = f"{setup['base_range_pct'] * 100:.1f}%" if setup["base_range_pct"] else "\u2014"
                    colored_metric("Range", range_str, COLORS["blue"])
                with k3:
                    vol_str = "Yes" if setup["volume_contracting"] else "No"
                    vol_color = COLORS["green"] if setup["volume_contracting"] else COLORS["red"]
                    colored_metric("Vol Contracting", vol_str, vol_color)
                with k4:
                    rr_str = f"{setup['risk_reward']:.1f}:1" if setup["risk_reward"] else "\u2014"
                    rr_color = COLORS["green"] if setup["risk_reward"] >= 2.0 else COLORS["orange"]
                    colored_metric("R:R", rr_str, rr_color)
                with k5:
                    pattern, direction = setup["weekly_candle"]
                    candle_str = f"{pattern} / {direction}"
                    colored_metric("Candle", candle_str, COLORS["purple"])

                # Levels row
                l1, l2, l3, l4 = st.columns(4)
                with l1:
                    val = f"${setup['entry']:.2f}" if setup["entry"] else "\u2014"
                    colored_metric("Entry", val, COLORS["blue"])
                with l2:
                    val = f"${setup['stop']:.2f}" if setup["stop"] else "\u2014"
                    colored_metric("Stop", val, COLORS["red"])
                with l3:
                    val = f"${setup['target_1']:.2f}" if setup["target_1"] else "\u2014"
                    colored_metric("Target 1", val, COLORS["green"])
                with l4:
                    val = f"${setup['target_2']:.2f}" if setup["target_2"] else "\u2014"
                    colored_metric("Target 2", val, COLORS["green"])

            # AI Weekly Trend button
            section_header("AI Analysis")
            _can_ai_3, _cnt_3 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_3:
                render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
            elif st.button("AI Weekly Trend", key="ai_weekly"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    context_parts = [f"Weekly chart for {hub_symbol}:"]
                    context_parts.append(
                        f"Last week: O=${week_open:.2f} H=${float(last_bar['High']):.2f} "
                        f"L=${float(last_bar['Low']):.2f} C=${week_close:.2f}"
                    )
                    if len(weekly_df) >= 2:
                        prev = weekly_df.iloc[-2]
                        context_parts.append(
                            f"Prior week: O=${float(prev['Open']):.2f} "
                            f"H=${float(prev['High']):.2f} "
                            f"L=${float(prev['Low']):.2f} "
                            f"C=${float(prev['Close']):.2f}"
                        )
                    for key, val in wmas.items():
                        context_parts.append(f"{key.upper()}: ${val:.2f}")
                    # Include setup context for AI
                    if setup["setup_type"] != "NO_SETUP":
                        context_parts.append(f"Weekly setup: {setup['setup_type']}")
                        context_parts.append(f"Setup edge: {setup['edge']}")
                        context_parts.append(f"Score: {setup['score_label']} ({setup['score']})")
                        if setup["entry"]:
                            context_parts.append(f"Entry: {setup['entry']:.2f}")
                        if setup["stop"]:
                            context_parts.append(f"Stop: {setup['stop']:.2f}")
                        if setup["target_1"]:
                            context_parts.append(f"T1: {setup['target_1']:.2f}")

                    st.write_stream(ask_ai_insight(
                        f"Analyze {hub_symbol}'s weekly chart structure. "
                        "Assess trend direction, MA positioning, key weekly "
                        "levels, and what to watch next week.",
                        "\n".join(context_parts),
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

    except Exception as e:
        st.error(f"Failed to load weekly data: {e}")


# ── Tab 4: AI Coach ──────────────────────────────────────────────────────────

with tab_coach:
    section_header("AI Trade Coach")

    # Quick prompts (enhanced with hub symbol)
    _QUICK_PROMPTS = [
        f"Analyze {hub_symbol} setup",
        "SPY outlook",
        "Review my positions",
        "Best setups today",
    ]

    def _send_prompt(text: str):
        """Append a user message and trigger rerun to process it."""
        st.session_state["coach_messages"].append(
            {"role": "user", "content": text}
        )

    if not st.session_state["coach_messages"]:
        with st.chat_message("assistant"):
            st.write(
                f"Hey! I'm your AI trade coach. I'm currently focused on "
                f"**{hub_symbol}** with full context: fundamentals, S/R levels, "
                f"weekly trend, and historical win rates. Ask me anything!"
            )
        # Auto-send deeplink prompt from Telegram alert link
        _dl_prompt = st.session_state.pop("_deeplink_prompt", None)
        if _dl_prompt:
            if _is_free and user:
                from db import increment_daily_usage
                increment_daily_usage(user["id"], "ai_query")
            _send_prompt(_dl_prompt)
            st.rerun()

    _can_qp, _ = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
    cols = st.columns(len(_QUICK_PROMPTS))
    for col, label in zip(cols, _QUICK_PROMPTS):
        with col:
            if st.button(label, use_container_width=True, key=f"qp_{label}",
                         disabled=(not _can_qp)):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                _send_prompt(label)
                st.rerun()

    # Render conversation history
    for msg in st.session_state["coach_messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Process pending user message
    _needs_response = (
        st.session_state["coach_messages"]
        and st.session_state["coach_messages"][-1]["role"] == "user"
    )

    # Chat input — gate for free users
    _can_chat, _cnt_chat = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)

    if not _can_chat:
        render_inline_upgrade("Unlimited AI Coach conversations — no daily limits", "elite")
    else:
        if prompt := st.chat_input("Ask your trade coach..."):
            if _is_free and user:
                from db import increment_daily_usage
                increment_daily_usage(user["id"], "ai_query")
            with st.chat_message("user"):
                st.write(prompt)
            st.session_state["coach_messages"].append(
                {"role": "user", "content": prompt}
            )
            _needs_response = True

    # Generate assistant response
    if _needs_response:
        with st.chat_message("assistant"):
            try:
                from analytics.trade_coach import (
                    assemble_context,
                    ask_coach,
                    format_system_prompt,
                )

                ctx = assemble_context(hub_symbol=hub_symbol)
                system_prompt = format_system_prompt(ctx)

                # Pro/Elite get Sonnet; free tier gets Haiku (default)
                _coach_model = None
                if not _is_free:
                    from alert_config import CLAUDE_MODEL_SONNET
                    _coach_model = CLAUDE_MODEL_SONNET

                response = st.write_stream(
                    ask_coach(system_prompt, st.session_state["coach_messages"],
                              max_tokens=1024, model=_coach_model)
                )
                st.session_state["coach_messages"].append(
                    {"role": "assistant", "content": response}
                )

            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Coach error: {e}")


# ── Tab 5: Scanner ────────────────────────────────────────────────────────

with tab_scanner:
    section_header("Scanner", "Ranked setups across your watchlist")

    # Auto-refresh during market hours (same pattern as pages/1_Scanner.py)
    from streamlit_autorefresh import st_autorefresh
    from analytics.market_hours import is_market_hours, is_premarket

    _scanner_market_open = is_market_hours()
    _scanner_premarket = is_premarket()
    if _scanner_market_open:
        st_autorefresh(interval=180_000, key="hub_scanner_refresh")  # 3 min
    elif _scanner_premarket:
        st_autorefresh(interval=120_000, key="hub_scanner_pm_refresh")  # 2 min

    # Session state for persisting scan results across tab switches
    if "scanner_blobs" not in st.session_state:
        st.session_state["scanner_blobs"] = None

    scan_col, status_col = st.columns([1, 2])
    with scan_col:
        do_scan = st.button("Scan Watchlist", type="primary", key="btn_scan_watchlist")
    with status_col:
        from config import is_crypto_alert_symbol

        has_crypto = any(is_crypto_alert_symbol(s) for s in sym_options)
        if has_crypto:
            st.caption("Crypto symbols scan 24/7. Stocks use prior day data when market is closed.")
        else:
            st.caption("Scans all watchlist symbols for the best setups.")

    # Auto-scan during market hours on first load
    if not do_scan and _scanner_market_open and st.session_state["scanner_blobs"] is None:
        do_scan = True

    if do_scan:
        try:
            from analytics.intel_hub import (
                assemble_scanner_context,
                compute_scanner_rank,
            )

            with st.spinner("Gathering data for all symbols..."):
                blobs = assemble_scanner_context(sym_options, user_id=_uid)

            if not blobs:
                empty_state("No scannable symbols found (need prior day data)")
            else:
                # Compute rank for each blob and attach it
                for b in blobs:
                    b["rank"] = compute_scanner_rank(b)
                # Sort by rank_score descending
                blobs.sort(key=lambda b: b["rank"]["rank_score"], reverse=True)
                st.session_state["scanner_blobs"] = blobs

        except Exception as e:
            st.error(f"Scanner error: {e}")

    # Display persisted results (survives tab switches)
    blobs = st.session_state.get("scanner_blobs")

    if blobs:
        section_header("Ranked Setups")

        for idx, blob in enumerate(blobs):
            sym = blob["symbol"]
            rank = blob.get("rank", {})
            rank_score = rank.get("rank_score", 0)
            rank_label = rank.get("rank_label", "C")
            is_invalidated = blob.get("invalidated", False)

            label_color = {"A+": "green", "A": "blue", "B": "orange", "C": "red"}.get(rank_label, "")
            header = f"#{idx + 1}: {sym} — {rank_label} ({rank_score})"
            if is_invalidated:
                header += " — INVALIDATED"

            with st.expander(header, expanded=(idx < 3)):
                # Invalidation banner
                if is_invalidated:
                    st.error(
                        "PLAN INVALIDATED — Stop was hit today. "
                        "Original levels no longer valid."
                    )

                # KPI row
                plan = blob.get("plan") or {}
                intra = blob.get("intraday", {})
                prior = blob.get("prior_day", {})

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    price = intra.get("current_price") or prior.get("close") or 0
                    colored_metric("Price", f"${price:.2f}" if price else "N/A", COLORS["blue"])
                with k2:
                    score_color = COLORS["green"] if rank_score >= 70 else COLORS["orange"] if rank_score >= 50 else COLORS["red"]
                    colored_metric("Rank", f"{rank_label} ({rank_score})", score_color)
                with k3:
                    nearest = rank.get("nearest_ma", "N/A")
                    dist = rank.get("nearest_ma_dist_pct", 0)
                    colored_metric("Nearest MA", f"{nearest} ({dist:.1f}%)", COLORS["purple"])
                with k4:
                    chg = intra.get("change_pct", 0)
                    chg_color = COLORS["green"] if chg >= 0 else COLORS["red"]
                    colored_metric("Day Change", f"{chg:+.2f}%", chg_color)

                # Edge line
                edge = rank.get("edge", "")
                if edge:
                    st.caption(edge)

                # Key levels row (strike-through if invalidated)
                if plan:
                    l1, l2, l3, l4 = st.columns(4)
                    _lvl_prefix = "~~" if is_invalidated else ""
                    _lvl_suffix = "~~" if is_invalidated else ""
                    with l1:
                        entry = plan.get("entry")
                        val = f"${entry:.2f}" if entry else "\u2014"
                        colored_metric("Entry", f"{_lvl_prefix}{val}{_lvl_suffix}", COLORS["blue"])
                    with l2:
                        stop = plan.get("stop")
                        val = f"${stop:.2f}" if stop else "\u2014"
                        colored_metric("Stop", f"{_lvl_prefix}{val}{_lvl_suffix}", COLORS["red"])
                    with l3:
                        t1 = plan.get("target_1")
                        val = f"${t1:.2f}" if t1 else "\u2014"
                        colored_metric("Target 1", f"{_lvl_prefix}{val}{_lvl_suffix}", COLORS["green"])
                    with l4:
                        t2 = plan.get("target_2")
                        val = f"${t2:.2f}" if t2 else "\u2014"
                        colored_metric("Target 2", f"{_lvl_prefix}{val}{_lvl_suffix}", COLORS["green"])

                # Reprojected plan (if invalidated + support found)
                reproj = blob.get("reprojected_plan")
                if is_invalidated and reproj:
                    st.markdown(
                        f"**Re-projected Plan** — next support at "
                        f"**{reproj['support_label']}** ({reproj['support']:.2f})"
                    )
                    r1, r2, r3, r4 = st.columns(4)
                    with r1:
                        colored_metric("New Entry", f"${reproj['entry']:.2f}", COLORS["orange"])
                    with r2:
                        colored_metric("New Stop", f"${reproj['stop']:.2f}", COLORS["red"])
                    with r3:
                        colored_metric("New T1", f"${reproj['target_1']:.2f}", COLORS["green"])
                    with r4:
                        rr = reproj.get("rr_ratio", 0)
                        colored_metric("R:R", f"{rr:.1f}:1", COLORS["orange"])
                elif is_invalidated:
                    st.warning("No valid support below. Sit out.")

                # Today's alert badges
                alerts = blob.get("alerts_today", [])
                if alerts:
                    buy_n = sum(1 for a in alerts if a.get("direction") == "BUY")
                    sell_n = sum(1 for a in alerts if a.get("direction") == "SELL")
                    badge_parts = []
                    if buy_n:
                        badge_parts.append(f"🟢 {buy_n} BUY")
                    if sell_n:
                        badge_parts.append(f"🔴 {sell_n} SELL")
                    st.caption(f"Today's alerts: {' | '.join(badge_parts)}")

                # Mini candlestick chart
                try:
                    from analytics.intraday_data import fetch_intraday

                    chart_df = fetch_intraday(sym)
                    if chart_df.empty:
                        import yfinance as yf

                        hist = yf.Ticker(sym).history(period="1mo")
                        if not hist.empty:
                            from analytics.intraday_data import _normalize_index_to_et
                            hist = _normalize_index_to_et(hist)
                            chart_df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

                    if not chart_df.empty:
                        n = len(chart_df)
                        x = list(range(n))
                        tick_step = max(1, n // 10)
                        tick_vals = list(range(0, n, tick_step))
                        tick_text = [
                            chart_df.index[i].strftime("%H:%M")
                            if n <= 80
                            else chart_df.index[i].strftime("%m/%d")
                            for i in tick_vals
                        ]

                        fig = build_candlestick_fig(
                            chart_df, x, sym,
                            height=CHART_HEIGHTS.get("compact", 300),
                            show_volume=False,
                        )
                        fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text)

                        # Overlay plan levels (or reprojected if invalidated)
                        active_plan = reproj if (is_invalidated and reproj) else plan
                        if active_plan.get("entry"):
                            add_level_line(fig, active_plan["entry"], "Entry", COLORS["blue"], width=1)
                        if active_plan.get("stop"):
                            add_level_line(fig, active_plan["stop"], "Stop", COLORS["red"], width=1)
                        if active_plan.get("target_1"):
                            add_level_line(fig, active_plan["target_1"], "T1", COLORS["green"], width=1)
                        if active_plan.get("target_2"):
                            add_level_line(fig, active_plan["target_2"], "T2", COLORS["green"], dash="dot", width=1)

                        # Top 3 S/R levels
                        sr_levels = blob.get("sr_levels", [])
                        for lvl in sr_levels[:3]:
                            sr_color = COLORS["green"] if lvl["type"] == "support" else COLORS["red"]
                            add_level_line(fig, lvl["level"], lvl["label"], sr_color, width=1, dash="dot")

                        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
                except Exception as e:
                    st.caption(f"Chart unavailable: {e}")
