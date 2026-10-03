import pandas as pd
import streamlit as st

from src.charts import line_chart, spread_chart, srmc_comparison_chart
from src.config import ASSET_GROUPS
from src.data_loader import get_historical_prices, load_uploaded_historical
from src.indicators import calculate_srmc_comparison, spread_suite
from src.preprocessing import prepare_historical
from src.transformations import normalize_to_100
from src.utils import analysis_window, configure_page, download_button, market_board


def _restore_history():
    st.session_state.pop("historical_override", None)
    st.session_state["upload_epoch"] = st.session_state.get("upload_epoch", 0) + 1


configure_page("Fuel & Margins")
with st.sidebar:
    with st.expander("Desk data"):
        upload = st.file_uploader("Historical prices CSV", type=["csv"], key=f"historical_upload_{st.session_state.get('upload_epoch', 0)}")
        if upload is not None:
            try:
                st.session_state["historical_override"] = load_uploaded_historical(upload)
                st.success("Desk history active across all pages.")
            except (ValueError, pd.errors.ParserError) as exc:
                st.error(str(exc))
        st.button("Restore public / sample history", icon=":material/restart_alt:", on_click=_restore_history)

history = prepare_historical(get_historical_prices())
with st.sidebar:
    start, end = analysis_window(history)
    with st.expander("SRMC assumptions"):
        settings = st.session_state.get("srmc_settings", {})
        gas_efficiency = st.slider("Gas efficiency", 0.45, 0.62, settings.get("gas_efficiency", 0.55), 0.01)
        coal_efficiency = st.slider("Coal efficiency", 0.34, 0.46, settings.get("coal_efficiency", 0.40), 0.01)
        gas_vom = st.number_input("Gas VOM (JPY/MWh)", min_value=0.0, value=settings.get("gas_vom_jpy_mwh", 500.0), step=50.0)
        coal_vom = st.number_input("Coal VOM (JPY/MWh)", min_value=0.0, value=settings.get("coal_vom_jpy_mwh", 700.0), step=50.0)
        settings = dict(gas_efficiency=gas_efficiency, coal_efficiency=coal_efficiency, gas_vom_jpy_mwh=gas_vom, coal_vom_jpy_mwh=coal_vom)
        st.session_state["srmc_settings"] = settings

filtered = history[history["date"].dt.date.between(start, end)]
st.title("Fuel & Margins")
st.caption(f"{start:%d %b %Y} - {end:%d %b %Y} | Indicative dispatch economics in JPY/kWh")
view = st.segmented_control("View", ["Dispatch economics", "Fuel inputs", "Relative value"], default="Dispatch economics", key="fuel_view")

if view == "Dispatch economics":
    srmc = calculate_srmc_comparison(history, **settings)
    srmc = srmc[srmc["date"].dt.date.between(start, end)] if not srmc.empty else srmc
    if srmc.empty or srmc["jkm_gas_srmc"].notna().sum() == 0:
        st.warning("Current SRMC unavailable: upload dated JKM, USD/JPY and coal observations; add JCC for the oil-linked range. Stale fuel marks are not extended into this period.")
    else:
        last = srmc.dropna(subset=["coal_srmc", "jkm_gas_srmc"]).tail(1)
        if not last.empty:
            row = last.iloc[0]
            cols = st.columns(3)
            cols[0].metric("Coal SRMC", f"{row['coal_srmc']:.2f} JPY/kWh")
            cols[1].metric("JKM gas SRMC", f"{row['jkm_gas_srmc']:.2f} JPY/kWh")
            cols[2].metric("Gas minus coal", f"{row['jkm_gas_srmc'] - row['coal_srmc']:+.2f} JPY/kWh")
            st.caption(f"Input comparison through {row['date']:%d %b %Y}; source classification is shown in the input board.")
        if filtered.get("source_type", pd.Series(dtype=str)).eq("synthetic").any():
            st.warning("Sample fuel observations are present. Historical SRMC is demonstration-only, not a current trading signal.")
        st.plotly_chart(srmc_comparison_chart(srmc, "Coal, JKM and oil-linked gas costs versus power"), width="stretch")
        costs = srmc[["date", "jkm_gas_srmc", "coal_srmc", "jepx_system"]]
        margins = pd.concat([
            pd.DataFrame({"date": costs["date"], "market": "Indicative gas margin", "price": costs["jepx_system"] - costs["jkm_gas_srmc"]}),
            pd.DataFrame({"date": costs["date"], "market": "Indicative coal margin", "price": costs["jepx_system"] - costs["coal_srmc"]}),
        ]).dropna()
        st.plotly_chart(spread_chart(margins, "Power less indicative SRMC", "JPY/kWh"), width="stretch")
    with st.expander("Cost basis and input dates"):
        st.write(f"Gas heat rate: {3.412 / gas_efficiency:.2f} MMBtu/MWh. Coal: 6,000 kcal/kg NAR at {coal_efficiency:.0%} efficiency. CFR Japan is preferred; Newcastle is benchmark fallback. Oil-linked gas uses JCC x 11-13% + USD 0.50/MMBtu. These are screening costs, not plant margins or marginal-fuel identification.")
        st.caption("Newcastle is a FOB benchmark, not a delivered Japan cost. Freight, carbon, startup and plant constraints are excluded.")
        market_board(history[history["market"].isin(["JKM", "JCC", "USDJPY", "CFR_JAPAN_COAL", "NEWCASTLE_COAL"])])
elif view == "Fuel inputs":
    market_board(filtered[filtered["asset_class"].ne("Power")])
    group = st.selectbox("Input group", ["LNG", "Coal", "Crude", "FX"])
    prices = filtered[filtered["market"].isin(ASSET_GROUPS[group])]
    if prices.empty:
        st.info("No observations in this period. Select an earlier period or upload desk history.")
    else:
        st.plotly_chart(line_chart(prices, "date", "price", "market", f"{group} prices", "JPY per USD" if group == "FX" else None), width="stretch")
else:
    pair = st.selectbox("Comparison", ["JKM vs Newcastle", "JKM vs oil-linked LNG", "Tokyo vs Kansai"])
    pairs = {"JKM vs Newcastle": ["JKM", "NEWCASTLE_COAL"], "JKM vs oil-linked LNG": ["JKM", "JCC_LINKED_LNG"], "Tokyo vs Kansai": ["JEPX_TOKYO", "JEPX_KANSAI"]}
    data = filtered[filtered["market"].isin(pairs[pair])]
    common = data.pivot_table(index="date", columns="market", values="price").dropna() if not data.empty else pd.DataFrame()
    if len(common.columns) != 2 or common.empty:
        st.info("No overlapping observations for this comparison.")
    else:
        long = common.reset_index().melt("date", var_name="market", value_name="price")
        st.plotly_chart(line_chart(normalize_to_100(long), "date", "normalized", "market", pair, "Index = 100"), width="stretch")
    spreads = spread_suite(history, **settings)
    spreads = spreads[spreads["date"].dt.date.between(start, end)]
    spread_unit = st.radio("Spread basis", ["JPY/kWh", "USD/MMBtu"], horizontal=True)
    spreads = spreads[spreads["unit"].eq(spread_unit)].dropna(subset=["price"])
    if not spreads.empty:
        st.plotly_chart(spread_chart(spreads, "Same-unit spread comparison", spread_unit), width="stretch")
download_button(filtered, "fuel_margins_history.csv")
