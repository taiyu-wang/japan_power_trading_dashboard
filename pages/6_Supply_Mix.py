import pandas as pd
import streamlit as st
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import generation_share_area_chart, generation_volume_bar_chart, line_chart
from src.data_loader import (
    get_generation_mix,
    load_generation_mix,
    load_supply_mix_daily_shape,
    load_supply_mix_residual_thermal,
    load_uploaded_generation_mix,
)
from src.supply_mix import add_generation_share, latest_generation_snapshot, residual_thermal_summary, source_catalog, thermal_share_summary
from src.utils import configure_page, dataframe_with_dates, download_button, page_header, render_chart, sample_data_notice


configure_page("Supply Mix")

with st.sidebar:
    st.header("Supply Console")
    use_processed_public = st.toggle(
        "Use processed public supply data",
        value=True,
        help="Uses compact Tokyo/Kansai aggregates derived from public half-hourly supply files when available.",
    )
    uploaded = st.file_uploader("Upload monthly generation mix CSV", type=["csv"])
    st.caption("Required columns: month, area, generation_type, generation_gwh")

source_label = "Bundled synthetic regional generation mix"
source_warnings: list[str] = []
try:
    if uploaded is not None:
        raw_mix = load_uploaded_generation_mix(uploaded)
        source_label = "Uploaded CSV"
        st.sidebar.success("Uploaded generation mix loaded.")
    else:
        raw_mix, source_warnings, source_label = get_generation_mix(use_processed_public)
except ValueError as exc:
    st.sidebar.error(str(exc))
    raw_mix = load_generation_mix()
    source_label = "Bundled synthetic regional generation mix"
for warning in source_warnings:
    st.warning(warning)

page_header(
    "Supply Mix",
    "Tokyo and Kansai monthly generation share by fuel type, thermal dependence, and solar-shape context.",
    {"Generation mix": source_label},
)
sample_data_notice()

mix = add_generation_share(raw_mix)
daily_shape = load_supply_mix_daily_shape() if use_processed_public and uploaded is None else pd.DataFrame()
processed_residual = load_supply_mix_residual_thermal() if use_processed_public and uploaded is None else pd.DataFrame()

with st.sidebar:
    areas = st.multiselect("Areas", sorted(mix["area"].unique()), default=["Tokyo", "Kansai"])
    fuels = st.multiselect("Generation types", sorted(mix["generation_type"].dropna().astype(str).unique()), default=["Gas", "Coal", "Nuclear", "Solar", "Hydro", "Wind", "Biomass", "Oil"])
    min_month, max_month = mix["month"].min().date(), mix["month"].max().date()
    month_range = st.date_input("Month range", (min_month, max_month), min_value=min_month, max_value=max_month)

start, end = month_range if len(month_range) == 2 else (min_month, max_month)
filtered = mix[
    mix["area"].isin(areas)
    & mix["generation_type"].astype(str).isin(fuels)
    & mix["month"].dt.date.between(start, end)
].copy()

if filtered.empty:
    st.warning("No generation mix data for the selected filters.")
    st.stop()

mix_tab, thermal_tab, source_tab = st.tabs(["Generation Share", "Thermal Dependence", "Source Detail"])

with mix_tab:
    latest = latest_generation_snapshot(filtered)
    latest_month = latest["month"].max()
    if pd.notna(latest_month):
        st.markdown(f"### Latest Mix Snapshot ({latest_month:%Y-%m})")
        for area in sorted(latest["area"].unique()):
            area_latest = latest[latest["area"] == area].head(4)
            cols = st.columns(len(area_latest) or 1)
            for col, (_, row) in zip(cols, area_latest.iterrows()):
                col.metric(f"{area} {row['generation_type']}", f"{row['share_pct']:.1f}%", f"{row['generation_gwh']:,.0f} GWh")

    st.markdown("### Monthly Market Share")
    render_chart(generation_share_area_chart(filtered, "Tokyo/Kansai Monthly Generation Share"))

    st.markdown("### Monthly Generation Volume")
    render_chart(generation_volume_bar_chart(filtered, "Tokyo/Kansai Monthly Generation by Source"))

with thermal_tab:
    st.markdown("### Thermal Dependence")
    thermal = thermal_share_summary(filtered)
    thermal_view = thermal[thermal["bucket"] == "Thermal"].copy()
    thermal_fig = line_chart(thermal_view, "month", "share_pct", "area", "Thermal Share of Generation", "%")
    thermal_fig.update_xaxes(tickformat="%b %Y", hoverformat="%b %Y")
    render_chart(thermal_fig)

    st.markdown("### Residual Thermal and Solar Shape")
    if processed_residual.empty:
        residual = residual_thermal_summary(filtered)
    else:
        residual = processed_residual[
            processed_residual["area"].isin(areas)
            & processed_residual["month"].dt.date.between(start, end)
        ].copy()
    if not residual.empty:
        residual_fig = line_chart(residual, "month", "residual_thermal_share_pct", "area", "Residual Thermal Share", "% of demand / generation")
        residual_fig.update_xaxes(tickformat="%b %Y", hoverformat="%b %Y")
        render_chart(residual_fig)

    if daily_shape.empty:
        st.info(
            "Daily solar-shape and curtailment metrics appear when processed public half-hourly data is present. "
            "Keep 'Use processed public supply data' enabled and run `PYTHONPATH=. python -m src.supply_mix_pipeline` to build it."
        )
    else:
        shape = daily_shape[daily_shape["area"].isin(areas)].copy()
        if not shape.empty:
            latest_shape_date = shape["date"].max()
            shape_start = latest_shape_date - pd.Timedelta(days=90)
            shape = shape[shape["date"].between(shape_start, latest_shape_date)]
            c1, c2 = st.columns(2)
            with c1:
                render_chart(line_chart(shape, "date", "thermal_ramp_mw", "area", "Evening Thermal Ramp", "MW"))
            with c2:
                render_chart(line_chart(shape, "date", "solar_share_midday_pct", "area", "Midday Solar Share", "% of demand"))
            curtailment = shape[shape["renewable_curtailment_mwh"].gt(0)].copy()
            if not curtailment.empty:
                render_chart(line_chart(curtailment, "date", "renewable_curtailment_mwh", "area", "Renewable Curtailment Watch", "MWh/day"))

with source_tab:
    st.markdown("### Data Source Status")
    st.caption(
        f"Current dataset: {source_label}. Public processed data is compact monthly/daily output only; raw half-hourly files are not loaded by the page."
    )
    dataframe_with_dates(source_catalog(), width="stretch", hide_index=True)

    st.markdown("### Analyst Notes")
    st.markdown(
        """
        - Public Tokyo/Kansai half-hourly supply files are aggregated before the dashboard loads, keeping the page fast.
        - Residual thermal is a trader proxy for fuel-exposed demand after nuclear, hydro, biomass, solar, wind, and geothermal output.
        - Midday solar share and evening thermal ramp help explain solar belly compression and evening peak repricing risk.
        - For production desk use, reconcile public aggregates against official TSO/OCCTO/METI or licensed vendor data.
        """
    )

download_button(filtered, "generation_mix_filtered.csv", "Export generation mix CSV")
