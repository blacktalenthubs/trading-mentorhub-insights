"""Trade Analytics Dashboard - Streamlit entry point."""

import streamlit as st
from db import init_db

st.set_page_config(
    page_title="Trade Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.title("Trade Analytics Dashboard")
st.caption("Individual Account (145610192) - Stocks & ETFs")

st.markdown("""
**Pages:**
- **Overview** - P&L summary, equity curve with drawdown, holding period breakdown
- **Trade Journal** - Every trade with daily P&L calendar, entry/exit, streaks, trade tagging
- **Trade Analysis** - Filterable trade table by symbol, category, month, source
- **Strategy Performance** - Day trade vs swing, strategy tags, overtrading detection
- **Risk Analysis** - Wash sales, concentration, biggest wins/losses
- **Monthly Comparison** - Month-over-month trends, strategy evolution
- **Import** - Upload and parse PDF statements
- **Symbol Deep-Dive** - Select any symbol for full trade history and should-I-keep-trading verdict
- **Pre-Market Planner** - Inside/outside day analysis, key levels, entries/stops/targets, risk calc
""")

from db import get_focus_account_trades

df = get_focus_account_trades()

if df.empty:
    st.info("No trade data imported yet. Go to the **Import** page to upload your PDFs.")
else:
    total_pnl = df["realized_pnl"].sum()
    winners = df[df["realized_pnl"] > 0]
    losers = df[df["realized_pnl"] < 0]
    win_rate = len(winners) / len(df) * 100 if len(df) > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total P&L", f"${total_pnl:,.2f}",
                delta_color="normal" if total_pnl >= 0 else "inverse")
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Trades", f"{len(df)}")
    col4.metric("Avg P&L/Trade", f"${df['realized_pnl'].mean():,.2f}")
