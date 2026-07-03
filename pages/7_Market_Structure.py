import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.charts import (
    offer_stack_curve_chart,
    offer_stack_daily_price_sensitivity_chart,
    offer_stack_depth_heatmap,
    offer_stack_period_shift_chart,
    offer_stack_price_attribution_chart,
    offer_stack_scenario_bar,
    offer_stack_shift_chart,
    offer_stack_tightness_spread_chart,
)
from src.data_loader import (
    cached_offer_stack_depth,
    cached_offer_stack_period_shift,
    cached_offer_stack_price_sensitivity,
    cached_offer_stack_scenarios,
    cached_offer_stack_shift,
    cached_offer_stack_shift_benchmarks,
    cached_offer_stack_shift_by_block,
    cached_offer_stack_signal_payload,
    cached_tokyo_kansai_stack_tightness_spread,
    get_jepx_offer_stack,
    load_jepx_offer_stack_compact_curves,
    load_jepx_offer_stack_depth,
)
from src.offer_stack import (
    offer_stack_time_period,
    prepare_offer_stack_curve,
)
from src.utils import configure_page, dataframe_with_dates, download_button, live_fetch_spinner, page_header, render_chart


def _time_block(time_code: int) -> str:
    return offer_stack_time_period(time_code)


def _desk_takeaway(row: pd.Series) -> str:
    regime = row.get("stack_regime", "n/a")
    up = row.get("upside_depth_mw", float("nan"))
    down = row.get("downside_depth_mw", float("nan"))
    price = row.get("clearing_price_estimate", float("nan"))
    if regime == "Scarcity stack":
        return f"Upside depth is thin at {up:,.0f} MW around {price:.2f} JPY/kWh; small demand or outage shocks can reprice the slot quickly."
    if regime == "Solar compression stack":
        return f"Downside depth is thin at {down:,.0f} MW; additional low-marginal-cost supply can pressure clearing prices."
    if regime == "Thin stack":
        return f"The stack is not deeply buffered around clearing. Treat price sensitivity as elevated even without a fuel move."
    return f"Depth around clearing is comparatively well buffered. Stack sensitivity is lower unless area splitting or fuel repricing changes the curve."


def _format_signed(value: float, unit: str = "MW", decimals: int = 0) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{float(value):+,.{decimals}f} {unit}"


def _shift_takeaway(summary: dict) -> str:
    if not summary:
        return "Curve shift could not be calculated for the selected periods."
    sell = summary.get("sell_shift_at_clearing_mw", 0)
    buy = summary.get("buy_shift_at_clearing_mw", 0)
    net = summary.get("net_depth_shift_at_clearing_mw", 0)
    price = summary.get("current_clearing_price_estimate", float("nan"))
    if net < -500:
        bias = "tighter"
        implication = "less sell depth or more buy depth around clearing; upside price sensitivity is higher."
    elif net > 500:
        bias = "looser"
        implication = "more sell depth or weaker buy depth around clearing; price pressure is more contained."
    else:
        bias = "broadly stable"
        implication = "net depth around clearing has not shifted enough to change the regime on its own."
    return (
        f"At the current estimated clearing level of {price:.2f} JPY/kWh, sell depth shifted {sell:+,.0f} MW "
        f"and buy depth shifted {buy:+,.0f} MW versus the comparison period. The curve screens {bias}: {implication}"
    )


def _build_shift_by_block(filtered_curves: pd.DataFrame, prior_date: pd.Timestamp, current_date: pd.Timestamp, area_group: str) -> pd.DataFrame:
    return cached_offer_stack_shift_by_block(filtered_curves, prior_date, current_date, area_group)


def _signal_interpretation(row: pd.Series, scenarios: pd.DataFrame, spread_row: pd.Series | None = None) -> list[str]:
    signals = [_desk_takeaway(row)]
    if not scenarios.empty:
        upside = scenarios.loc[scenarios["demand_shift_mw"] > 0, "price_impact_jpy_kwh"].max()
        downside = scenarios.loc[scenarios["demand_shift_mw"] < 0, "price_impact_jpy_kwh"].min()
        if pd.notna(upside) and pd.notna(downside):
            if upside > abs(downside):
                signals.append(f"Upward shocks screen more expensive than relief: +1 GW repricing is roughly {_format_signed(upside, 'JPY/kWh', 2)}.")
            elif abs(downside) > upside:
                signals.append(f"Downside relief has the larger move: -1 GW repricing is roughly {_format_signed(downside, 'JPY/kWh', 2)}.")
            else:
                signals.append("Demand-shift pricing is fairly symmetric around the selected block.")
    if spread_row is not None and not spread_row.empty:
        side = spread_row.get("tighter_area", "n/a")
        spread = spread_row.get("tightness_spread_mw")
        if side in {"Tokyo", "Kansai"} and pd.notna(spread):
            signals.append(f"Area spread watch: {side} has the thinner stack by about {abs(float(spread)):,.0f} MW at this block.")
    return signals


