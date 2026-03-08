"""TradeCoPilot — Navigation shell."""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(
    page_title="TradeCoPilot",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

from db import init_db

init_db()

import ui_theme

ui_theme.inject_custom_css()

# Start monitor thread (idempotent)
if not os.environ.get("DISABLE_MONITOR_THREAD", "").lower() == "true":
    import monitor_thread

    monitor_thread.start()

# Auth gate — unauthenticated users see landing page
from auth import get_current_user

user = get_current_user()

if user is None:
    ui_theme.render_landing_page()
    st.stop()

# Signal to setup_page() that the nav shell handles branding + user info
st.session_state["_nav_mode"] = True

# Sidebar branding
with st.sidebar:
    ui_theme.sidebar_branding()

# Build grouped navigation
pg = st.navigation(
    {
        "": [
            st.Page("pages/home.py", title="Dashboard", icon=":material/dashboard:", default=True),
        ],
        "Signals": [
            st.Page("pages/1_Scanner.py", title="Scanner", icon=":material/radar:"),
            st.Page("pages/10_Swing_Trades.py", title="Swing Trades", icon=":material/trending_up:"),
        ],
        "Analysis": [
            st.Page("pages/7_Charts.py", title="Charts", icon=":material/show_chart:"),
            st.Page("pages/5_Backtest.py", title="Backtest", icon=":material/replay:"),
        ],
        "Trading": [
            st.Page("pages/8_Real_Trades.py", title="Real Trades", icon=":material/attach_money:"),
            st.Page("pages/6_Paper_Trading.py", title="Paper Trading", icon=":material/edit_note:"),
        ],
        "Journal": [
            st.Page("pages/9_Alerts.py", title="Alert History", icon=":material/notifications:"),
            st.Page("pages/2_Scorecard.py", title="Scorecard", icon=":material/assessment:"),
            st.Page("pages/3_History.py", title="History", icon=":material/history:"),
            st.Page("pages/4_Import.py", title="Import", icon=":material/upload_file:"),
        ],
        "AI": [
            st.Page("pages/11_AI_Coach.py", title="AI Coach", icon=":material/psychology:"),
        ],
        "Account": [
            st.Page("pages/12_Settings.py", title="Settings", icon=":material/settings:"),
        ],
    }
)

# Sidebar user info (below navigation links)
from db import get_user_tier

tier = get_user_tier(user["id"])
ui_theme._render_sidebar_user(user, tier)

pg.run()
