import pandas as pd
import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import bar_chart, line_chart, temperature_power_chart
from src.config import DEFAULT_FOCUS_START, WEATHER_SOURCE_NOTE
from src.data_loader import get_weather_temperatures, load_historical_prices
from src.preprocessing import prepare_historical
from src.weather import weather_power_join
from src.utils import configure_page, download_button, page_header, sample_data_notice


configure_page("Weather & Seasonality")

hist = prepare_historical(load_historical_prices())
power = hist[hist["asset_class"] == "Power"]
min_date, max_date = hist["date"].min().date(), hist["date"].max().date()
default_start = max(pd.Timestamp(DEFAULT_FOCUS_START).date(), min_date)

with st.sidebar:
    st.header("Demand Console")
    use_live_weather = st.toggle("Refresh Open-Meteo weather", value=False, help="Bundled weather loads fastest. Enable to attempt Open-Meteo historical daily temperatures.")
    date_range = st.date_input("Analysis window", (default_start, max_date), min_value=min_date, max_value=max_date)
    regions = st.multiselect("Regions", ["Tokyo", "Kansai"], default=["Tokyo", "Kansai"])
    market = st.selectbox("Seasonal market", sorted(hist["market"].unique()), index=sorted(hist["market"].unique()).index("JEPX_SYSTEM"))
    years = st.multiselect("Compare years", sorted(hist["year"].unique()), default=sorted(hist["year"].unique())[-3:])
    regime = st.selectbox("Climate regime lens", ["All years", "El Niño years", "La Niña years", "Neutral years"])
    st.caption(WEATHER_SOURCE_NOTE)

start, end = date_range if len(date_range) == 2 else (default_start, max_date)
weather, warnings, source_label = get_weather_temperatures(use_live_weather, start, end)
for warning in warnings:
    st.warning(warning)
weather = weather[weather["date"].dt.date.between(start, end) & weather["region"].isin(regions)]
joined = weather_power_join(weather, power[power["date"].dt.date.between(start, end)])

page_header(
    "Weather & Seasonality",
    "Tokyo/Kansai temperature, degree-day pressure, and recurring seasonal power patterns.",
    {"Weather": source_label, "Power prices": "Bundled synthetic historical prices"},
)
sample_data_notice()

weather_tab, seasonality_tab = st.tabs(["Weather Regime", "Seasonal Pattern"])

with weather_tab:
    st.markdown("### Weather Regime")
    st.caption(f"Weather source: {source_label}. Temperature is daily 2m mean in deg C; CDD base 22 deg C, HDD base 18 deg C.")
    if weather.empty:
        st.warning("No weather data for the selected filters.")
    else:
        latest = weather.sort_values("date").groupby("region", as_index=False).tail(1)
        cols = st.columns(len(latest) or 1)
        for col, (_, row) in zip(cols, latest.iterrows()):
            col.metric(row["region"], f"{row['temperature_mean_c']:.1f} deg C", f"CDD {row['cooling_degree_day']:.1f} | HDD {row['heating_degree_day']:.1f}")

        st.plotly_chart(line_chart(weather, "date", "temperature_mean_c", "region", "Tokyo/Kansai Daily Temperature", "deg C"), width="stretch")

        degree_pressure = weather.copy()
        degree_pressure["degree_day_pressure"] = degree_pressure["cooling_degree_day"] + degree_pressure["heating_degree_day"]
        st.plotly_chart(line_chart(degree_pressure, "date", "degree_day_pressure", "region", "Tokyo/Kansai Degree-Day Pressure", "CDD + HDD"), width="stretch")

        if not joined.empty:
            left, right = st.columns(2)
            with left:
                st.plotly_chart(temperature_power_chart(joined, "Tokyo", "Tokyo Temperature vs JEPX Tokyo"), width="stretch")
            with right:
                st.plotly_chart(temperature_power_chart(joined, "Kansai", "Kansai Temperature vs JEPX Kansai"), width="stretch")

        with st.expander("Regional spread and degree-day totals", expanded=False):
            wide = weather.pivot_table(index="date", columns="region", values="temperature_mean_c", aggfunc="mean")
            if {"Tokyo", "Kansai"}.issubset(wide.columns):
                spread = (wide["Tokyo"] - wide["Kansai"]).reset_index(name="value")
                spread["market"] = "Tokyo minus Kansai temperature"
                st.plotly_chart(line_chart(spread, "date", "value", "market", "Tokyo-Kansai Temperature Spread", "deg C"), width="stretch")

            degree_summary = weather.groupby("region", as_index=False)[["cooling_degree_day", "heating_degree_day"]].sum()
            degree_long = degree_summary.melt("region", var_name="metric", value_name="value")
            st.plotly_chart(bar_chart(degree_long, "region", "value", "metric", "Cumulative Degree-Day Load"), width="stretch")
        download_button(weather, "weather_temperature_filtered.csv")
        if not joined.empty:
            download_button(joined, "weather_power_join.csv", "Export weather-power join as CSV")

with seasonality_tab:
    st.markdown("### Seasonal Price Pattern")
    subset = hist[(hist["market"] == market) & (hist["year"].isin(years))].copy()
    if regime != "All years":
        mapping = {"El Niño years": [2023, 2024], "La Niña years": [2021, 2022], "Neutral years": [2025, 2026]}
        subset = subset[subset["year"].isin(mapping[regime])]

    if subset.empty:
        st.warning("No seasonality data for the selected years/regime.")
    else:
        st.caption(f"Seasonality lens: {regime}; years in view: {', '.join(map(str, sorted(subset['year'].unique())))}")
        monthly = subset.groupby(["year", "month", "month_name"], as_index=False)["price"].mean()
        month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly["month_name"] = pd.Categorical(monthly["month_name"], categories=month_order, ordered=True)
        monthly = monthly.sort_values(["year", "month_name"])
        st.plotly_chart(line_chart(monthly, "month_name", "price", "year", f"{market} Monthly Seasonal Profile"), width="stretch")

        weekly = subset.groupby(["year", "week"], as_index=False)["price"].mean()
        st.plotly_chart(line_chart(weekly, "week", "price", "year", "Weekly Seasonal Track"), width="stretch")

        summer = subset[subset["month"].isin([7, 8, 9])].groupby("year", as_index=False)["price"].mean().assign(season="Peak summer")
        winter = subset[subset["month"].isin([12, 1, 2])].groupby("year", as_index=False)["price"].mean().assign(season="Peak winter")
        st.plotly_chart(bar_chart(pd.concat([summer, winter]), "year", "price", "season", "Peak Summer / Winter Comparison"), width="stretch")
        download_button(subset, "seasonality_filtered.csv")
