"""Centralized UI theme for TradeCoPilot — single source of truth for styling."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLORS = {
    "green": "#2ecc71",
    "green_dark": "#27ae60",
    "red": "#e74c3c",
    "red_dark": "#a93226",
    "blue": "#3498db",
    "orange": "#f39c12",
    "orange_dark": "#e67e22",
    "purple": "#9b59b6",
    "bg_primary": "#0e1117",
    "bg_secondary": "#1a1a2e",
    "bg_card": "#16213e",
    "border": "#1e3a5f",
    "text_muted": "#888",
}

DIRECTION_DISPLAY = {
    "BUY": ("Potential Entry", "#2ecc71"),
    "SELL": ("Exit Zone", "#e74c3c"),
    "SHORT": ("Potential Short", "#9b59b6"),
    "NOTICE": ("Market Update", "#3498db"),
}


def display_direction(direction: str) -> tuple[str, str]:
    """Return (label, color) for a direction. Used by UI + notifications."""
    return DIRECTION_DISPLAY.get(direction, (direction, "#888"))


CHART_HEIGHTS = {
    "hero": 450,
    "standard": 380,
    "compact": 300,
    "mini": 200,
    "full": 700,
}

PLOTLY_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToAdd": ["drawline", "eraseshape"],
}

PLOTLY_CONFIG_MINIMAL = {
    "scrollZoom": True,
    "displayModeBar": False,
    "displaylogo": False,
}


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def inject_custom_css():
    """Inject global CSS to style the app like a professional trading terminal."""
    st.markdown("""
    <style>
    /* ── Load Inter font ──────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── Hide Streamlit branding (keep header for sidebar toggle) ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stStatusWidget"] {visibility: hidden;}
    /* Hide header text but keep the sidebar collapse/expand button */
    header [data-testid="stHeader"] {background: transparent;}
    header {background: transparent !important;}

    /* ── Reduce top padding ───────────────────────────────────────── */
    .block-container {
        padding-top: 1.5rem !important;
    }

    /* ── Metric cards ─────────────────────────────────────────────── */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        border: 1px solid #1e3a5f;
        border-radius: 8px;
        padding: 12px 16px;
        transition: box-shadow 0.2s ease;
    }
    [data-testid="stMetric"]:hover {
        box-shadow: 0 0 12px rgba(52, 152, 219, 0.15);
    }
    [data-testid="stMetric"] label {
        text-transform: uppercase;
        font-size: 0.75rem !important;
        letter-spacing: 0.05em;
        color: #888 !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-weight: 600;
    }

    /* ── Dataframes ───────────────────────────────────────────────── */
    [data-testid="stDataFrame"] {
        border: 1px solid #1e3a5f;
        border-radius: 8px;
    }

    /* ── Sidebar ──────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0e1117 0%, #1a1a2e 100%);
        border-right: 1px solid #1e3a5f;
    }
    /* Compact sidebar buttons (watchlist remove) */
    [data-testid="stSidebar"] .stButton > button {
        padding: 2px 6px;
        font-size: 0.72rem;
        min-height: 0;
        color: #f85149;
        background: transparent;
        border: 1px solid #f8514930;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: #f8514920;
        border-color: #f85149;
    }
    /* Tighter sidebar column gaps */
    [data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        gap: 0.25rem;
    }

    /* ── Tabs — pill style ────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 6px 16px;
        font-size: 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1e3a5f;
    }

    /* ── Expanders ────────────────────────────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid #1e3a5f;
        border-radius: 8px;
        background: rgba(22, 33, 62, 0.3);
    }

    /* ── Custom scrollbar ─────────────────────────────────────────── */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #0e1117;
    }
    ::-webkit-scrollbar-thumb {
        background: #1e3a5f;
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #2a5a8f;
    }

    /* ── Responsive: tablet ─────────────────────────────────────── */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        [data-testid="stMetric"] {
            padding: 8px 10px;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.1rem !important;
        }
    }

    /* ── Responsive: mobile ─────────────────────────────────────── */
    @media (max-width: 480px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 1rem !important;
        }
        [data-testid="stMetric"] {
            padding: 6px 8px;
        }
        [data-testid="stMetric"] label {
            font-size: 0.65rem !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1rem !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper components
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str = ""):
    """Render a gradient branded header with optional subtitle."""
    subtitle_html = f"<p style='color:#888;font-size:0.95rem;margin:0'>{subtitle}</p>" if subtitle else ""
    st.markdown(f"""
    <div style='margin-bottom:1rem'>
        <h1 style='
            background: linear-gradient(90deg, #3498db, #2ecc71);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2rem;
            font-weight: 700;
            margin: 0;
            line-height: 1.2;
        '>&#9889; {title}</h1>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, description: str = ""):
    """Render a styled section divider with bottom border accent."""
    desc_html = f"<span style='color:#888;font-size:0.85rem;margin-left:12px'>{description}</span>" if description else ""
    st.markdown(f"""
    <div style='
        border-bottom: 2px solid #1e3a5f;
        padding-bottom: 6px;
        margin: 1.2rem 0 0.8rem 0;
    '>
        <h3 style='margin:0;font-size:1.15rem;font-weight:600;color:#fafafa'>
            {title}{desc_html}
        </h3>
    </div>
    """, unsafe_allow_html=True)


def colored_metric(label: str, value: str, color: str = "#3498db", delta: str = ""):
    """Render a KPI card with left accent border."""
    delta_html = f"<div style='color:#888;font-size:0.75rem;margin-top:2px'>{delta}</div>" if delta else ""
    st.markdown(f"""
    <div style='
        border-left: 3px solid {color};
        background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin-bottom: 8px;
    '>
        <div style='text-transform:uppercase;font-size:0.7rem;letter-spacing:0.05em;color:#888'>{label}</div>
        <div style='font-size:1.3rem;font-weight:600;color:{color}'>{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def empty_state(message: str, icon: str = "info"):
    """Render a centered empty state card with icon."""
    icon_map = {
        "info": "&#8505;&#65039;",
        "warning": "&#9888;&#65039;",
        "success": "&#9989;",
        "error": "&#10060;",
    }
    icon_char = icon_map.get(icon, icon_map["info"])
    st.markdown(f"""
    <div style='
        text-align: center;
        padding: 2rem 1.5rem;
        background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        border: 1px solid #1e3a5f;
        border-radius: 10px;
        margin: 1rem 0;
        color: #888;
    '>
        <div style='font-size:1.8rem;margin-bottom:8px'>{icon_char}</div>
        <div style='font-size:0.95rem'>{message}</div>
    </div>
    """, unsafe_allow_html=True)


def sidebar_branding():
    """Render the TradeCoPilot logo block in the sidebar."""
    st.markdown("""
    <div style='
        text-align: center;
        padding: 12px 0 16px 0;
        margin-bottom: 8px;
        border-bottom: 1px solid #1e3a5f;
    '>
        <div style='font-size:1.4rem;font-weight:700;
            background: linear-gradient(90deg, #3498db, #2ecc71);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        '>&#9889; TradeCoPilot</div>
        <div style='color:#888;font-size:0.75rem;letter-spacing:0.08em;text-transform:uppercase'>
            AI-Powered Trade Intelligence
        </div>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar watchlist widget
# ---------------------------------------------------------------------------

FREE_WATCHLIST_MAX = 5


def render_sidebar_watchlist(user: dict | None) -> list[str]:
    """Render a polished watchlist widget in the sidebar. Returns current symbols."""
    from db import (
        get_watchlist, add_to_watchlist, remove_from_watchlist,
        set_watchlist, get_user_tier,
    )

    _uid = user["id"] if user else None
    tier = get_user_tier(_uid) if _uid else "free"

    # Init session state
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = get_watchlist(_uid)

    wl = st.session_state["watchlist"]
    count = len(wl)
    is_free = tier == "free"
    at_limit = is_free and count >= FREE_WATCHLIST_MAX

    # ── Header with count ──
    limit_text = f" / {FREE_WATCHLIST_MAX}" if is_free else ""
    header_color = "#f85149" if at_limit else "#3498db"
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"margin-bottom:6px'>"
        f"<span style='font-weight:600;font-size:0.95rem;color:#fafafa'>Watchlist</span>"
        f"<span style='background:{header_color}20;color:{header_color};"
        f"padding:2px 8px;border-radius:10px;font-size:0.72rem;font-weight:600'>"
        f"{count}{limit_text}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Add symbol ──
    add_col, btn_col = st.columns([3, 1])
    with add_col:
        new_sym = st.text_input(
            "Add symbol", key="add_sym_input",
            label_visibility="collapsed", placeholder="Add symbol...",
            disabled=at_limit,
        )
    with btn_col:
        add_clicked = st.button(
            "+", key="add_sym_btn", use_container_width=True,
            disabled=at_limit,
        )

    if add_clicked and new_sym:
        sym_clean = new_sym.strip().upper()
        if sym_clean and sym_clean not in wl:
            add_to_watchlist(sym_clean, _uid)
            st.session_state["watchlist"].append(sym_clean)
            st.rerun()

    if at_limit:
        st.markdown(
            "<div style='font-size:0.72rem;color:#f85149;margin:-8px 0 4px 0'>"
            "Free tier limit reached &mdash; "
            "<a href='/Settings' target='_self' style='color:#3498db'>upgrade</a>"
            " for unlimited symbols</div>",
            unsafe_allow_html=True,
        )

    # ── Vertical symbol list ──
    if wl:
        from config import INDEX_ETF, MEGA_CAP, SPECULATIVE
        _cat_colors = {
            "index_etf": "#3498db",
            "mega_cap": "#2ecc71",
            "speculative": "#e74c3c",
            "other": "#888",
        }

        def _cat(sym: str) -> str:
            if sym in INDEX_ETF:
                return "index_etf"
            if sym in MEGA_CAP:
                return "mega_cap"
            if sym in SPECULATIVE:
                return "speculative"
            return "other"

        remove_sym = None
        for i, sym in enumerate(wl):
            fg = _cat_colors[_cat(sym)]
            sym_col, rm_col = st.columns([5, 1])
            with sym_col:
                st.markdown(
                    f"<div style='padding:4px 0;font-weight:600;font-size:0.85rem;"
                    f"color:{fg};border-bottom:1px solid #1e3a5f22'>"
                    f"&#x25CF; {sym}</div>",
                    unsafe_allow_html=True,
                )
            with rm_col:
                if st.button("\u2715", key=f"rm_{sym}_{i}"):
                    remove_sym = sym
        if remove_sym is not None:
            remove_from_watchlist(remove_sym, _uid)
            st.session_state["watchlist"].remove(remove_sym)
            st.rerun()
    else:
        st.caption("No symbols yet. Add one above.")

    # ── Bulk edit ──
    with st.expander("Bulk Edit"):
        bulk_text = st.text_area(
            "Symbols (comma-separated)",
            value=", ".join(wl),
            height=68,
            key="bulk_edit_area",
            label_visibility="collapsed",
        )
        if st.button("Apply", key="bulk_apply", use_container_width=True):
            parsed = [s.strip().upper() for s in bulk_text.split(",") if s.strip()]
            if is_free and len(parsed) > FREE_WATCHLIST_MAX:
                parsed = parsed[:FREE_WATCHLIST_MAX]
                st.warning(f"Free tier limited to {FREE_WATCHLIST_MAX} symbols. List trimmed.")
            set_watchlist(parsed, _uid)
            st.session_state["watchlist"] = parsed
            st.rerun()

    return list(st.session_state["watchlist"])


def welcome_banner():
    """Dismissible getting-started banner for first-time users."""
    if st.session_state.get("_welcome_dismissed"):
        return
    with st.expander("Getting Started", expanded=True):
        actions = [
            ("&#128200;", "Scanner", "Scored trade plans with entry, stop, and targets for your watchlist.", "/Scanner"),
            ("&#128276;", "Alerts", "Real-time signals delivered to Telegram and email during market hours.", "/Alerts"),
            ("&#127919;", "Scorecard", "Track win rate, R:R ratio, and equity curve across all your trades.", "/Scorecard"),
        ]
        cols = st.columns(3)
        for col, (icon, title, desc, href) in zip(cols, actions):
            with col:
                st.markdown(
                    f"<a href='{href}' target='_self' style='text-decoration:none'>"
                    f"<div style='"
                    f"background:linear-gradient(135deg,#16213e 0%,#1a1a2e 100%);"
                    f"border:1px solid #1e3a5f;border-radius:10px;"
                    f"padding:1.2rem;min-height:120px;"
                    f"transition:box-shadow 0.2s ease'>"
                    f"<div style='font-size:1.5rem;margin-bottom:6px'>{icon}</div>"
                    f"<div style='font-weight:600;color:#fafafa;margin-bottom:4px'>{title}</div>"
                    f"<div style='color:#888;font-size:0.85rem'>{desc}</div>"
                    f"</div></a>",
                    unsafe_allow_html=True,
                )
        if st.button("Got it!", key="_dismiss_welcome"):
            st.session_state["_welcome_dismissed"] = True
            st.rerun()


def render_signal_card(
    *,
    symbol: str,
    score_label: str,
    score: int,
    status_label: str,
    status_color: str,
    price: float,
    support_level: float,
    support_name: str,
    distance_pct: float,
    ma20: float | None,
    ma50: float | None,
    is_live: bool = False,
    pattern: str = "normal",
) -> None:
    """Render a compact signal card for the Scanner page.

    Matches the Alerts page _render_card() styling: dark background, left
    colored border, pill badges.
    """
    # Score badge color
    if score >= 90:
        score_color = "#2ecc71"
    elif score >= 75:
        score_color = "#2ecc71"
    elif score >= 50:
        score_color = "#f39c12"
    else:
        score_color = "#e74c3c"

    # MA trend indicator
    ma_parts = []
    above_count = 0
    if ma20 is not None:
        if price > ma20:
            above_count += 1
        ma_parts.append(f"20MA ${ma20:,.2f}")
    if ma50 is not None:
        if price > ma50:
            above_count += 1
        ma_parts.append(f"50MA ${ma50:,.2f}")
    if above_count == 2:
        ma_trend = "Above MAs"
    elif above_count == 1:
        ma_trend = "Mixed MAs"
    else:
        ma_trend = "Below MAs"

    # Optional badges
    badges = ""
    if is_live:
        badges += (
            "<span style='background:#2ecc7130;color:#2ecc71;padding:1px 6px;"
            "border-radius:3px;font-size:0.7rem;font-weight:600;margin-left:6px'>LIVE</span>"
        )
    if pattern == "inside":
        badges += (
            "<span style='background:#9b59b630;color:#9b59b6;padding:1px 6px;"
            "border-radius:3px;font-size:0.7rem;font-weight:600;margin-left:6px'>INSIDE</span>"
        )
    elif pattern == "outside":
        badges += (
            "<span style='background:#e67e2230;color:#e67e22;padding:1px 6px;"
            "border-radius:3px;font-size:0.7rem;font-weight:600;margin-left:6px'>OUTSIDE</span>"
        )

    # Distance label
    dist_dir = "above" if distance_pct >= 0 else "below"
    dist_abs = abs(distance_pct)

    st.markdown(
        f"<div style='background:#161b22;border:1px solid #30363d;border-left:3px solid {status_color};"
        f"border-radius:6px;padding:0.75rem 1rem;margin-bottom:0.5rem'>"
        # Row 1: symbol + badges ... price
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div>"
        f"<span style='font-weight:700;font-size:1.05rem'>{symbol}</span>"
        f"{badges}"
        f"</div>"
        f"<span style='font-weight:600;font-size:1.05rem'>${price:,.2f}</span>"
        f"</div>"
        # Row 2: score + status ... support + distance + MA trend
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-top:4px;font-size:0.82rem'>"
        f"<div>"
        f"<span style='color:{score_color};font-weight:700'>{score_label} ({score})</span>"
        f"&nbsp;&nbsp;"
        f"<span style='background:{status_color}20;color:{status_color};padding:1px 8px;"
        f"border-radius:10px;font-size:0.75rem;font-weight:600'>{status_label}</span>"
        f"</div>"
        f"<div style='color:#8b949e;text-align:right'>"
        f"{support_name} ${support_level:,.2f}"
        f"&nbsp;&middot;&nbsp;{dist_abs:.1f}% {dist_dir}"
        f"&nbsp;&middot;&nbsp;{ma_trend}"
        f"</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def plotly_layout(height_key: str = "standard", **overrides) -> dict:
    """Return a consistent Plotly layout dict for dark-themed charts."""
    layout = {
        "height": CHART_HEIGHTS.get(height_key, CHART_HEIGHTS["standard"]),
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, sans-serif", "color": "#fafafa"},
        "xaxis": {"gridcolor": "#1e3a5f", "zerolinecolor": "#1e3a5f"},
        "yaxis": {"gridcolor": "#1e3a5f", "zerolinecolor": "#1e3a5f"},
        "legend": {"orientation": "h", "y": 1.08},
        "margin": {"l": 40, "r": 20, "t": 40, "b": 30},
    }
    layout.update(overrides)
    return layout


# ---------------------------------------------------------------------------
# Shared chart helpers (used by Home + Scanner)
# ---------------------------------------------------------------------------


def add_level_line(fig, price, label, color, position="top left", dash="dash", width=1.5, row=1):
    """Add a horizontal level line with a styled annotation badge."""
    fig.add_hline(
        y=price, line_dash=dash, line_color=color, line_width=width,
        annotation_text=f"  {label} ${price:,.2f}  ",
        annotation_font=dict(size=10, color="white"),
        annotation_bgcolor=color, annotation_borderpad=2,
        annotation_bordercolor=color,
        annotation_position=position,
        row=row, col=1,
    )


def volume_colors(chart: pd.DataFrame) -> list[str]:
    """Green/red volume bar colors matching candle direction."""
    return [
        "#2ecc71" if c >= o else "#e74c3c"
        for c, o in zip(chart["Close"], chart["Open"])
    ]


def build_candlestick_fig(
    chart: pd.DataFrame,
    x_vals,
    name: str,
    *,
    height: int = 450,
    show_volume: bool = True,
    tick_vals=None,
    tick_text=None,
) -> go.Figure:
    """Construct a dark-themed candlestick + volume subplot figure."""
    from plotly.subplots import make_subplots

    if show_volume and "Volume" in chart.columns:
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
            row_heights=[0.78, 0.22],
        )
    else:
        fig = make_subplots(rows=1, cols=1)
        show_volume = False

    fig.add_trace(go.Candlestick(
        x=x_vals,
        open=chart["Open"], high=chart["High"],
        low=chart["Low"], close=chart["Close"],
        name=name,
        increasing_line_color="#2ecc71", increasing_fillcolor="#2ecc71",
        decreasing_line_color="#e74c3c", decreasing_fillcolor="#e74c3c",
    ), row=1, col=1)

    if show_volume:
        fig.add_trace(go.Bar(
            x=x_vals, y=chart["Volume"],
            marker_color=volume_colors(chart),
            opacity=0.5, showlegend=False, name="Volume",
        ), row=2, col=1)
        fig.update_yaxes(title_text="Vol", row=2, col=1,
                         gridcolor="#1e3a5f", zerolinecolor="#1e3a5f")

    # Dark theme layout
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#c9d1d9", size=11),
        margin=dict(l=50, r=20, t=10, b=30),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)),
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1a1a2e",
            bordercolor="#1e3a5f",
            font=dict(color="#c9d1d9", size=11),
        ),
    )
    _spike_kw = dict(
        showspikes=True, spikemode="across", spikethickness=1,
        spikecolor="#888", spikedash="dot", spikesnap="cursor",
    )
    fig.update_xaxes(
        gridcolor="#1e3a5f", zerolinecolor="#1e3a5f",
        showgrid=False, row=1, col=1,
        **_spike_kw,
    )
    fig.update_yaxes(
        gridcolor="#1e3a5f", zerolinecolor="#1e3a5f",
        title_text="Price ($)", row=1, col=1,
        **_spike_kw,
    )

    # Custom tick labels (for gap-free integer x-axis)
    if tick_vals is not None and tick_text is not None:
        axis_key = "xaxis" if not show_volume else "xaxis2"
        fig.update_layout(**{
            axis_key: dict(
                tickmode="array", tickvals=tick_vals, ticktext=tick_text,
            ),
        })
        fig.update_xaxes(
            tickmode="array", tickvals=tick_vals, ticktext=tick_text,
            row=1, col=1,
        )

    # Y-axis padding: 3% above/below visible price range
    price_min = chart["Low"].min()
    price_max = chart["High"].max()
    pad = (price_max - price_min) * 0.03
    fig.update_yaxes(range=[price_min - pad, price_max + pad], row=1, col=1)

    return fig


# ---------------------------------------------------------------------------
# Page titles
# ---------------------------------------------------------------------------

_PAGE_TITLES = {
    "home": "TradeCoPilot",
    "scanner": "Scanner | TradeCoPilot",
    "scorecard": "Scorecard | TradeCoPilot",
    "history": "History | TradeCoPilot",
    "import": "Import | TradeCoPilot",
    "backtest": "Backtest | TradeCoPilot",
    "paper_trading": "Paper Trading | TradeCoPilot",
    "charts": "Charts | TradeCoPilot",
    "real_trades": "Real Trades | TradeCoPilot",
    "alerts": "Alerts | TradeCoPilot",
    "settings": "Settings | TradeCoPilot",
    "swing_trades": "Swing Trades | TradeCoPilot",
    "ai_coach": "AI Hub | TradeCoPilot",
}


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------

TIER_LEVELS = {"free": 0, "pro": 1, "elite": 2, "admin": 99}

TIER_COLORS = {
    "free": "#888",
    "pro": "#3498db",
    "elite": "#f39c12",
    "admin": "#e74c3c",
}

TIER_FEATURES = {
    "free": [
        "Live signal scanner & daily plans",
        "Interactive candlestick charts",
        "Today's alerts feed",
        "AI Coach preview (3 queries/day)",
        "Swing trade setups (view only)",
    ],
    "pro": [
        "Everything in Free",
        "AI pre-market game plan via Telegram",
        "Sonnet-powered AI Coach (unlimited)",
        "Enhanced AI narratives for A+ signals",
        "Daily AI EOD review via Telegram",
        "Position advisor (on-demand)",
        "Score breakdown on every alert",
        "Full alert history (all sessions)",
        "Scorecard & performance analytics",
        "Trade journal with stop discipline lab",
        "Real trade P&L tracking",
        "Swing trade tracking & options",
        "Telegram DM alerts",
    ],
    "elite": [
        "Everything in Pro",
        "Auto position updates via Telegram (hourly)",
        "Weekly AI trading journal",
        "Backtesting engine",
        "Paper trading simulator",
        "Priority support",
    ],
}

TIER_PRICES = {"free": "$0", "pro": "$29/mo", "elite": "$59/mo"}

FREE_TIER_LIMITS = {
    "ai_queries_per_day": 3,
    "alerts_days_back": 1,
}


# ---------------------------------------------------------------------------
# Upgrade prompt (shown when tier is insufficient)
# ---------------------------------------------------------------------------

def _render_upgrade_prompt(current_tier: str, required_tier: str):
    """Show a styled upgrade prompt when user lacks the required tier."""
    color = TIER_COLORS.get(required_tier, "#3498db")
    features_html = "".join(
        f"<div style='padding:4px 0;color:#ccc'>&#10003; {f}</div>"
        for f in TIER_FEATURES.get(required_tier, [])
    )
    st.markdown(f"""
    <div style='
        max-width: 500px;
        margin: 3rem auto;
        padding: 2rem;
        background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        border: 1px solid {color};
        border-radius: 12px;
        text-align: center;
    '>
        <div style='font-size:2rem;margin-bottom:0.5rem'>&#128274;</div>
        <h2 style='margin:0 0 0.5rem 0;color:#fafafa'>Upgrade Required</h2>
        <p style='color:#888;margin-bottom:1.5rem'>
            This feature requires a <strong style='color:{color}'>{required_tier.title()}</strong>
            subscription.
        </p>
        <div style='text-align:left;padding:0 1rem;margin-bottom:1.5rem'>
            <div style='color:#aaa;font-size:0.85rem;text-transform:uppercase;
                        letter-spacing:0.05em;margin-bottom:8px'>
                What you get with {required_tier.title()} ({TIER_PRICES[required_tier]}):
            </div>
            {features_html}
        </div>
        <a href='https://square.link/u/FdEAnalM' target='_blank'
           style='display:inline-block;background:{color};color:white;
                  padding:10px 24px;border-radius:6px;text-decoration:none;
                  font-weight:600;font-size:0.95rem'>
            Subscribe Now &#8594;
        </a>
        <p style='color:#666;font-size:0.75rem;margin-top:8px'>
            Powered by Square &middot; Secure checkout
        </p>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Inline upgrade helpers (for preview-mode pages)
# ---------------------------------------------------------------------------

def get_current_tier() -> str:
    """Return the current user's tier from session state."""
    return st.session_state.get("_user_tier", "free")


def render_inline_upgrade(what_you_get: str, required_tier: str = "pro"):
    """Compact inline upgrade CTA — used within pages for section-level gating."""
    color = TIER_COLORS.get(required_tier, "#3498db")
    price = TIER_PRICES.get(required_tier, "")
    st.markdown(f"""
    <div style='
        background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
        border: 1px solid {color}40;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin: 1rem 0;
        text-align: center;
    '>
        <span style='font-size:1.2rem'>&#128274;</span>
        <span style='color:#ccc;margin-left:8px'>{what_you_get}</span>
        <br>
        <a href='https://square.link/u/FdEAnalM' target='_blank'
           style='display:inline-block;background:{color};color:white;
                  padding:6px 18px;border-radius:5px;text-decoration:none;
                  font-weight:600;font-size:0.85rem;margin-top:8px'>
            Upgrade to {required_tier.title()} ({price}) &#8594;
        </a>
    </div>
    """, unsafe_allow_html=True)


def render_usage_counter(current: int, limit: int, label: str = "AI queries"):
    """Show usage progress bar: '2/3 AI queries used today'."""
    pct = min(current / limit, 1.0) if limit > 0 else 1.0
    remaining = max(limit - current, 0)
    if pct < 0.67:
        bar_color = "#2ecc71"
    elif pct < 1.0:
        bar_color = "#f39c12"
    else:
        bar_color = "#e74c3c"
    limit_msg = '<strong style="color:#e74c3c">limit reached</strong>' if remaining == 0 else f"{remaining} remaining"
    st.markdown(f"""
    <div style='margin:8px 0'>
        <div style='color:#aaa;font-size:0.8rem;margin-bottom:4px'>
            {current}/{limit} {label} used today &mdash; {limit_msg}
        </div>
        <div style='background:#1a1a2e;border-radius:4px;height:6px;overflow:hidden'>
            <div style='background:{bar_color};width:{pct*100:.0f}%;height:100%;border-radius:4px'></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def check_usage_limit(user_id: int, feature: str, limit: int) -> tuple:
    """Check if user is within daily usage limit. Returns (allowed, current_count)."""
    from db import get_daily_usage
    count = get_daily_usage(user_id, feature)
    return (count < limit, count)


# ---------------------------------------------------------------------------
# Sidebar user info with tier badge
# ---------------------------------------------------------------------------

def _render_sidebar_user(user: dict, tier: str):
    """Show user info, tier badge, and upgrade CTA in sidebar."""
    from auth import logout_user

    color = TIER_COLORS.get(tier, "#888")
    with st.sidebar:
        st.markdown(
            f"<div style='padding:8px 0;margin-bottom:4px'>"
            f"<strong>{user['display_name']}</strong>"
            f"<br><span style='color:#888;font-size:0.75rem'>{user['email']}</span>"
            f"<br><span style='background:{color};color:white;padding:2px 8px;"
            f"border-radius:3px;font-size:0.7rem;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:0.05em'>{tier}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Upgrade CTA (only for non-elite, non-admin)
        if tier not in ("elite", "admin"):
            next_tier = "pro" if tier == "free" else "elite"
            next_color = TIER_COLORS[next_tier]
            st.markdown(
                f"<div style='background:{next_color}15;border:1px solid {next_color}40;"
                f"border-radius:6px;padding:8px 10px;margin:8px 0;text-align:center;"
                f"font-size:0.8rem'>"
                f"<a href='/Settings' target='_self' style='color:{next_color};"
                f"text-decoration:none;font-weight:600'>"
                f"Upgrade to {next_tier.title()} &#8594;</a>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if st.button("Logout", key="sidebar_logout"):
            logout_user()
            st.rerun()


# ---------------------------------------------------------------------------
# Landing page (public, unauthenticated)
# ---------------------------------------------------------------------------

def render_landing_page():
    """Render the full marketing landing page for unauthenticated visitors."""
    from auth import get_current_user, login_user, authenticate_user, create_user, get_user_by_id
    from auth import _render_reset_password_form, _render_forgot_password_form

    # Handle password reset links
    reset_token = st.query_params.get("reset_token")
    if reset_token:
        _render_reset_password_form(reset_token)
        st.stop()

    # ── Navbar ──
    st.markdown("""
    <div style='
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.5rem 0;
        margin-bottom: 1rem;
        border-bottom: 1px solid #1e3a5f;
    '>
        <div style='font-size:1.5rem;font-weight:700;
            background: linear-gradient(90deg, #3498db, #2ecc71);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        '>&#9889; TradeCoPilot</div>
        <div style='color:#888;font-size:0.85rem'>
            <a href='#features' style='color:#888;text-decoration:none;margin:0 12px'>Features</a>
            <a href='#pricing' style='color:#888;text-decoration:none;margin:0 12px'>Pricing</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Hero ──
    st.markdown("""
    <div style='text-align:center;padding:3rem 1rem 2rem 1rem'>
        <h1 style='
            font-size: 2.8rem;
            font-weight: 700;
            background: linear-gradient(90deg, #3498db, #2ecc71);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0 0 0.5rem 0;
            line-height: 1.2;
        '>Your AI Co-Pilot for Smarter Trading</h1>
        <p style='color:#aaa;font-size:1.15rem;max-width:650px;margin:0 auto 0.5rem auto'>
            AI monitors the market for you and delivers scored trade signals
            with exact entry, stop, and target levels &mdash; straight to your phone.
        </p>
        <p style='color:#888;font-size:0.95rem;max-width:550px;margin:0 auto 1.5rem auto'>
            Built for busy professionals who trade but don't have time
            to sit in front of charts. Less stress, better decisions.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Auth forms ──
    col_spacer_l, col_auth, col_spacer_r = st.columns([1, 2, 1])
    with col_auth:
        tab_login, tab_register, tab_forgot = st.tabs(["Login", "Register", "Forgot Password"])
        with tab_login:
            with st.form("landing_login"):
                email = st.text_input("Email", key="landing_login_email")
                password = st.text_input("Password", type="password", key="landing_login_pass")
                submitted = st.form_submit_button("Login", use_container_width=True)
            if submitted:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    user = authenticate_user(email, password)
                    if user:
                        login_user(user)
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")

        with tab_register:
            with st.form("landing_register"):
                reg_email = st.text_input("Email", key="landing_reg_email")
                reg_name = st.text_input("Display Name (optional)", key="landing_reg_name")
                reg_pass = st.text_input("Password", type="password", key="landing_reg_pass")
                reg_confirm = st.text_input("Confirm Password", type="password", key="landing_reg_confirm")
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
            if reg_submitted:
                if reg_pass != reg_confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        from db import upsert_subscription, add_to_watchlist
                        from config import DEFAULT_WATCHLIST
                        user_id = create_user(reg_email, reg_pass, reg_name or None)
                        upsert_subscription(user_id, "free")
                        # Seed default watchlist (free tier: first 5 symbols)
                        for sym in DEFAULT_WATCHLIST[:5]:
                            add_to_watchlist(sym, user_id)
                        user = get_user_by_id(user_id)
                        login_user(user)
                        st.success("Account created!")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        with tab_forgot:
            _render_forgot_password_form()

    # ── Features ──
    st.markdown("<a id='features'></a>", unsafe_allow_html=True)
    st.markdown("")
    st.markdown("""
    <div style='text-align:center;margin:2rem 0 1rem 0'>
        <h2 style='color:#fafafa;margin:0'>Everything You Need to Trade With AI</h2>
        <p style='color:#888'>Professional-grade tools, powered by AI</p>
    </div>
    """, unsafe_allow_html=True)

    features = [
        ("&#128200;", "Real-Time Signals", "MA bounce, support bounce, breakout, gap fill — scored and ranked automatically."),
        ("&#129302;", "AI Trade Coach", "Get personalized coaching on your setups, entries, and risk management."),
        ("&#128276;", "Smart Alerts", "Telegram DM + email alerts with AI-generated narratives for every signal."),
        ("&#127919;", "Score Engine", "Every signal scored 0-100 with A+/A/B/C grades. Focus on the best setups."),
        ("&#128737;", "Risk Management", "Auto stop-loss tracking, position sizing, and cooldown logic built in."),
        ("&#128221;", "Trade Journal", "Full history, P&L tracking, scorecard, and equity curve analytics."),
    ]
    cols = st.columns(3)
    for i, (icon, title, desc) in enumerate(features):
        with cols[i % 3]:
            st.markdown(f"""
            <div style='
                background: linear-gradient(135deg, #16213e 0%, #1a1a2e 100%);
                border: 1px solid #1e3a5f;
                border-radius: 10px;
                padding: 1.2rem;
                margin-bottom: 1rem;
                min-height: 140px;
            '>
                <div style='font-size:1.5rem;margin-bottom:6px'>{icon}</div>
                <div style='font-weight:600;color:#fafafa;margin-bottom:4px'>{title}</div>
                <div style='color:#888;font-size:0.85rem'>{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── How it works ──
    st.markdown("""
    <div style='text-align:center;margin:2rem 0 1rem 0'>
        <h2 style='color:#fafafa;margin:0'>How It Works</h2>
    </div>
    """, unsafe_allow_html=True)
    hw_cols = st.columns(3)
    steps = [
        ("1", "Set Your Watchlist", "Add the symbols you trade. We scan them in real-time during market hours."),
        ("2", "Get Scored Alerts", "Signals fire with entry, stop, and targets. Each scored A+ through C."),
        ("3", "Trade With Confidence", "Execute the best setups. Track results. Improve with AI coaching."),
    ]
    for col, (num, title, desc) in zip(hw_cols, steps):
        with col:
            st.markdown(f"""
            <div style='text-align:center;padding:1rem'>
                <div style='
                    width:40px;height:40px;border-radius:50%;
                    background:linear-gradient(135deg,#3498db,#2ecc71);
                    color:white;font-weight:700;font-size:1.2rem;
                    display:inline-flex;align-items:center;justify-content:center;
                    margin-bottom:8px;
                '>{num}</div>
                <div style='font-weight:600;color:#fafafa;margin-bottom:4px'>{title}</div>
                <div style='color:#888;font-size:0.85rem'>{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Pricing ──
    st.markdown("<a id='pricing'></a>", unsafe_allow_html=True)
    st.markdown("")
    st.markdown("### Simple, Transparent Pricing")
    st.caption("Start free. Upgrade when you're ready.")

    tiers = [
        ("Free", "$0", "forever", "#888", [
            "Signal scanner (15-min delay)", "5-symbol watchlist",
            "Basic candlestick charts", "Community Telegram group",
        ]),
        ("Pro", "$29", "/month", "#3498db", [
            "Real-time signals", "Unlimited watchlist",
            "Telegram DM alerts", "AI Trade Narrator",
            "Full trade history", "Scorecard & analytics",
        ]),
        ("Elite", "$79", "/month", "#f39c12", [
            "Everything in Pro", "AI Trade Coach",
            "Backtesting engine", "Paper trading simulator",
            "Priority support",
        ]),
    ]
    pricing_cols = st.columns(3)
    for col, (name, price, period, color, feats) in zip(pricing_cols, tiers):
        with col:
            with st.container(border=True):
                if name == "Pro":
                    st.caption("MOST POPULAR")
                st.subheader(name)
                st.metric(label=period, value=price)
                for f in feats:
                    st.markdown(f"\\- {f}", unsafe_allow_html=False)

    # ── Stats ──
    st.markdown("")
    stat_cols = st.columns(3)
    stats = [("12,000+", "Alerts Generated"), ("85%", "A+ Signal Hit Rate"), ("50+", "Symbols Tracked")]
    for col, (val, label) in zip(stat_cols, stats):
        with col:
            st.markdown(f"""
            <div style='text-align:center;padding:1rem'>
                <div style='font-size:1.8rem;font-weight:700;
                    background:linear-gradient(90deg,#3498db,#2ecc71);
                    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                '>{val}</div>
                <div style='color:#888;font-size:0.85rem'>{label}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Disclaimer + Footer ──
    st.markdown("")
    st.markdown("""
    <div style='
        border-top: 1px solid #1e3a5f;
        padding: 1.5rem 0;
        margin-top: 2rem;
        text-align: center;
        color: #666;
        font-size: 0.75rem;
    '>
        <p style='margin:0 0 0.5rem 0'>
            <strong>Disclaimer:</strong> TradeCoPilot is for informational purposes only.
            Not financial advice. Past performance does not guarantee future results.
            Trade at your own risk.
        </p>
        <p style='margin:0'>
            &copy; 2026 TradeCoPilot &mdash;
            <a href='mailto:support@aicopilottrader.com' style='color:#3498db'>Contact</a>
        </p>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Centralized page setup
# ---------------------------------------------------------------------------

def setup_page(page_key: str, *, tier_required: str | None = None,
               tier_preview: str | None = None) -> dict | None:
    """One-call page bootstrap — must be the first Streamlit call in every page.

    1. ``st.set_page_config`` with sidebar expanded (skipped under nav shell)
    2. ``init_db()``
    3. ``inject_custom_css()``
    4. Sidebar branding (skipped under nav shell)
    5. Auth + tier gating based on ``tier_required``

    **tier_required=None**: Public page — returns user if logged in, None otherwise.
    **tier_required='free'**: Auth required, any tier works.
    **tier_required='pro'**: Auth required, pro or elite tier needed.
    **tier_required='elite'**: Auth required, elite tier needed.

    **tier_preview**: When set, users at this tier level can access the page
    in preview mode (limited functionality) instead of being fully blocked.
    The page checks ``get_current_tier()`` to decide what to render.

    Returns the user dict (or ``None`` for public pages when not logged in).
    """
    try:
        st.set_page_config(
            page_title=_PAGE_TITLES.get(page_key, "TradeCoPilot"),
            page_icon="\u26a1",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except st.errors.StreamlitAPIException:
        pass  # Already set by navigation shell

    _nav_mode = st.session_state.get("_nav_mode", False)

    from db import init_db
    init_db()

    # Start background monitor thread (idempotent — only once per process)
    # Disabled when Railway worker handles monitoring (DISABLE_MONITOR_THREAD=true)
    import os
    if not os.environ.get("DISABLE_MONITOR_THREAD", "").lower() == "true":
        import monitor_thread
        monitor_thread.start()

    inject_custom_css()

    if not _nav_mode:
        with st.sidebar:
            sidebar_branding()

    if tier_required is None:
        # Public page — return user if logged in, None otherwise
        from auth import get_current_user
        return get_current_user()

    # Auth required — gate with login/register form
    from auth import require_auth
    from db import get_user_tier
    user = require_auth()

    # Tier check
    tier = get_user_tier(user["id"])
    st.session_state["_user_tier"] = tier
    if TIER_LEVELS.get(tier, 0) < TIER_LEVELS.get(tier_required, 0):
        # Allow through in preview mode if tier >= preview level
        if tier_preview and TIER_LEVELS.get(tier, 0) >= TIER_LEVELS.get(tier_preview, 0):
            pass  # Page handles its own gating via get_current_tier()
        else:
            _render_upgrade_prompt(tier, tier_required)
            st.stop()

    # Show sidebar user info with tier badge (nav shell renders this itself)
    if not _nav_mode:
        _render_sidebar_user(user, tier)

    return user
