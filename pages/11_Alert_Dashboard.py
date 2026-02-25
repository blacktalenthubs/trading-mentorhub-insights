"""Alert Dashboard — view today's alerts, alert history, monitor status, test notifications."""

import streamlit as st
import pandas as pd
from datetime import datetime

from auth import require_auth
from db import init_db
from alerting.alert_store import get_alerts_today, get_alerts_history, get_monitor_status
from alert_config import ALERT_WATCHLIST, POLL_INTERVAL_MINUTES

init_db()
user = require_auth()

st.title("Alert Dashboard")

# ---------------------------------------------------------------------------
# Monitor Status
# ---------------------------------------------------------------------------

st.subheader("Monitor Status")
status = get_monitor_status()

if status:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", status["status"].replace("_", " ").title())
    col2.metric("Last Poll", status["last_poll_at"] or "Never")
    col3.metric("Symbols Checked", status["symbols_checked"])
    col4.metric("Alerts Fired", status["alerts_fired"])
else:
    st.info(
        "Monitor has not run yet. Start it with:\n\n"
        "```\npython monitor.py            # live mode\n"
        "python monitor.py --dry-run  # test without notifications\n```"
    )

st.caption(
    f"Watchlist: {', '.join(ALERT_WATCHLIST)} | "
    f"Poll interval: {POLL_INTERVAL_MINUTES} min"
)

st.divider()

# ---------------------------------------------------------------------------
# Today's Alerts
# ---------------------------------------------------------------------------

st.subheader("Today's Alerts")
today_alerts = get_alerts_today()

if today_alerts:
    for alert in today_alerts:
        direction = alert["direction"]
        color = "#2ecc71" if direction == "BUY" else "#e74c3c"
        icon = "+" if direction == "BUY" else "-"

        with st.container():
            cols = st.columns([1, 2, 3, 2, 2])
            cols[0].markdown(
                f"<span style='color:{color};font-weight:bold;font-size:1.1em'>"
                f"{direction}</span>",
                unsafe_allow_html=True,
            )
            cols[1].markdown(f"**{alert['symbol']}**")
            cols[2].write(alert["alert_type"].replace("_", " ").title())
            cols[3].write(f"${alert['price']:.2f}")
            cols[4].write(alert["created_at"])

            if alert.get("entry"):
                with st.expander("Details"):
                    detail_cols = st.columns(4)
                    detail_cols[0].metric("Entry", f"${alert['entry']:.2f}")
                    if alert.get("stop"):
                        detail_cols[1].metric("Stop", f"${alert['stop']:.2f}")
                    if alert.get("target_1"):
                        detail_cols[2].metric("T1", f"${alert['target_1']:.2f}")
                    if alert.get("target_2"):
                        detail_cols[3].metric("T2", f"${alert['target_2']:.2f}")

                    notif = []
                    if alert.get("notified_email"):
                        notif.append("Email sent")
                    if alert.get("notified_sms"):
                        notif.append("SMS sent")
                    if notif:
                        st.caption(" | ".join(notif))

                    if alert.get("message"):
                        st.write(alert["message"])

    # Summary KPIs
    buy_count = sum(1 for a in today_alerts if a["direction"] == "BUY")
    sell_count = sum(1 for a in today_alerts if a["direction"] == "SELL")

    st.divider()
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Alerts", len(today_alerts))
    kpi2.metric("BUY Signals", buy_count)
    kpi3.metric("SELL Signals", sell_count)
else:
    st.info("No alerts fired today.")

st.divider()

# ---------------------------------------------------------------------------
# Alert History
# ---------------------------------------------------------------------------

st.subheader("Alert History")

history = get_alerts_history(limit=200)

if history:
    df = pd.DataFrame(history)
    display_cols = [
        "session_date", "symbol", "direction", "alert_type",
        "price", "entry", "stop", "target_1", "target_2",
        "notified_email", "notified_sms", "created_at",
    ]
    existing = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[existing],
        use_container_width=True,
        hide_index=True,
        column_config={
            "price": st.column_config.NumberColumn(format="$%.2f"),
            "entry": st.column_config.NumberColumn(format="$%.2f"),
            "stop": st.column_config.NumberColumn(format="$%.2f"),
            "target_1": st.column_config.NumberColumn(format="$%.2f"),
            "target_2": st.column_config.NumberColumn(format="$%.2f"),
            "notified_email": st.column_config.CheckboxColumn("Email"),
            "notified_sms": st.column_config.CheckboxColumn("SMS"),
        },
    )
else:
    st.info("No alert history yet.")

# ---------------------------------------------------------------------------
# Test Notifications
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Test Notifications")

st.caption("Send a test alert to verify your email and SMS configuration.")

if st.button("Send Test Alert"):
    from analytics.intraday_rules import AlertSignal, AlertType
    from alerting.notifier import send_email, send_sms

    test_signal = AlertSignal(
        symbol="TEST",
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=100.00,
        entry=100.00,
        stop=99.00,
        target_1=101.00,
        target_2=102.00,
        confidence="high",
        message="Test alert from Alert Dashboard — ignore this message",
    )

    with st.spinner("Sending test email..."):
        email_ok = send_email(test_signal)

    with st.spinner("Sending test SMS..."):
        sms_ok = send_sms(test_signal)

    if email_ok:
        st.success("Test email sent successfully!")
    else:
        st.warning("Email failed — check .env SMTP settings")

    if sms_ok:
        st.success("Test SMS sent successfully!")
    else:
        st.warning("SMS failed — check .env Twilio settings")
