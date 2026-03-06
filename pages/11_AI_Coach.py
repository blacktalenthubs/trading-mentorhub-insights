"""AI Trade Coach — chat with an AI coach using your real trading data."""

from __future__ import annotations

import streamlit as st

import ui_theme

user = ui_theme.setup_page("ai_coach")

ui_theme.page_header(
    "AI Trade Coach",
    "Ask questions about your trades, positions, and market conditions",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "coach_messages" not in st.session_state:
    st.session_state["coach_messages"] = []
if "coach_context" not in st.session_state:
    st.session_state["coach_context"] = None

# ---------------------------------------------------------------------------
# Sidebar — context summary + controls
# ---------------------------------------------------------------------------

with st.sidebar:
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
            st.metric("Total P&L", "—")
            st.metric("Win Rate", "—")

        # SPY regime
        spy = ctx.get("spy_context")
        if spy:
            st.metric("SPY Regime", spy.get("regime", "—"))
        else:
            st.metric("SPY Regime", "—")

    except Exception:
        st.caption("Could not load context")

# ---------------------------------------------------------------------------
# Quick prompts + welcome message
# ---------------------------------------------------------------------------

_QUICK_PROMPTS = [
    "SPY outlook",
    "Review my positions",
    "Yesterday recap",
    "Best setups today",
]


def _send_prompt(text: str):
    """Append a user message and trigger rerun to process it."""
    st.session_state["coach_messages"].append({"role": "user", "content": text})


if not st.session_state["coach_messages"]:
    with st.chat_message("assistant"):
        st.write(
            "Hey! I'm your AI trade coach. I can see your open positions, "
            "trade history, today's watchlist, and market regime."
        )

cols = st.columns(len(_QUICK_PROMPTS))
for col, label in zip(cols, _QUICK_PROMPTS):
    with col:
        if st.button(label, use_container_width=True):
            _send_prompt(label)
            st.rerun()

# ---------------------------------------------------------------------------
# Render conversation history
# ---------------------------------------------------------------------------

for msg in st.session_state["coach_messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ---------------------------------------------------------------------------
# Process pending user message (no assistant response yet)
# ---------------------------------------------------------------------------

_needs_response = (
    st.session_state["coach_messages"]
    and st.session_state["coach_messages"][-1]["role"] == "user"
)

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask your trade coach..."):
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state["coach_messages"].append({"role": "user", "content": prompt})
    _needs_response = True

# ---------------------------------------------------------------------------
# Generate assistant response
# ---------------------------------------------------------------------------

if _needs_response:
    with st.chat_message("assistant"):
        try:
            from analytics.trade_coach import (
                assemble_context,
                ask_coach,
                format_system_prompt,
            )

            ctx = assemble_context()
            system_prompt = format_system_prompt(ctx)

            response = st.write_stream(
                ask_coach(system_prompt, st.session_state["coach_messages"])
            )
            st.session_state["coach_messages"].append(
                {"role": "assistant", "content": response}
            )

        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Coach error: {e}")
