from contextlib import nullcontext

import pandas as pd
import streamlit as st

from .config import APP_TITLE
from .source_quality import source_status_table


# Shared Plotly config: mode bar only on hover, no logo, responsive resize.
CHART_CONFIG = {"displayModeBar": "hover", "displaylogo": False, "responsive": True}


def render_chart(fig, **kwargs) -> None:
    """Render a Plotly figure with the shared desk defaults (stretch width, lean mode bar)."""
    st.plotly_chart(fig, width="stretch", config=CHART_CONFIG, **kwargs)


def live_fetch_spinner(label: str, active: bool = True):
    """Return st.spinner(label) while a live fetch is enabled, else a no-op context manager."""
    return st.spinner(label) if active else nullcontext()


def configure_page(page_title: str = APP_TITLE) -> None:
    st.set_page_config(page_title=page_title, page_icon="📈", layout="wide")
    inject_trading_css()


def sample_data_notice() -> None:
    st.caption("Historical prices are bundled synthetic sample data unless replaced with licensed/vendor or user-supplied datasets.")


def inject_trading_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --oe-bg: #F5F7FB;
            --oe-paper: #FFFFFF;
            --oe-paper-soft: #F0F4F7;
            --oe-grid: rgba(31, 41, 51, 0.045);
            --oe-line: #E3E8EF;
            --oe-line-strong: #CBD5E1;
            --oe-ink: #1F2933;
            --oe-muted: #667085;
            --oe-faint: #98A2B3;
            --accent: #008A66;
            --accent-soft: #E4F6EF;
            --accent-ink: #0B3B2E;
            --accent-red: #D64545;
            --risk: #D64545;
            --positive: #008A66;
            --solar: #F4E300;
            --coal: #2F3136;
            --gas: #D65F5F;
            --hydro: #2F80ED;
        }
        .stApp {
            background: var(--oe-bg);
            color: var(--oe-ink);
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .main .block-container {
            padding-top: 1.75rem;
            padding-bottom: 3rem;
            max-width: 1480px;
        }
        section[data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: 1px solid var(--oe-line);
            box-shadow: 8px 0 22px rgba(31, 41, 51, 0.04);
        }
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][href$="/"] span[label="app"] p {
            font-size: 0;
        }
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][href$="/"] span[label="app"] p::after {
            content: "Overview";
            font-size: 1rem;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            border-bottom: 1px solid var(--oe-line);
            padding-top: 1.2rem;
            padding-bottom: 1rem;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"]::before {
            content: "Japan Power";
            display: block;
            color: var(--oe-ink);
            font-size: 1.08rem;
            line-height: 1.15;
            font-weight: 750;
            letter-spacing: 0;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"]::after {
            content: "Fuel & market intelligence";
            display: block;
            color: var(--oe-muted);
            font-size: 0.75rem;
            line-height: 1.2;
            margin-top: 3px;
        }
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {
            border-radius: 8px;
            margin: 2px 10px;
            min-height: 36px;
            color: var(--oe-muted);
            font-weight: 600;
        }
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover,
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {
            background: var(--oe-paper-soft);
            color: var(--oe-ink);
        }
        section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"]::before {
            content: "";
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: var(--accent);
            margin-right: 2px;
        }
        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] [data-baseweb="select"] > div,
        section[data-testid="stSidebar"] [data-baseweb="input"] > div {
            border-color: var(--oe-line-strong);
            background: #FFFFFF;
            border-radius: 8px;
        }
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid var(--oe-line);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(31, 41, 51, 0.06);
            padding: 13px 15px;
        }
        div[class*="st-key-kpi-card-"] div[data-testid="stMetric"] {
            border: none;
            box-shadow: none;
            background: transparent;
            padding: 2px 4px;
        }
        div[data-testid="stMetric"] label {
            color: var(--oe-muted);
            font-weight: 650;
            letter-spacing: 0.01em;
        }
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] p {
            max-width: 100%;
            white-space: normal;
            overflow-wrap: anywhere;
            line-height: 1.15;
        }
        div[data-testid="stMetricValue"] {
            color: var(--oe-ink);
            font-size: 1.45rem !important;
            font-weight: 720;
            line-height: 1.05;
            font-variant-numeric: tabular-nums;
        }
        .desk-panel {
            background: #FFFFFF;
            border: 1px solid var(--oe-line);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(31, 41, 51, 0.055);
            padding: 16px;
        }
        .signal-card {
            background: #FFFFFF;
            border-left: 4px solid var(--accent);
            border-top: 1px solid var(--oe-line);
            border-right: 1px solid var(--oe-line);
            border-bottom: 1px solid var(--oe-line);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(31, 41, 51, 0.055);
            padding: 15px 16px;
            margin-bottom: 12px;
        }
        .small-muted { color: var(--oe-muted); font-size: 0.88rem; }
        .source-chip {
            display: inline-block;
            border: 1px solid var(--oe-line);
            border-radius: 999px;
            padding: 3px 10px;
            margin: 0 6px 6px 0;
            color: var(--accent);
            background: var(--accent-soft);
            font-size: 0.82rem;
            font-weight: 650;
        }
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stExpander"],
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {
            border-color: var(--oe-line) !important;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stTable"] {
            background: #FFFFFF;
            border-radius: 8px;
        }
        div[data-testid="stPlotlyChart"] {
            background: #FFFFFF;
            border: 1px solid var(--oe-line);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(31, 41, 51, 0.055);
            padding: 8px 8px 2px;
        }
        [data-baseweb="tag"] {
            background: var(--oe-paper-soft) !important;
            border: 1px solid var(--oe-line-strong) !important;
            color: var(--accent) !important;
        }
        [data-baseweb="tag"] span,
        [data-baseweb="tag"] svg {
            color: var(--accent) !important;
            fill: var(--accent) !important;
        }
        .stButton button,
        .stDownloadButton button,
        button[kind="secondary"],
        button[kind="primary"] {
            border-radius: 8px;
            border: 1px solid var(--oe-line-strong);
            background: #FFFFFF;
            color: var(--oe-ink);
            font-weight: 650;
            min-height: 36px;
        }
        .stButton button:hover,
        .stDownloadButton button:hover,
        button[kind="secondary"]:hover,
        button[kind="primary"]:hover {
            border-color: var(--accent);
            color: var(--accent);
            background: var(--accent-soft);
        }
        button[kind="primary"] {
            background: var(--accent);
            border-color: var(--accent);
            color: #FFFFFF;
        }
        button[kind="primary"]:hover {
            background: #00775A;
            border-color: #00775A;
            color: #FFFFFF;
        }
        button[data-baseweb="tab"] {
            color: var(--oe-muted);
            font-weight: 650;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--accent);
        }
        [data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
        }
        .js-plotly-plot .main-svg text,
        .js-plotly-plot .gtitle,
        .js-plotly-plot .xtick text,
        .js-plotly-plot .ytick text,
        .js-plotly-plot .legendtext {
            fill: var(--oe-ink) !important;
        }
        .js-plotly-plot .gridlayer path {
            stroke: var(--oe-line) !important;
        }
        .js-plotly-plot .zerolinelayer path {
            stroke: var(--oe-line-strong) !important;
        }
        h1, h2, h3 {
            color: var(--oe-ink);
            letter-spacing: 0;
        }
        h1 {
            font-size: 1.95rem !important;
            line-height: 1.12;
            font-weight: 720;
            padding-bottom: 0.15rem;
            border-bottom: 0;
        }
        h3 {
            margin-top: 0.65rem;
        }
        div[data-testid="stMetricValue"],
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stCaptionContainer"],
        label,
        p {
            color: var(--oe-ink);
        }
        div[data-testid="stCaptionContainer"],
        .stCaption,
        small {
            color: var(--oe-muted) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_price(value: float, currency: str = "", unit: str = "") -> str:
    if value is None:
        return "n/a"
    if currency == "JPY":
        return f"¥{value:,.0f}/{unit}" if unit else f"¥{value:,.0f}"
    if currency == "USD":
        return f"${value:,.2f}/{unit}" if unit else f"${value:,.2f}"
    return f"{value:,.2f}"


DATE_DISPLAY_COLUMNS = {"date", "curve_date", "contract_month", "front_month", "delivery_date"}


def format_dates_for_display(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        col_key = str(col).lower()
        is_date_col = col_key in DATE_DISPLAY_COLUMNS or pd.api.types.is_datetime64_any_dtype(out[col])
        if not is_date_col:
            continue
        converted = pd.to_datetime(out[col], errors="coerce")
        original_has_value = out[col].notna()
        if original_has_value.any() and converted[original_has_value].notna().all():
            formatted = converted.dt.strftime("%Y-%m-%d")
            out[col] = formatted.where(original_has_value, "")
    return out


def dataframe_with_dates(df: pd.DataFrame, **kwargs) -> None:
    st.dataframe(format_dates_for_display(df), **kwargs)


def download_button(df, filename: str, label: str = "Export filtered data as CSV") -> None:
    st.download_button(label, format_dates_for_display(df).to_csv(index=False), file_name=filename, mime="text/csv")


def source_status_panel(sources: dict[str, str], expanded: bool = False) -> None:
    if not sources:
        return
    status = source_status_table(sources)
    chips = "".join(
        f"<span class='source-chip'>{row['dataset']}: {row['confidence']}</span>"
        for _, row in status.iterrows()
    )
    st.markdown(chips, unsafe_allow_html=True)
    with st.expander("Source quality notes", expanded=expanded):
        dataframe_with_dates(status, width="stretch", hide_index=True)


def page_header(title: str, subtitle: str, sources: dict[str, str] | None = None) -> None:
    st.title(title)
    st.caption(subtitle)
    if sources:
        source_status_panel(sources)
