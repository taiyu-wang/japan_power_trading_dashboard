import pandas as pd
import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import intraday_convergence_chart, intraday_liquidity_heatmap, line_chart, spread_chart, temperature_power_chart
from src.config import MARKET_NOTES
from src.data_loader import (
    cached_detect_spikes,
    cached_intraday_liquidity_by_day,
    cached_spread_suite,
    cached_weather_power_join,
    get_weather_temperatures,
    load_jepx_intraday,
    load_prepared_historical,
)
from src.utils import configure_page, dataframe_with_dates, download_button, page_header, sample_data_notice


configure_page("Power Market")

df = load_prepared_historical()
power = df[df["asset_class"] == "Power"]
markets = ["JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI", "JEPX_INTRADAY", "JAPAN_POWER_FUTURES"]
default_focus_start = pd.Timestamp("2026-02-01").date()
with st.sidebar:
    st.header("Power Console")
    selected = st.multiselect("Power markets", markets, default=markets[:4])
    min_date, max_date = power["date"].min().date(), power["date"].max().date()
    default_start = max(default_focus_start, min_date)
    date_range = st.date_input("Date range", (default_start, max_date), min_value=min_date, max_value=max_date)
    spike_market = st.selectbox("Spike monitor market", selected or markets)

start, end = date_range if len(date_range) == 2 else (default_start, max_date)
filtered = power[power["market"].isin(selected) & power["date"].dt.date.between(start, end)]
if filtered.empty:
    st.warning("No power market data for the selected filters.")
    st.stop()

intraday = load_jepx_intraday()
weather, weather_warnings, weather_source = get_weather_temperatures(False)

page_header(
    "Power Market",
    "JEPX system, regional basis, intraday spread, weather-linked price context, and event screens.",
    {
        "Power prices": "Bundled synthetic historical prices",
        "JEPX intraday": "Processed public JEPX intraday CSV" if not intraday.empty else "No local JEPX intraday CSV",
        "Weather": weather_source,
    },
)
sample_data_notice()
st.info(MARKET_NOTES["JAPAN_POWER_FUTURES"])

st.markdown("### Price Stack")
st.plotly_chart(line_chart(filtered, "date", "price", "market", "Japan Power Price Stack", "JPY/kWh"), width="stretch")

spreads = cached_spread_suite(df)
st.markdown("### Basis and Intraday")
st.plotly_chart(spread_chart(spreads[spreads["market"].isin(["Tokyo minus Kansai", "Spot minus intraday"])], "Regional Basis and Spot-Intraday Spread", "JPY/kWh"), width="stretch")

st.markdown("### Intraday Liquidity and Convergence")
st.caption("Public JEPX intraday data by half-hour product. Volume and contract count indicate liquidity; convergence compares day-ahead system price against intraday average.")
if intraday.empty:
    st.info("No processed JEPX intraday dataset is available.")
else:
    intraday_filtered = intraday[intraday["delivery_date"].dt.date.between(start, end)].copy()
    if intraday_filtered.empty:
        st.info("No JEPX intraday records in the selected date range.")
    else:
        daily_intraday = cached_intraday_liquidity_by_day(intraday_filtered, df)
        i1, i2, i3, i4 = st.columns(4)
        latest_intraday = daily_intraday.sort_values("delivery_date").tail(1)
        if not latest_intraday.empty:
            row = latest_intraday.iloc[0]
            i1.metric("Intraday Avg", f"{row['intraday_average_price']:.2f} JPY/kWh")
            i2.metric("Spot-Intraday", f"{row['spot_intraday_spread']:+.2f} JPY/kWh")
            i3.metric("Intraday Volume", f"{row['total_volume_mwh']:,.0f} MWh")
            i4.metric("Contracts", f"{row['number_of_contracts']:,.0f}")
        st.plotly_chart(intraday_convergence_chart(daily_intraday), width="stretch")
        st.plotly_chart(intraday_liquidity_heatmap(intraday_filtered, "number_of_contracts", "JEPX Intraday Contract Count by Half-Hour"), width="stretch")
        download_button(intraday_filtered, "jepx_intraday_filtered.csv", "Export JEPX intraday CSV")

weather = weather[weather["date"].dt.date.between(start, end)]
joined_weather = cached_weather_power_join(weather, power[power["date"].dt.date.between(start, end)])
st.markdown("### Weather-Price Context")
st.caption(f"Weather source: {weather_source}. Temperature screens are weather-price proxies, not observed power demand MW.")
for warning in weather_warnings:
    st.warning(warning)
if not joined_weather.empty:
    w1, w2 = st.columns(2)
    with w1:
        st.plotly_chart(temperature_power_chart(joined_weather, "Tokyo", "Tokyo Temperature vs JEPX Tokyo"), width="stretch")
    with w2:
        st.plotly_chart(temperature_power_chart(joined_weather, "Kansai", "Kansai Temperature vs JEPX Kansai"), width="stretch")
else:
    st.warning("Power-weather join is empty for the selected dates.")

st.markdown("### Operating Rhythm")
weekday = filtered.groupby(["market", "weekday", "is_weekend"], as_index=False)["price"].mean()
dataframe_with_dates(weekday, width="stretch", hide_index=True)

st.markdown("### Spike Checklist")
st.caption("Large daily moves for the selected market. Use as an event checklist, not as a standalone signal.")
dataframe_with_dates(cached_detect_spikes(df, spike_market)[["date", "market", "price", "return_zscore"]].tail(20), width="stretch", hide_index=True)
download_button(filtered, "power_market_filtered.csv")