configure_page("Market Structure")

with st.sidebar:
    st.header("Offer Stack")
    use_live = st.toggle(
        "Refresh latest month from JEPX",
        value=False,
        help="Large public download. Local cache is used by default for fast dashboard loading.",
    )
    use_full_raw = st.toggle(
        "Use full local raw stack",
        value=False,
        help="Loads the large local raw bidding-curve cache when available. Keep off for deployed/GitHub use.",
    )

raw_data = pd.DataFrame()
warnings: list[str] = []
source_label = "Processed compact JEPX offer-stack analytics"
if use_live or use_full_raw:
    with live_fetch_spinner("Refreshing latest-month JEPX offer stack (large public download)...", use_live):
        raw_data, warnings, source_label = get_jepx_offer_stack(use_live=use_live)
for warning in warnings:
    st.warning(warning)

processed_depth = load_jepx_offer_stack_depth()
processed_curves = load_jepx_offer_stack_compact_curves()
using_raw = not raw_data.empty
curve_data = raw_data if using_raw else processed_curves

if curve_data.empty or (processed_depth.empty and not using_raw):
    st.warning(
        "No JEPX offer-stack analytics are available. Run `PYTHONPATH=. python3 -m src.offer_stack` locally to build raw and processed caches."
    )
    st.stop()

curve_data = curve_data.copy()
curve_data["delivery_date"] = pd.to_datetime(curve_data["delivery_date"], errors="coerce").dt.normalize()
curve_data = curve_data.dropna(subset=["delivery_date", "time_code", "area_group"])

min_date = curve_data["delivery_date"].min().date()
max_date = curve_data["delivery_date"].max().date()
today_japan = pd.Timestamp.now(tz="Asia/Tokyo").date()
default_end = min(today_japan, max_date)
default_start = max(min_date, (pd.Timestamp(default_end) - pd.Timedelta(days=4)).date())
area_options = sorted(curve_data["area_group"].dropna().unique())

with st.sidebar:
    date_range = st.date_input(
        "Delivery date range",
        (default_start, default_end),
        min_value=min_date,
        max_value=max_date,
    )
    area_group = st.selectbox("Area group", area_options, index=area_options.index("System Price") if "System Price" in area_options else 0)
    time_code = st.slider("Delivery block", 1, 48, 37, help="JEPX day-ahead uses 48 half-hour blocks. Block 37 is around 18:00.")
    price_band = st.selectbox("Depth band", [5, 10, 20], index=0, format_func=lambda value: f"+/- {value} JPY/kWh")
    sensitivity_shock = st.selectbox("Sensitivity shock", [500, 1000], index=0, format_func=lambda value: f"+{value:,} MW net demand")
    comparison_mode = st.selectbox("Curve shift comparison", ["Previous day", "Previous week", "Start of selected range"], index=1)

start, end = date_range if len(date_range) == 2 else (default_start, default_end)
date_filtered_curves = curve_data[curve_data["delivery_date"].dt.date.between(start, end)].copy()
filtered_curves = date_filtered_curves[date_filtered_curves["area_group"].eq(area_group)].copy()

if using_raw:
    all_depth_source = cached_offer_stack_depth(date_filtered_curves, price_band=float(price_band))
    filtered_depth_source = (
        all_depth_source[all_depth_source["area_group"].eq(area_group)].copy() if not all_depth_source.empty else pd.DataFrame()
    )
    data_mode = "Full raw local/live stack"
else:
    depth_source = processed_depth.copy()
    depth_source["delivery_date"] = pd.to_datetime(depth_source["delivery_date"], errors="coerce").dt.normalize()
    all_depth_source = depth_source[
        depth_source["delivery_date"].dt.date.between(start, end)
        & depth_source["price_band_jpy_kwh"].eq(float(price_band))
    ].copy()
    filtered_depth_source = (
        all_depth_source[all_depth_source["area_group"].eq(area_group)].copy() if not all_depth_source.empty else pd.DataFrame()
    )
    data_mode = "Compact processed analytics"

