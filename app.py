import pandas as pd
import streamlit as st

from src.config import APP_TITLE, DEFAULT_MARKETS, MARKET_NOTES
from src.data_loader import cached_market_commentary, cached_srmc_comparison, get_forward_curves, load_prepared_historical
from src.indicators import latest_snapshot
from src.transformations import normalize_to_100
from src.charts import line_chart, srmc_comparison_chart
from src.utils import configure_page, dataframe_with_dates, download_button, live_fetch_spinner, page_header, render_chart, sample_data_notice


configure_page("Overview")

hist = load_prepared_historical()
default_focus_start = pd.Timestamp("2026-02-01").date()

with st.sidebar:
    st.header("Market Console")
    use_live_curves = st.toggle("Refresh live public curves", value=False, help="Bundled curves load fastest on Streamlit Cloud. Enable to attempt live Brent/JCC-derived curves.")
    markets = st.multiselect("Markets", sorted(hist["market"].unique()), default=DEFAULT_MARKETS)
    min_date, max_date = hist["date"].min().date(), hist["date"].max().date()
    default_start = max(default_focus_start, min_date)
    date_range = st.date_input("Date range", value=(default_start, max_date), min_value=min_date, max_value=max_date)
    with st.expander("SRMC assumptions"):
        gas_efficiency = st.slider("Gas efficiency", 0.45, 0.62, 0.55, 0.01)
        coal_efficiency = st.slider("Coal efficiency", 0.34, 0.46, 0.40, 0.01)
        gas_vom = st.number_input("Gas VOM (JPY/MWh)", value=500.0, step=50.0)
        coal_vom = st.number_input("Coal VOM (JPY/MWh)", value=700.0, step=50.0)
    if len(date_range) == 2:
        start, end = date_range
    else:
        start, end = min_date, max_date
    with st.expander("Data source notes"):
        st.caption("Curve source defaults to bundled CSV for fast deployed startup. Live mode pulls public Brent where available; JCC/JCC-linked LNG are Brent-derived proxies. JKM, coal, and Japan power forwards require vendor settlement or upload.")

with live_fetch_spinner("Refreshing live public forward curves...", use_live_curves):
    curves, curve_warnings, curve_source_label = get_forward_curves(use_live_curves)
for warning in curve_warnings:
    st.sidebar.warning(warning)

page_header(
    "Overview",
    f"{APP_TITLE}: institutional-style market intelligence for Japan LNG, coal, crude, FX, and power markets.",
    {
        "Historical prices": "Bundled synthetic historical prices",
        "Forward curves": curve_source_label,
        "SRMC inputs": "Derived from dashboard fuel, FX, and power data",
    },
)
sample_data_notice()

filtered = hist[(hist["market"].isin(markets)) & (hist["date"].dt.date.between(start, end))]
srmc_filtered = hist[hist["date"].dt.date.between(start, end)]

snapshot = latest_snapshot(hist[hist["market"].isin(DEFAULT_MARKETS)])
for row_markets in (DEFAULT_MARKETS[:4], DEFAULT_MARKETS[4:]):
    if not row_markets:
        continue
    cards = st.columns(4)
    for col, market in zip(cards, row_markets):
        row = snapshot[snapshot["market"] == market]
        with col.container(border=True, key=f"kpi-card-{market}"):
            if row.empty:
                st.metric(market, "n/a")
            else:
                r = row.iloc[0]
                st.metric(market, f"{r['price']:,.2f}", f"{r['change_30d_pct']:.1f}% 30d")

left, right = st.columns([2, 1])
with left:
    render_chart(line_chart(normalize_to_100(filtered), "date", "normalized", "market", "Cross-Asset Repricing Since Window Start", "Index = 100"))
with right:
    st.markdown("### Desk Commentary")
    for item in cached_market_commentary(filtered):
        st.markdown(f"- {item}")
    download_button(filtered, "filtered_market_data.csv")

srmc = cached_srmc_comparison(
    srmc_filtered,
    gas_efficiency=gas_efficiency,
    coal_efficiency=coal_efficiency,
    gas_vom_jpy_mwh=gas_vom,
    coal_vom_jpy_mwh=coal_vom,
)
st.markdown("### SRMC Stack vs JEPX System Price")
st.caption("Fuel SRMC lines are shown in JPY/kWh. Coal SRMC uses CFR Japan delivered coal when available, with Newcastle as fallback; thermal conversion assumes 6,000 kcal/kg NAR and selected efficiency. The amber band visualizes JCC-linked gas SRMC from 11% to 13% slope.")
if srmc.empty:
    st.warning("SRMC view needs JKM, JCC, USDJPY, JEPX system price, and either CFR Japan coal or Newcastle coal data in the selected date range.")
else:
    render_chart(srmc_comparison_chart(srmc, "Coal SRMC, JKM Gas SRMC, JCC 11-13% Gas SRMC Band, and JEPX System"))

st.markdown("### Forward Curve Monitor")
st.caption(f"Curve source: {curve_source_label}. Public/derived marks are screening inputs, not licensed settlement data.")
front = curves.sort_values("curve_date").groupby(["market", "curve_date"]).head(1).groupby("market").tail(1)
front_columns = ["market", "curve_date", "contract_month", "price", "currency", "unit"]
for optional_col in ["contract_type", "source_note"]:
    if optional_col in front.columns:
        front_columns.append(optional_col)
dataframe_with_dates(front[front_columns], width="stretch", hide_index=True)

st.markdown("### Contract and Data Source Notes")
for market in ["JCC", "BRENT", "JAPAN_POWER_FUTURES", "JEPX_SYSTEM"]:
    st.markdown(f"- **{market}:** {MARKET_NOTES[market]}")
