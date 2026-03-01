"""Centralized UI theme for TradeSignal — single source of truth for styling."""

from __future__ import annotations

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

CHART_HEIGHTS = {
    "hero": 450,
    "standard": 380,
    "compact": 300,
    "mini": 200,
    "full": 700,
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

    /* ── Hide Streamlit branding ──────────────────────────────────── */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stStatusWidget"] {visibility: hidden;}

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
        font-size: 0.7rem !important;
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
    """Render the TradeSignal logo block in the sidebar."""
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
        '>&#9889; TradeSignal</div>
        <div style='color:#888;font-size:0.75rem;letter-spacing:0.08em;text-transform:uppercase'>
            Trade Smarter
        </div>
    </div>
    """, unsafe_allow_html=True)


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
