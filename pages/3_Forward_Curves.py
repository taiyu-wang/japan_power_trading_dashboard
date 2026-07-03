import pandas as pd
import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import bar_chart, baseload_price_volume_chart, forward_curve_chart, power_futures_curve_chart, power_futures_peak_premium_chart
from src.config import MARKET_NOTES
from src.data_loader import get_forward_curves, load_jepx_baseload, load_power_futures, load_uploaded_curve, load_uploaded_power_futures
from src.indicators import forward_curve_metrics
from src.live_forward_curves import required_vendor_curve_sources
from src.power_futures import power_futures_front_snapshot, power_futures_peak_premium, power_futures_source_notes
from src.utils import configure_page, dataframe_with_dates, download_button, live_fetch_spinner, page_header, render_chart, source_status_panel


configure_page("Forward Curves")

with st.sidebar:
    st.header("Curve Console")
    use_live_curves = st.toggle("Refresh live public curves", value=False, help="Bundled curves load fastest on deployed Streamlit. Enable to attempt live Brent/JCC-derived curves.")
    uploaded = st.file_uploader("Upload forward curve CSV", type=["csv"])
    uploaded_power_futures = st.file_uploader("Upload monthly power futures CSV", type=["csv"], key="power_futures_upload")

with live_fetch_spinner("Refreshing live public forward curves...", use_live_curves):
    curves, curve_warnings, curve_source_label = get_forward_curves(use_live_curves)
if uploaded is not None:
    try:
        curves = load_uploaded_curve(uploaded)
        curve_source_label = "Uploaded CSV"
        curve_warnings = []
        st.sidebar.success("Uploaded curve loaded.")
        diagnostics = curves.attrs.get("diagnostics")
        if diagnostics:
            for warning in diagnostics.warnings:
                st.sidebar.warning(warning)
    except ValueError as exc:
        st.sidebar.error(str(exc))

page_header(
    "Forward Curves",
    (
        f"Curve source: {curve_source_label}. Brent live where available; JCC/JCC-linked LNG are Brent-derived proxies. "
        "JKM, coal, and Japan power forwards require licensed/vendor settlement or upload."
    ),
    {"Forward curves": curve_source_label},
)
for warning in curve_warnings:
    st.caption(warning)

if curves.empty:
    st.info("No forward curve data is available. Enable the live curve refresh in the sidebar or upload a forward curve CSV to populate this page; bundled fallback data is used otherwise.")
    st.stop()

try:
    if uploaded_power_futures is not None:
        power_futures = load_uploaded_power_futures(uploaded_power_futures)
        power_futures_source = "Uploaded monthly power futures CSV"
        st.sidebar.success("Uploaded monthly power futures loaded.")
    else:
        power_futures = load_power_futures()
        power_futures_source = "Bundled synthetic monthly power futures"
except ValueError as exc:
    st.sidebar.error(str(exc))
    power_futures = load_power_futures()
    power_futures_source = "Bundled synthetic monthly power futures"

coverage_rows = []
for live_market in sorted(curves["market"].unique()):
    coverage_rows.append({"market": live_market, "status": "loaded", "source_note": "Loaded in current curve dataset."})
coverage = pd.concat([pd.DataFrame(coverage_rows), required_vendor_curve_sources()], ignore_index=True)
with st.expander("Japan-relevant curve coverage", expanded=False):
    dataframe_with_dates(coverage, width="stretch", hide_index=True)

with st.sidebar:
    market = st.selectbox("Market", sorted(curves["market"].unique()))
    curve_dates = st.multiselect("Curve dates", sorted(curves["curve_date"].dt.date.unique(), reverse=True), default=sorted(curves["curve_date"].dt.date.unique(), reverse=True)[:3])

manual = st.sidebar.expander("Manual curve input")
with manual:
    manual_market = st.text_input("Market code", value=market)
    manual_price = st.number_input("Front price", value=12.0)
    if st.button("Append manual front point"):
        new = pd.DataFrame(
            {
                "curve_date": [pd.Timestamp.today().normalize()],
                "contract_month": [pd.Timestamp.today().normalize() + pd.offsets.MonthBegin(1)],
                "market": [manual_market],
                "region": ["Japan"],
                "price": [manual_price],
                "currency": ["USD"],
                "unit": ["MMBtu"],
                "contract_type": ["manual_analyst_input"],
                "source_note": ["Manual analyst input; verify source, unit, and settlement basis before use."],
            }
        )
        curves = pd.concat([curves, new], ignore_index=True)

filtered = curves[(curves["market"] == market) & (curves["curve_date"].dt.date.isin(curve_dates))]
if market in MARKET_NOTES:
    st.caption(MARKET_NOTES[market])
if "contract_type" in filtered.columns and not filtered.empty:
    contract_type = filtered["contract_type"].dropna().astype(str).unique()
    if len(contract_type):
        st.caption(f"Contract classification: {', '.join(contract_type)}")
render_chart(forward_curve_chart(filtered, f"{market} Forward Curve Comparison"))

metrics = forward_curve_metrics(curves[curves["market"] == market])
latest_metrics = metrics.sort_values("curve_date").tail(1)
cols = st.columns(5)
if not latest_metrics.empty:
    row = latest_metrics.iloc[0]
    cols[0].metric("Front premium", f"{row['front_month_premium']:.2f}")
    cols[1].metric("Prompt-quarter avg", f"{row['quarterly_average']:.2f}")
    cols[2].metric("Cal strip avg", f"{row['calendar_average']:.2f}")
    cols[3].metric("Back minus front", f"{row.get('steepness', 0):.2f}")
    cols[4].metric("M1-M2 carry", f"{row['rolling_carry']:.2f}")