page_header(
    "Market Structure",
    f"JEPX day-ahead bidding curves translated into stack depth, curve shifts, and area tightness reads. Coverage: {min_date} to {max_date}.",
    {"JEPX offer stack": source_label, "Stack depth": data_mode},
)
st.info(
    "This page uses public aggregate JEPX day-ahead bidding-curve data. It is ex-post market depth, not live order-book, participant-level, or plant-level offer data."
)

if filtered_curves.empty:
    st.info("No offer-stack rows for the selected date range and area group. Widen the delivery date range, switch area group, or enable the live JEPX refresh in the sidebar.")
    st.stop()

selected_date = pd.Timestamp(end)
curve = prepare_offer_stack_curve(filtered_curves, selected_date, time_code, area_group)
if curve.empty:
    available_dates = sorted(filtered_curves["delivery_date"].dt.date.unique())
    selected_date = pd.Timestamp(available_dates[-1])
    curve = prepare_offer_stack_curve(filtered_curves, selected_date, time_code, area_group)

depth = filtered_depth_source
if depth.empty:
    st.warning("Stack depth metrics could not be calculated for the selected view.")
    st.info("Adjust the depth band or date range, or enable the live JEPX refresh in the sidebar to rebuild depth analytics.")
    st.stop()

latest_depth = depth[(depth["delivery_date"].eq(selected_date.normalize())) & (depth["time_code"].eq(time_code))]
if latest_depth.empty:
    latest_depth = depth.sort_values(["delivery_date", "time_code"]).tail(1)

row = latest_depth.iloc[0]

scenario_base = filtered_curves[
    filtered_curves["delivery_date"].eq(selected_date.normalize())
    & filtered_curves["time_code"].eq(time_code)
    & filtered_curves["area_group"].eq(area_group)
]
scenarios = cached_offer_stack_scenarios(scenario_base, demand_shifts_mw=(-1000, -500, 500, 1000))

scenario_day_base = filtered_curves[
    filtered_curves["delivery_date"].eq(selected_date.normalize())
    & filtered_curves["area_group"].eq(area_group)
]
day_sensitivity = cached_offer_stack_price_sensitivity(scenario_day_base, shocks_mw=(-1000, -500, 500, 1000))

area_spread = cached_tokyo_kansai_stack_tightness_spread(all_depth_source, price_band=float(price_band))
area_spread = area_spread[area_spread["delivery_date"].eq(selected_date.normalize())].copy() if not area_spread.empty else pd.DataFrame()
selected_spread = area_spread[area_spread["time_code"].eq(time_code)].tail(1) if not area_spread.empty else pd.DataFrame()
spread_row = selected_spread.iloc[0] if not selected_spread.empty else None

read_tab, shift_tab, spread_tab, data_tab = st.tabs(["Stack Read", "Curve Shift", "Tokyo/Kansai Spread", "Data"])

with read_tab:
    st.markdown("### Market Read")
    top = st.columns(4)
    top[0].metric("Estimated Clearing", f"{row['clearing_price_estimate']:.2f} JPY/kWh")
    top[1].metric("Upside Depth", f"{row['upside_depth_mw']:,.0f} MW")
    top[2].metric("Downside Depth", f"{row['downside_depth_mw']:,.0f} MW")
    top[3].metric("Stack Read", row["stack_regime"])

    signal_lines = "".join(f"<li>{line}</li>" for line in _signal_interpretation(row, scenarios, spread_row))
    st.markdown(f"<div class='desk-panel'><b>Stack-derived signal interpretation</b><ul>{signal_lines}</ul></div>", unsafe_allow_html=True)

    st.markdown("### Bidding Curve")
    st.caption(
        "Sell and buy curves are cumulative public bidding curves. The clearing marker is an estimated curve crossing and should be reconciled with official JEPX price data."
    )
    render_chart(offer_stack_curve_chart(curve, f"{area_group} Bidding Curve | {selected_date.date()} | Product {time_code}"))

    st.markdown("### Stack Tightness Map")
    st.caption("Lower values are thinner depth near clearing. Use this first to find blocks where small shocks can move price.")
    render_chart(offer_stack_depth_heatmap(depth, f"{area_group} Tightest Depth Around Clearing"))

    st.markdown("### Price Sensitivity")
    st.caption("Ex-post repricing estimate from shifting net demand across every delivery block on the selected day.")
    render_chart(
        offer_stack_daily_price_sensitivity_chart(
            day_sensitivity,
            shock_mw=int(sensitivity_shock),
            title=f"{area_group} Price Impact From +{sensitivity_shock:,} MW Net Demand | {selected_date.date()}",
        )
    )
    if scenarios.empty:
        st.info("Selected-block sensitivity could not be calculated for this view.")
    else:
        render_chart(offer_stack_scenario_bar(scenarios, "Selected Block Price Impact From Net Demand Shift"))

