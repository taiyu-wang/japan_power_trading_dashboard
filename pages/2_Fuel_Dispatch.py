import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import PLOT_TEMPLATE, apply_terminal_layout, line_chart, spread_chart, srmc_comparison_chart
from src.config import ASSET_GROUPS
from src.data_loader import cached_srmc_comparison, load_historical_prices
from src.indicators import spread_suite
from src.preprocessing import prepare_historical
from src.transformations import normalize_to_100
from src.utils import configure_page, download_button, page_header, sample_data_notice


configure_page("Fuel & Dispatch")

df = prepare_historical(load_historical_prices())
default_start = max(pd.Timestamp("2026-02-01").date(), df["date"].min().date())

with st.sidebar:
    st.header("Fuel Console")
    min_date, max_date = df["date"].min().date(), df["date"].max().date()
    date_range = st.date_input("Date range", (default_start, max_date), min_value=min_date, max_value=max_date)
    markets = st.multiselect(
        "Markets",
        sorted(df["market"].unique()),
        default=["JKM", "JCC_LINKED_LNG", "CFR_JAPAN_COAL", "NEWCASTLE_COAL", "JEPX_SYSTEM", "USDJPY"],
    )
    with st.expander("SRMC assumptions"):
        gas_efficiency = st.slider("Gas efficiency", 0.45, 0.62, 0.55, 0.01)
        coal_efficiency = st.slider("Coal efficiency", 0.34, 0.46, 0.40, 0.01)
        gas_vom = st.number_input("Gas VOM (JPY/MWh)", value=500.0, step=50.0)
        coal_vom = st.number_input("Coal VOM (JPY/MWh)", value=700.0, step=50.0)

start, end = date_range if len(date_range) == 2 else (default_start, max_date)
filtered_df = df[df["date"].dt.date.between(start, end)]
selected_df = filtered_df[filtered_df["market"].isin(markets)]

if selected_df.empty:
    st.warning("No fuel or power data for the selected filters.")
    st.stop()

page_header(
    "Fuel & Dispatch",
    "Fuel price history, SRMC stack, and Japan power relative-value screens.",
    {
        "Fuel and power prices": "Bundled synthetic historical prices",
        "SRMC inputs": "Derived from dashboard fuel, FX, and power data",
    },
)
sample_data_notice()


def indexed_pair_chart(data: pd.DataFrame, pair_markets: list[str], labels: dict[str, str], title: str) -> go.Figure:
    wide = data[data["market"].isin(pair_markets)].pivot_table(index="date", columns="market", values="price", aggfunc="mean").sort_index()
    wide = wide.dropna(how="all").ffill().dropna()
    fig = go.Figure()
    for market in pair_markets:
        if market not in wide.columns or wide[market].dropna().empty:
            continue
        series = wide[market].dropna()
        indexed = series / series.iloc[0] * 100
        fig.add_trace(
            go.Scatter(
                x=indexed.index,
                y=indexed,
                mode="lines",
                name=labels.get(market, market),
                line=dict(width=2.6),
                hovertemplate=f"{labels.get(market, market)}: %{{y:.2f}}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        template=PLOT_TEMPLATE,
        hovermode="x unified",
        legend_title_text="",
        xaxis_title="",
        yaxis_title="Index = 100",
    )
    return apply_terminal_layout(fig)


st.markdown("### Fuel and Power Repricing")
st.plotly_chart(line_chart(normalize_to_100(selected_df), "date", "normalized", "market", "Selected Market Repricing Since Window Start", "Index = 100"), width="stretch")

for title, group in {"LNG": ASSET_GROUPS["LNG"], "Coal": ASSET_GROUPS["Coal"], "Crude": ASSET_GROUPS["Crude"], "FX": ["USDJPY"]}.items():
    group_df = filtered_df[filtered_df["market"].isin(group)]
    if not group_df.empty:
        y_title = "JPY per USD" if title == "FX" else None
        st.plotly_chart(line_chart(group_df, "date", "price", "market", f"{title} Price History", y_title), width="stretch")

st.markdown("### Dispatch Stack")
srmc = cached_srmc_comparison(
    filtered_df,
    gas_efficiency=gas_efficiency,
    coal_efficiency=coal_efficiency,
    gas_vom_jpy_mwh=gas_vom,
    coal_vom_jpy_mwh=coal_vom,
)
st.caption("SRMC is shown in JPY/kWh. Delivered CFR Japan coal is preferred when available; Newcastle is fallback benchmark context.")
if srmc.empty:
    st.warning("SRMC view needs JKM, JCC, USDJPY, JEPX system, and either CFR Japan coal or Newcastle coal data in the selected range.")
else:
    st.plotly_chart(srmc_comparison_chart(srmc, "Fuel SRMC Stack vs JEPX System"), width="stretch")

st.markdown("### Relative-Value Screens")
jkm_coal_markets = ["JKM", "NEWCASTLE_COAL"]
jkm_coal_subset = filtered_df[filtered_df["market"].isin(jkm_coal_markets)]
if set(jkm_coal_markets).issubset(set(jkm_coal_subset["market"].unique())):
    st.plotly_chart(
        indexed_pair_chart(
            jkm_coal_subset,
            jkm_coal_markets,
            {"JKM": "JKM LNG", "NEWCASTLE_COAL": "Newcastle thermal coal"},
            "JKM vs Newcastle Coal Repricing Since Window Start",
        ),
        width="stretch",
    )

pairs = {
    "JKM versus JCC-linked LNG": ["JKM", "JCC_LINKED_LNG"],
    "Power versus LNG": ["JEPX_SYSTEM", "JKM"],
    "Power versus coal": ["JEPX_SYSTEM", "NEWCASTLE_COAL"],
    "Brent versus JKM": ["BRENT", "JKM"],
    "USDJPY impact overlay": ["USDJPY", "JEPX_SYSTEM"],
}
for title, pair_markets in pairs.items():
    pair_df = filtered_df[filtered_df["market"].isin(pair_markets)]
    if not pair_df.empty:
        st.plotly_chart(line_chart(normalize_to_100(pair_df), "date", "normalized", "market", title, "Index = 100"), width="stretch")

spreads = spread_suite(filtered_df)
st.plotly_chart(spread_chart(spreads, "Fuel and Power Spread Screen", "Proxy spread / unconverted units"), width="stretch")
download_button(pd.concat([selected_df, spreads], ignore_index=True, sort=False), "fuel_dispatch_filtered.csv")