strips = filtered.assign(quarter=filtered["contract_month"].dt.to_period("Q").astype(str)).groupby(["curve_date", "quarter"], as_index=False)["price"].mean()
render_chart(bar_chart(strips, "quarter", "price", "curve_date", "Quarterly Strip Analysis"))

if "source_note" in filtered.columns:
    with st.expander("Source / contract notes", expanded=False):
        dataframe_with_dates(filtered[["market", "contract_type", "source_note"]].drop_duplicates(), width="stretch", hide_index=True)
download_button(filtered, "forward_curves_filtered.csv")

futures_tab, baseload_tab = st.tabs(["Monthly Power Futures", "Physical Baseload Market"])

with futures_tab:
    st.markdown("### Japan Power Futures: Monthly Baseload and Peakload")
    st.caption(
        f"Power futures source: {power_futures_source}. JPX/TOCOM monthly electricity futures are cash-settled financial contracts referencing JEPX monthly area prices; they are not physical delivery."
    )
    source_status_panel({"Power futures": power_futures_source})
    with st.expander("Power futures source notes", expanded=False):
        dataframe_with_dates(power_futures_source_notes(), width="stretch", hide_index=True)

    with st.sidebar:
        futures_areas = st.multiselect("Power futures areas", sorted(power_futures["area"].unique()), default=sorted(power_futures["area"].unique()))
        futures_loads = st.multiselect("Power futures load types", sorted(power_futures["load_type"].unique()), default=sorted(power_futures["load_type"].unique()))
        futures_curve_dates = st.multiselect(
            "Power futures curve dates",
            sorted(power_futures["curve_date"].dt.date.unique(), reverse=True),
            default=sorted(power_futures["curve_date"].dt.date.unique(), reverse=True)[:2],
        )

    futures_filtered = power_futures[
        power_futures["area"].isin(futures_areas)
        & power_futures["load_type"].isin(futures_loads)
        & power_futures["curve_date"].dt.date.isin(futures_curve_dates)
    ].copy()

    if futures_filtered.empty:
        st.info("No monthly power futures rows match the sidebar filters. Broaden the areas, load types, or curve dates, or upload a monthly power futures CSV.")
    else:
        snapshot = power_futures_front_snapshot(futures_filtered)
        cards = st.columns(min(len(snapshot), 4) or 1)
        for col, (_, row) in zip(cards, snapshot.iterrows()):
            col.metric(f"{row['area']} {row['load_type']}", f"{row['settlement_price']:.2f}", f"{row['contract_month']:%b %Y}")

        render_chart(power_futures_curve_chart(futures_filtered, "Monthly Baseload / Peakload Futures Curve"))
        premium = power_futures_peak_premium(futures_filtered)
        if not premium.empty:
            render_chart(power_futures_peak_premium_chart(premium))
        with st.expander("Monthly power futures table", expanded=False):
            table_cols = ["curve_date", "contract_month", "area", "load_type", "settlement_price", "currency", "unit", "contract_type", "source"]
            dataframe_with_dates(futures_filtered[table_cols], width="stretch", hide_index=True)
        download_button(futures_filtered, "monthly_power_futures_filtered.csv", "Export monthly power futures CSV")

with baseload_tab:
    st.markdown("### JEPX Baseload Market Tracker")
    st.caption(
        "Public JEPX baseload market results. This is a physical baseload auction reference, separate from cash-settled monthly electricity futures."
    )
    source_status_panel({"JEPX baseload": "Processed public JEPX baseload CSV"})
    baseload = load_jepx_baseload()
    if baseload.empty:
        st.info("No processed JEPX baseload dataset is available. Rebuild the processed JEPX market-data CSVs (data/processed) to populate this tracker.")
    else:
        with st.sidebar:
            baseload_areas = st.multiselect("Baseload areas", sorted(baseload["area"].dropna().unique()), default=sorted(baseload["area"].dropna().unique()))
            baseload_years = st.multiselect(
                "Baseload fiscal years",
                sorted(baseload["fiscal_year"].dropna().astype(int).unique(), reverse=True),
                default=sorted(baseload["fiscal_year"].dropna().astype(int).unique(), reverse=True)[:3],
            )
        baseload_filtered = baseload[
            baseload["area"].isin(baseload_areas)
            & baseload["fiscal_year"].astype(int).isin(baseload_years)
        ].copy()
        if baseload_filtered.empty:
            st.info("No baseload market records for the selected filters. Broaden the areas or fiscal years in the sidebar to populate this view.")
        else:
            clean = baseload_filtered.dropna(subset=["clearing_price_jpy_kwh", "volume_mw"])
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Auction Records", f"{len(baseload_filtered):,}")
            b2.metric("Total Volume", f"{clean['volume_mw'].sum():,.1f} MW")
            b3.metric("Avg Price", f"{clean['clearing_price_jpy_kwh'].mean():.2f} JPY/kWh")
            latest_trade = clean.sort_values("trade_date").tail(1)
            b4.metric("Latest Trade", f"{latest_trade.iloc[0]['trade_date']:%Y-%m-%d}" if not latest_trade.empty else "n/a")
            render_chart(baseload_price_volume_chart(baseload_filtered))
            summary = clean.groupby(["fiscal_year", "area"], as_index=False).agg(
                avg_price=("clearing_price_jpy_kwh", "mean"),
                total_volume_mw=("volume_mw", "sum"),
                records=("product_name", "count"),
            )
            st.markdown("### Baseload Area Summary")
            dataframe_with_dates(summary, width="stretch", hide_index=True)
            with st.expander("Baseload auction records", expanded=False):
                dataframe_with_dates(baseload_filtered, width="stretch", hide_index=True)
            download_button(baseload_filtered, "jepx_baseload_filtered.csv", "Export JEPX baseload CSV")