with shift_tab:
    st.markdown("### Curve Shift")
    available_dates = sorted(filtered_curves["delivery_date"].dt.normalize().drop_duplicates())
    current_date = selected_date.normalize()
    if comparison_mode == "Previous day":
        target_prior = current_date - pd.Timedelta(days=1)
    elif comparison_mode == "Previous week":
        target_prior = current_date - pd.Timedelta(days=7)
    else:
        target_prior = pd.Timestamp(start)
    prior_candidates = [date for date in available_dates if date <= target_prior and date < current_date]
    if not prior_candidates:
        prior_candidates = [date for date in available_dates if date < current_date]
    prior_date = prior_candidates[-1] if prior_candidates else None

    if prior_date is None:
        st.info("Curve shift needs at least two delivery dates in the selected view.")
    else:
        shift = cached_offer_stack_shift(filtered_curves, prior_date, current_date, time_code, area_group)
        shift_summary = shift.attrs.get("summary", {})
        st.caption(
            f"Comparison: {pd.Timestamp(prior_date).date()} vs {current_date.date()} for product {time_code}. "
            "Positive sell shift means more offered depth at that price; positive buy shift means stronger bid depth."
        )
        s1, s2, s3 = st.columns(3)
        s1.metric("Sell Shift at Clearing", f"{shift_summary.get('sell_shift_at_clearing_mw', 0):+,.0f} MW")
        s2.metric("Buy Shift at Clearing", f"{shift_summary.get('buy_shift_at_clearing_mw', 0):+,.0f} MW")
        s3.metric("Net Depth Shift", f"{shift_summary.get('net_depth_shift_at_clearing_mw', 0):+,.0f} MW")
        st.markdown(f"<div class='desk-panel'><b>Curve shift read:</b> {_shift_takeaway(shift_summary)}</div>", unsafe_allow_html=True)
        render_chart(offer_stack_shift_chart(shift, f"{area_group} Curve Shift | {pd.Timestamp(prior_date).date()} to {current_date.date()}"))

        with st.expander("Benchmark and block-level diagnostics", expanded=False):
            st.markdown("#### Benchmark Curve Shift")
            st.caption("Latest selected block versus prior 7-day, 30-day, and selected-window average curves.")
            benchmarks = cached_offer_stack_shift_benchmarks(
                filtered_curves,
                current_date=current_date,
                time_code=time_code,
                area_group=area_group,
                lookback_days=(7, 30),
                selected_start=start,
                selected_end=end,
            )
            if benchmarks.empty:
                st.info("Benchmark curve-shift comparison is unavailable for this selection.")
            else:
                benchmark_options = benchmarks["benchmark_label"].drop_duplicates().tolist()
                benchmark_label = st.selectbox(
                    "Benchmark period",
                    benchmark_options,
                    format_func=lambda value: {
                        "7d_avg": "Prior 7-day average",
                        "30d_avg": "Prior 30-day average",
                        "selected_avg": "Selected-window average",
                    }.get(value, value),
                )
                benchmark_view = benchmarks[benchmarks["benchmark_label"].eq(benchmark_label)]
                render_chart(offer_stack_shift_chart(benchmark_view, f"{area_group} Latest vs {benchmark_label.replace('_', ' ')}"))

            st.markdown("#### Curve Shift by Delivery Block")
            block_shift = _build_shift_by_block(filtered_curves, prior_date, current_date, area_group)
            if block_shift.empty:
                st.info("No block-level curve-shift summary is available for the selected comparison.")
            else:
                block_table = block_shift.sort_values("net_depth_shift_at_clearing_mw").copy()
                dataframe_with_dates(
                    block_table[
                        [
                            "time_code",
                            "delivery_block",
                            "clearing_price_estimate",
                            "sell_shift_at_clearing_mw",
                            "buy_shift_at_clearing_mw",
                            "net_depth_shift_at_clearing_mw",
                        ]
                    ],
                    width="stretch",
                    hide_index=True,
                )

        st.markdown("### Time-of-Day Shift Attribution")
        st.caption(
            "Aggregates all 48 half-hour curves into trading periods. Positive supply-side tightening means less sell depth; positive buy-side strength means stronger demand depth."
        )
        period_shift = cached_offer_stack_period_shift(filtered_curves, prior_date, current_date, area_group)
        if period_shift.empty:
            st.info("Time-of-day shift attribution is unavailable for this comparison.")
        else:
            period_summary = (
                period_shift.groupby("delivery_period", as_index=False)
                .agg(
                    blocks=("time_code", "count"),
                    avg_supply_tightening_mw=("supply_tightening_mw", "mean"),
                    avg_buy_side_strength_mw=("demand_strength_mw", "mean"),
                    avg_net_tightening_pressure_mw=("net_tightening_pressure_mw", "mean"),
                    avg_price_change_jpy_kwh=("price_change_jpy_kwh", "mean"),
                    avg_supply_price_contribution_jpy_kwh=("supply_price_contribution_jpy_kwh", "mean"),
                    avg_demand_price_contribution_jpy_kwh=("demand_price_contribution_jpy_kwh", "mean"),
                )
                .sort_values("avg_net_tightening_pressure_mw", ascending=False)
                .reset_index(drop=True)
            )
            lead_period = period_summary.iloc[0]
            price_period = period_summary.loc[period_summary["avg_price_change_jpy_kwh"].abs().idxmax()]
            p1, p2, p3 = st.columns(3)
            p1.metric("Tightest Shift Period", str(lead_period["delivery_period"]))
            p2.metric("Net Tightening Pressure", f"{lead_period['avg_net_tightening_pressure_mw']:+,.0f} MW")
            p3.metric("Largest Price Move Period", f"{price_period['delivery_period']} ({price_period['avg_price_change_jpy_kwh']:+.2f})")
            render_chart(offer_stack_period_shift_chart(period_shift, f"{area_group} Supply/Demand Shift by Time of Day"))
            render_chart(offer_stack_price_attribution_chart(period_shift, f"{area_group} Counterfactual Price Attribution by Time of Day"))
            dataframe_with_dates(period_summary, width="stretch", hide_index=True)

