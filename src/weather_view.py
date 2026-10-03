import pandas as pd
import streamlit as st
from src.charts import bar_chart, line_chart, temperature_power_chart
from src.config import WEATHER_SOURCE_NOTE
from src.data_loader import get_weather_temperatures, get_historical_prices as load_historical_prices
from src.preprocessing import prepare_historical
from src.weather import weather_power_join
from src.utils import analysis_window, download_button, page_header



def render_weather_seasonality(embedded: bool = False):
    hist = prepare_historical(load_historical_prices())
    power = hist[hist["asset_class"] == "Power"]
    if hist.empty:
        st.info("No historical observations are available.")
        return

    with st.sidebar:
        st.header("Demand Console")
        use_live_weather = st.toggle(
            "Refresh Open-Meteo weather",
            value=False,
            help="The default scheduled snapshot loads fastest. Enable to query Open-Meteo on demand for the selected window.",
        )
        start, end = analysis_window(hist)
        regions = st.multiselect("Regions", ["Tokyo", "Kansai"], default=["Tokyo", "Kansai"])
        markets = sorted(hist["market"].unique())
        market = st.selectbox("Seasonal market", markets, index=markets.index("JEPX_SYSTEM") if "JEPX_SYSTEM" in markets else 0)
        years = st.multiselect("Compare years", sorted(hist["year"].unique()), default=sorted(hist["year"].unique())[-3:])
        st.caption(WEATHER_SOURCE_NOTE)

    weather, warnings, source_label = get_weather_temperatures(use_live_weather, start, end)
    for warning in warnings:
        st.warning(warning)
    weather = weather[weather["date"].dt.date.between(start, end) & weather["region"].isin(regions)]
    joined = weather_power_join(weather, power[power["date"].dt.date.between(start, end)])

    if not embedded:
        page_header("Weather & Seasonality", "Tokyo/Kansai temperature and recurring price patterns.", {"Weather": source_label})

    view = st.segmented_control("Weather view", ["Weather regime", "Seasonal pattern"], default="Weather regime", key="weather_view")

    if view == "Weather regime":
        st.markdown("### Weather Regime")
        st.caption(f"Weather source: {source_label}. Temperature is daily 2m mean in deg C; CDD base 22 deg C, HDD base 18 deg C.")
        if weather.empty:
            st.warning("No weather data for the selected filters.")
        else:
            latest = weather.sort_values("date").groupby("region", as_index=False).tail(1)
            cols = st.columns(len(latest) or 1)
            for col, (_, row) in zip(cols, latest.iterrows()):
                col.metric(row["region"], f"{row['temperature_mean_c']:.1f} deg C")
                col.caption(f"{row['date']:%d %b %Y} | CDD {row['cooling_degree_day']:.1f} | HDD {row['heating_degree_day']:.1f}")

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

    if view == "Seasonal pattern":
        st.markdown("### Seasonal Price Pattern")
        subset = hist[(hist["market"] == market) & (hist["year"].isin(years))].copy()

        if subset.empty:
            st.warning("No seasonality data for the selected years.")
        else:
            st.caption(f"Full calendar years selected independently of the delivery window: {', '.join(map(str, sorted(subset['year'].unique())))}.")
            if subset.get("source_type", pd.Series(dtype=str)).eq("synthetic").any():
                st.warning("Sample observations are included. This is a demonstration seasonal profile, not a verified climatology or trading forecast.")
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
