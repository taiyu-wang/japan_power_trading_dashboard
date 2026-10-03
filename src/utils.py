from html import escape

import pandas as pd
import streamlit as st

from .config import APP_TITLE
from .published_data import load_runtime_manifest
from .source_quality import source_status_table


def configure_page(page_title: str = APP_TITLE) -> None:
    st.set_page_config(page_title=page_title, page_icon="📈", layout="wide")
    inject_trading_css()
    with st.sidebar.expander("Published feed status"):
        render_freshness_bar()


_FRESHNESS_GROUPS = [
    ("Historical", {"historical_prices", "forward_curves"}),
    (
        "JEPX",
        {
            "jepx_spot_daily",
            "jepx_intraday",
            "jepx_baseload",
            "jepx_offer_stack_depth",
            "jepx_offer_stack_curves",
        },
    ),
    ("Supply", {"supply_mix", "supply_mix_daily_shape", "supply_mix_residual_thermal"}),
    ("Weather", {"weather"}),
    ("News", {"news"}),
]
_STATUS_PRIORITY = {"unavailable": 4, "stale": 3, "partial": 2, "delayed": 1, "current": 0}


def _group_freshness(records: list[dict], dataset_ids: set[str]) -> tuple[str, str]:
    matching = [record for record in records if record.get("dataset_id") in dataset_ids]
    if not matching:
        return "unavailable", "n/a"
    status = max(
        (str(record.get("status", "unavailable")) for record in matching),
        key=lambda value: _STATUS_PRIORITY.get(value, 4),
    )
    dates = pd.to_datetime(
        [record.get("observation_end") for record in matching],
        errors="coerce",
        utc=True,
    )
    valid_dates = [date for date in dates if pd.notna(date)]
    date_label = max(valid_dates).date().isoformat() if valid_dates else "n/a"
    return status, date_label


def freshness_bar_html(manifest: dict, source: str) -> str:
    overall = str(manifest.get("overall_status", "unavailable")).lower()
    records = list(manifest.get("datasets", []))
    chips = [
        (
            f"<span class='freshness-chip freshness-{escape(overall)}'>"
            f"<strong>Data status</strong> {escape(overall.upper())}</span>"
        )
    ]
    for label, dataset_ids in _FRESHNESS_GROUPS:
        status, date_label = _group_freshness(records, dataset_ids)
        chips.append(
            f"<span class='freshness-chip freshness-{escape(status)}' "
            f"title='{escape(status.title())}'>"
            f"{escape(label)}: {escape(date_label)}</span>"
        )
    chips.append(f"<span class='freshness-source'>{escape(source)}</span>")
    return f"<div class='freshness-strip'>{''.join(chips)}</div>"


def render_freshness_bar() -> None:
    manifest, source = load_runtime_manifest()
    st.markdown(freshness_bar_html(manifest, source), unsafe_allow_html=True)


def sample_data_notice() -> None:
    st.caption("Historical prices are bundled synthetic sample data unless replaced with licensed/vendor or user-supplied datasets.")