with spread_tab:
    st.markdown("### Tokyo / Kansai Stack Spread")
    st.caption("Tokyo minus Kansai tightest depth. Negative means Tokyo has the thinner stack; positive means Kansai is thinner.")
    if area_spread.empty:
        st.info("Tokyo/Kansai area-stack spread is not available in the selected data window. It appears when JEPX area groups are present in the offer-stack cache.")
    else:
        latest_spread = spread_row if spread_row is not None else area_spread.tail(1).iloc[0]
        s1, s2, s3 = st.columns(3)
        s1.metric("Selected Block Spread", _format_signed(latest_spread["tightness_spread_mw"]))
        s2.metric("Thinner Side", latest_spread["tighter_area"])
        s3.metric("Selected Block", _time_block(int(latest_spread["time_code"])))
        render_chart(offer_stack_tightness_spread_chart(area_spread, f"Tokyo/Kansai Stack Tightness | {selected_date.date()}"))

    st.markdown("### Stack-Derived Desk Prompts")
    signal_payload = cached_offer_stack_signal_payload(filtered_curves, depth=depth)
    if signal_payload.empty:
        st.info("No stack-derived prompts are available for the selected view.")
    else:
        prompt_rows = signal_payload.sort_values("stack_tightest_depth_mw").head(3)
        prompt_cols = st.columns(len(prompt_rows))
        for idx, (_, prompt) in enumerate(prompt_rows.iterrows()):
            impact_cols = [col for col in prompt.index if col.startswith("stack_price_impact_up_")]
            impact_text = "n/a"
            if impact_cols:
                impacts = prompt[impact_cols].dropna()
                if not impacts.empty:
                    impact_text = f"{impacts.max():+.2f} JPY/kWh"
            prompt_cols[idx].markdown(
                f"""
                <div class="signal-card">
                    <h4>{prompt['area_group']} | Block {int(prompt['time_code'])}</h4>
                    <div class="small-muted">{pd.Timestamp(prompt['delivery_date']).date()} | {prompt['stack_regime']}</div>
                    <p><strong>Trader takeaway:</strong> Thin depth near clearing raises exposure to demand, outage, and renewable forecast errors.</p>
                    <div class="small-muted"><strong>Depth:</strong> {prompt['stack_tightest_depth_mw']:,.0f} MW | <strong>Upside shock:</strong> {impact_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

with data_tab:
    st.markdown("### Analyst Table")
    table = depth.assign(time_block=depth["time_code"].map(_time_block)).sort_values(
        ["delivery_date", "time_code", "area_group"]
    )
    dataframe_with_dates(table.tail(200), width="stretch", hide_index=True)
    download_button(table, "jepx_offer_stack_depth.csv", "Export stack depth CSV")
