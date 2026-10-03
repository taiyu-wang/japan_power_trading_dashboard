import pandas as pd
import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import intraday_convergence_chart, intraday_liquidity_heatmap, line_chart, spread_chart
from src.config import MARKET_NOTES
from src.data_loader import get_historical_prices as load_historical_prices, load_jepx_intraday
from src.indicators import detect_spikes, spread_suite
from src.jepx_market_data import intraday_liquidity_by_day
from src.preprocessing import prepare_historical
from src.utils import analysis_window, configure_page, dataframe_with_dates, download_button, page_header


configure_page("Power & Liquidity")

df = prepare_historical(load_historical_prices())
power = df[df["asset_class"] == "Power"]
if power.empty:
    st.warning("No power observations in the active history. Restore public data or upload power prices.")
    st.stop()
markets = ["JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI", "JEPX_INTRADAY", "JAPAN_POWER_FUTURES"]
with st.sidebar:
    st.header("Power Console")
    selected = st.multiselect("Power markets", markets, default=markets[:4])
    start, end = analysis_window(power)
    spike_market = st.selectbox("Spike monitor market", selected or markets)

filtered = power[power["market"].isin(selected) & power["date"].dt.date.between(start, end)]
if filtered.empty:
    st.warning("No power market data for the selected filters.")
    st.stop()

intraday = load_jepx_intraday()

page_header(
    "Power & Liquidity",
    "JEPX regional prices, basis, intraday liquidity and convergence.",
    {
        "Power prices": " / ".join(sorted(filtered.get("source_type", pd.Series("unverified", index=filtered.index)).unique())),
        "JEPX intraday": "Official JEPX public intraday CSV" if not intraday.empty else "No JEPX intraday CSV",
    },
)
st.caption("Official JEPX spot and intraday prices override bundled sample rows where public observations are available.")
for warning in df.attrs.get("load_warnings", []):
    st.warning(warning)
if intraday.attrs.get("load_warning"):
    st.warning(intraday.attrs["load_warning"])
if "JAPAN_POWER_FUTURES" in selected:
    st.info(MARKET_NOTES["JAPAN_POWER_FUTURES"])

st.markdown("### Price Stack")
st.plotly_chart(line_chart(filtered, "date", "price", "market", "Japan Power Price Stack", "JPY/kWh"), width="stretch")

spreads = spread_suite(filtered)
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
        daily_intraday = intraday_liquidity_by_day(intraday_filtered, df)
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

st.page_link("views/6_Supply_Mix.py", label="Generation and weather fundamentals", icon=":material/wb_sunny:")

st.markdown("### Operating Rhythm")
weekday = filtered.groupby(["market", "weekday", "is_weekend"], as_index=False)["price"].mean()
dataframe_with_dates(weekday, width="stretch", hide_index=True)

st.markdown("### Spike Checklist")
st.caption("Large daily moves for the selected market. Use as an event checklist, not as a standalone signal.")
spikes = detect_spikes(df, spike_market)
spikes = spikes[spikes["date"].dt.date.between(start, end)]
dataframe_with_dates(spikes[["date", "market", "price", "return_zscore"]].tail(20), width="stretch", hide_index=True)
download_button(filtered, "power_market_filtered.csv")