def inject_trading_css() -> None:
    st.markdown(
        f"""<style>
        :root {{
            --desk-paper: rgba(127,127,127,0.04); --desk-ink: inherit;
            --desk-muted: inherit; --desk-line: rgba(127,127,127,0.25);
        }}
        [data-testid="stMainBlockContainer"] {{ padding-top: 1.5rem; max-width: 1480px; }}
        [data-testid="stSidebar"] {{ border-right: 1px solid var(--desk-line); }}
        h1 {{ font-size: 1.7rem !important; letter-spacing: 0; }}
        h2 {{ font-size: 1.2rem !important; letter-spacing: 0; }}
        h3 {{ font-size: 1.05rem !important; letter-spacing: 0; }}
        [data-testid="stMetric"] {{
            padding: 12px 14px; border: 1px solid var(--desk-line);
            border-radius: 6px; background: var(--desk-paper);
        }}
        [data-testid="stMetricValue"] {{
            font-size: 1.45rem !important; font-variant-numeric: tabular-nums;
        }}
        [data-testid="stMetricLabel"] p {{ white-space: normal; overflow-wrap: anywhere; }}
        [data-testid="stPlotlyChart"] {{ padding: 0; }}
        .desk-panel, .signal-card {{
            padding: 12px 0; border-bottom: 1px solid var(--desk-line);
            background: transparent; color: var(--desk-ink);
        }}
        .small-muted {{ color: inherit; opacity: 0.75; font-size: 0.8rem; }}
        .source-chip {{
            display: inline-block; font-size: 0.75rem; color: var(--desk-muted);
            margin: 0 12px 6px 0; padding: 0; background: transparent;
        }}
        .freshness-strip {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .freshness-chip {{
            font-size: 0.72rem; border-left: 3px solid var(--desk-line);
            padding: 3px 6px; color: var(--desk-ink);
        }}
        .freshness-current {{ border-color: #2F8F71; }}
        .freshness-delayed, .freshness-partial {{ border-color: #D39B36; }}
        .freshness-stale, .freshness-unavailable {{ border-color: #D65F5F; }}
        .freshness-source {{ color: var(--desk-muted); font-size: 0.72rem; }}
        @media (max-width: 640px) {{
            [data-testid="stMainBlockContainer"] {{ padding: 1rem 0.75rem; }}
            h1 {{ font-size: 1.45rem !important; }}
            [data-testid="stMetricValue"] {{ font-size: 1.25rem !important; }}
        }}
        </style>""",
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


DATE_DISPLAY_COLUMNS = {"date", "curve_date", "contract_month", "delivery_date"}


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
        f"<span class='source-chip'>{escape(row['dataset'])}: {escape(row['category'])}</span>"
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


def analysis_window(df: pd.DataFrame) -> tuple:
    first, last = df["date"].min().date(), df["date"].max().date()
    saved = st.session_state.get("analysis_period", "30D")
    choices = ["7D", "30D", "90D", "Feb 2026 onward", "Custom"]
    choice = st.selectbox("Analysis period", choices, index=choices.index(saved), key="_analysis_period")
    st.session_state["analysis_period"] = choice
    if choice == "Custom":
        window = st.session_state.get("analysis_dates", (first, last))
        window = tuple(min(last, max(first, pd.Timestamp(value).date())) for value in window)
        result = st.date_input("Delivery date range", window, min_value=first, max_value=last, key="_analysis_dates")
        if len(result) == 2:
            st.session_state["analysis_dates"] = result
            return result
        return window
    start = pd.Timestamp("2026-02-01") if choice == "Feb 2026 onward" else pd.Timestamp(last) - pd.Timedelta(days=int(choice[:-1]) - 1)
    return max(first, start.date()), last


def market_board(df: pd.DataFrame) -> None:
    from .indicators import latest_snapshot
    from .market_context import MARKET_LABELS
    if df.empty:
        st.info("No observations in this period.")
        return
    board = latest_snapshot(df)
    board["Market"] = board["market"].map(MARKET_LABELS).fillna(board["market"])
    board["Source"] = board.get("source_type", pd.Series("unverified", index=board.index)).str.title()
    board["Status"] = board["age_days"].map(lambda age: "Current" if age <= 4 else "Stale")
    board.loc[board["Source"].eq("Synthetic"), "Status"] = "Sample only"
    board.loc[board["Source"].eq("Unverified"), "Status"] = "Unverified"
    board = board.rename(columns={"price": "Price", "unit": "Unit", "date": "Observation date", "change_30d_pct": "30d to quote (%)"})
    dataframe_with_dates(board[["Market", "Price", "Unit", "Observation date", "30d to quote (%)", "Source", "Status"]], hide_index=True, width="stretch", column_config={"Price": st.column_config.NumberColumn(format="%.2f"), "30d to quote (%)": st.column_config.NumberColumn(format="%.1f")})


def signal_watchlist(signals: pd.DataFrame) -> None:
    if signals.empty:
        st.info("No eligible alerts. Stale, synthetic or insufficient-history inputs are excluded.")
        return
    display = signals.rename(columns={"signal_name": "Condition", "direction": "Market read", "market_data_as_of": "Evidence date", "evidence_strength": "Evidence strength"})
    st.dataframe(display[["Condition", "Market read", "Evidence date", "Evidence strength"]], hide_index=True, width="stretch")
    for _, signal in signals.iterrows():
        with st.expander(signal["signal_name"]):
            st.caption(f"Computed {signal['signal_time_sgt']} | Evidence {signal['market_data_as_of']} | Rule strength, not forecast probability")
            st.write(signal["rationale"])
            st.write(f"Market implication: {signal['possible_market_implication']}")
            st.write(f"Invalidation: {signal['invalidation']}")
            st.caption(signal["supporting_metrics"])
