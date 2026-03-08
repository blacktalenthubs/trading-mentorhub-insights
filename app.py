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

# Resolve user tier for lock badges + sidebar display
from db import get_user_tier

tier = get_user_tier(user["id"])
_user_level = ui_theme.TIER_LEVELS.get(tier, 0)


def _page(file: str, title: str, icon: str, tier_req: str = "free", **kw) -> st.Page:
    """Build st.Page, appending lock icon if user's tier is insufficient."""
    if ui_theme.TIER_LEVELS.get(tier_req, 0) > _user_level:
        title = f"{title} \U0001F512"
    return st.Page(file, title=title, icon=icon, **kw)


# Build grouped navigation
pg = st.navigation(
    {
        "": [
            _page("pages/home.py", "Dashboard", ":material/dashboard:", "free", default=True),
        ],
        "Signals": [
            _page("pages/1_Scanner.py", "Scanner", ":material/radar:", "free"),
            _page("pages/10_Swing_Trades.py", "Swing Trades", ":material/trending_up:", "pro"),
        ],
        "Analysis": [
            _page("pages/7_Charts.py", "Charts", ":material/show_chart:", "free"),
            _page("pages/5_Backtest.py", "Backtest", ":material/replay:", "elite"),
        ],
        "Trading": [
            _page("pages/8_Real_Trades.py", "Real Trades", ":material/attach_money:", "pro"),
            _page("pages/6_Paper_Trading.py", "Paper Trading", ":material/edit_note:", "elite"),
        ],
        "Journal": [
            _page("pages/9_Alerts.py", "Alert History", ":material/notifications:", "pro"),
            _page("pages/2_Scorecard.py", "Scorecard", ":material/assessment:", "pro"),
            _page("pages/3_History.py", "History", ":material/history:", "pro"),
            _page("pages/4_Import.py", "Import", ":material/upload_file:", "pro"),
        ],
        "AI": [
            _page("pages/11_AI_Coach.py", "AI Coach", ":material/psychology:", "elite"),
        ],
        "Account": [
            _page("pages/12_Settings.py", "Settings", ":material/settings:", "free"),
        ],
    }
)
ui_theme._render_sidebar_user(user, tier)

pg.run()
