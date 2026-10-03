import pandas as pd
import streamlit as st

from src.charts import line_chart
from src.config import DEFAULT_MARKETS
from src.data_loader import get_historical_prices, get_power_news
from src.preprocessing import prepare_historical
from src.signals import generate_trading_signals
from src.utils import analysis_window, configure_page, download_button, market_board, signal_watchlist


def render_overview():
    configure_page("Overview")
    history = prepare_historical(get_historical_prices())
    with st.sidebar:
        start, end = analysis_window(history)
        markets = st.multiselect("Market board", sorted(history["market"].unique()), default=[m for m in DEFAULT_MARKETS if m in set(history["market"])])
    filtered = history[history["date"].dt.date.between(start, end)]
    st.title("Japan Fuel & Power")
    st.caption(f"Desk overview | {start:%d %b %Y} - {end:%d %b %Y} | Delivery dates in JST")
    power = filtered[filtered["market"].isin(["JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI"])]
    cols = st.columns(3)
    for col, market, label in zip(cols, ["JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI"], ["System", "Tokyo", "Kansai"]):
        observations = power[power["market"].eq(market)].dropna(subset=["price"]).sort_values("date")
        if observations.empty:
            col.metric(label, "n/a")
        else:
            quote = observations.iloc[-1]
            col.metric(label, f"{quote['price']:.2f} JPY/kWh")
            col.caption(f"{quote['date']:%d %b %Y} | {quote.get('source_type', 'unverified').title()}")
    if not power.empty:
        st.plotly_chart(line_chart(power, "date", "price", "market", "Japan power prices", "JPY/kWh"), width="stretch")
    st.subheader("Market board")
    st.caption("Latest observation per market, independent of the chart window. Changes end at each quote date.")
    market_board(history[history["market"].isin(markets)])
    st.subheader("Current desk watchlist")
    signals = generate_trading_signals(history, pd.DataFrame(), srmc_settings=st.session_state.get("srmc_settings"))
    signal_watchlist(signals)
    st.page_link("views/5_Trading_Signals.py", label="All alerts and market news", icon=":material/notifications:")
    st.page_link("views/2_Fuel_Dispatch.py", label="Fuel & margins", icon=":material/bolt:")
    news, warnings, source = get_power_news(False)
    if not news.empty and "sample" not in source.lower():
        st.subheader("Japan power events")
        for _, event in news.head(3).iterrows():
            st.caption(f"{event['published_at']:%d %b %Y} | {event['source']}")
            if str(event["url"]).startswith(("https://", "http://")):
                st.link_button(event["title"], event["url"], icon=":material/open_in_new:")
            else:
                st.write(event["title"])
    issues = history.attrs.get("load_warnings", []) + warnings
    if issues:
        with st.expander("Data availability"):
            for issue in issues:
                st.warning(issue)
    download_button(filtered[filtered["market"].isin(markets)], "overview_market_data.csv")


st.set_page_config(page_title="Japan Fuel & Power", layout="wide")
page = st.navigation([
    st.Page(render_overview, title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/1_Power_Market.py", title="Power & Liquidity", url_path="Power_Market", icon=":material/bolt:"),
    st.Page("views/7_Market_Structure.py", title="Market Structure", url_path="Market_Structure", icon=":material/stacked_line_chart:"),
    st.Page("views/2_Fuel_Dispatch.py", title="Fuel & Margins", url_path="Fuel_Dispatch", icon=":material/local_fire_department:"),
    st.Page("views/6_Supply_Mix.py", title="Fundamentals", url_path="Supply_Mix", icon=":material/wb_sunny:"),
    st.Page("views/3_Forward_Curves.py", title="Curves & Hedges", url_path="Forward_Curves", icon=":material/timeline:"),
    st.Page("views/4_Weather_Seasonality.py", title="Weather & Seasonality", url_path="Weather_Seasonality", visibility="hidden"),
    st.Page("views/5_Trading_Signals.py", title="Trading Signals", url_path="Trading_Signals", visibility="hidden"),
])
page.run()
