from io import StringIO

import numpy as np
import pandas as pd

from src.offer_stack import (
    JEPX_OFFER_STACK_COLUMNS,
    _nearest_price_index,
    build_offer_stack_signal_payload,
    calculate_offer_stack_depth,
    calculate_offer_stack_price_sensitivity,
    calculate_offer_stack_period_shift,
    calculate_offer_stack_scenarios,
    calculate_offer_stack_shift,
    calculate_offer_stack_shift_benchmarks,
    calculate_tokyo_kansai_stack_tightness_spread,
    compact_offer_stack_curves,
    generate_offer_stack_processed_artifacts,
    normalize_jepx_offer_stack,
    normalize_jepx_offer_stack_upload,
    parse_jepx_available_offer_stack_dates,
    prepare_offer_stack_curve,
)


def test_normalize_jepx_offer_stack_translates_jepx_bid_curve_columns():
    raw = pd.read_csv(
        StringIO(
            "電力受渡日,商品コード,入札価格(円/kWh),売入札量累積(MW),買入札量累積(MW),分断エリア連番\n"
            "20260531,1,0.00,0.0,38388.2,\n"
            "20260531,1,0.01,11225.8,38388.2,1\n"
        )
    )
    areas = pd.read_csv(
        StringIO(
            "電力受渡日,商品コード,エリアグループ,分断エリア連番\n"
            "20260531,1,システムプライス,\n"
            "20260531,1,東北・東京,1\n"
        )
    )

    out = normalize_jepx_offer_stack(raw, areas, source_url="https://www.jepx.jp/example.csv")

    assert list(out.columns) == JEPX_OFFER_STACK_COLUMNS
    assert out.iloc[0]["delivery_date"] == pd.Timestamp("2026-05-31")
    assert out.iloc[0]["time_code"] == 1
    assert out.iloc[0]["area_group"] == "System Price"
    assert out.iloc[1]["area_group"] == "Tohoku / Tokyo"
    assert out.iloc[1]["bid_price_jpy_kwh"] == 0.01
    assert out.iloc[1]["sell_cumulative_mw"] == 11225.8
    assert out.iloc[1]["buy_cumulative_mw"] == 38388.2
    assert out.iloc[1]["source"] == "JEPX day-ahead bidding curve"


def test_parse_jepx_available_offer_stack_dates_returns_oldest_and_latest():
    available = parse_jepx_available_offer_stack_dates("20260602,20220601")

    assert available.latest == pd.Timestamp("2026-06-02")
    assert available.oldest == pd.Timestamp("2022-06-01")


def test_normalize_jepx_offer_stack_upload_accepts_cached_english_schema():
    raw = pd.DataFrame(
        {
            "delivery_date": ["2026-05-31"],
            "time_code": [1],
            "area_group_code": [""],
            "area_group": ["System Price"],
            "bid_price_jpy_kwh": ["10.5"],
            "sell_cumulative_mw": ["30100"],
            "buy_cumulative_mw": ["29800"],
            "source": ["JEPX day-ahead bidding curve"],
            "source_url": ["https://www.jepx.jp/example.csv"],
            "downloaded_at": ["2026-06-01 00:00:00"],
        }
    )

    out = normalize_jepx_offer_stack_upload(raw)

    assert list(out.columns) == JEPX_OFFER_STACK_COLUMNS
    assert out.iloc[0]["delivery_date"] == pd.Timestamp("2026-05-31")
    assert out.iloc[0]["bid_price_jpy_kwh"] == 10.5


def test_prepare_offer_stack_curve_finds_crossing_price():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-05-31"] * 5,
            "time_code": [1] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    curve = prepare_offer_stack_curve(stack, "2026-05-31", 1, "System Price")

    assert curve.iloc[2]["net_supply_mw"] == 0
    assert curve.attrs["clearing_price_estimate"] == 10


def test_calculate_offer_stack_depth_measures_mw_around_clearing_price():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-05-31"] * 5,
            "time_code": [1] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    depth = calculate_offer_stack_depth(stack, price_band=5)

    assert depth.iloc[0]["clearing_price_estimate"] == 10
    assert depth.iloc[0]["upside_depth_mw"] == 2000
    assert depth.iloc[0]["downside_depth_mw"] == 2000
    assert depth.iloc[0]["stack_regime"] == "Balanced stack"


def test_nearest_price_index_matches_idxmin_including_ties_and_duplicates():
    prices = np.array([0.0, 4.0, 4.0, 6.0, 10.0, 10.0, 10.0, 16.0, 20.0])
    series = pd.Series(prices)
    targets = [-5.0, 0.0, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 13.0, 18.0, 20.0, 25.0]

    for target in targets:
        expected = int((series - target).abs().idxmin())
        assert _nearest_price_index(prices, target) == expected, f"mismatch at target={target}"


def test_calculate_offer_stack_depth_ties_resolve_to_lower_price_like_idxmin():
    # up_price (13) is equidistant from 10 and 16; down_price (7) from 4 and 10.
    # The prior idxmin implementation picked the first (lower-price) row on ties.
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-05-31"] * 5,
            "time_code": [1] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 4, 10, 16, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    depth = calculate_offer_stack_depth(stack, price_band=3)

    assert depth.iloc[0]["clearing_price_estimate"] == 10
    assert depth.iloc[0]["upside_depth_mw"] == 0
    assert depth.iloc[0]["downside_depth_mw"] == 2000


def test_calculate_offer_stack_scenarios_matches_prior_per_row_implementation():
    rows = []
    for day, offset in zip(["2026-05-30", "2026-05-31"], [0, 250]):
        for area in ["System Price", "Tokyo"]:
            for time_code in [1, 37]:
                for price, sell, buy in [(0, 1000, 5200), (5, 2000, 4100), (10, 3000, 3000), (15, 4000, 1900), (20, 5000, 800)]:
                    rows.append(
                        {
                            "delivery_date": day,
                            "time_code": time_code,
                            "area_group": area,
                            "bid_price_jpy_kwh": price,
                            "sell_cumulative_mw": sell + offset,
                            "buy_cumulative_mw": buy - offset,
                        }
                    )
    stack = pd.DataFrame(rows)
    shifts = (-800, -300, 300, 800)

    scenarios = calculate_offer_stack_scenarios(stack, demand_shifts_mw=shifts)

    def price_at_net_supply_reference(curve, target):
        if target > 0 and curve["net_supply_mw"].ge(target).any():
            idx = curve[curve["net_supply_mw"].ge(target)].index[0]
        elif target < 0 and curve["net_supply_mw"].le(target).any():
            idx = curve[curve["net_supply_mw"].le(target)].index[-1]
        else:
            idx = (curve["net_supply_mw"] - target).abs().idxmin()
        return float(curve.loc[idx, "bid_price_jpy_kwh"])

    depth = calculate_offer_stack_depth(stack, price_band=5.0)
    expected_rows = []
    work = stack.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    for _, item in depth.iterrows():
        curve = prepare_offer_stack_curve(work, item["delivery_date"], int(item["time_code"]), str(item["area_group"]))
        base_price = float(item["clearing_price_estimate"])
        for shift in shifts:
            scenario_price = price_at_net_supply_reference(curve, float(shift))
            expected_rows.append(
                {
                    "delivery_date": item["delivery_date"],
                    "time_code": int(item["time_code"]),
                    "area_group": item["area_group"],
                    "base_price_jpy_kwh": base_price,
                    "demand_shift_mw": int(shift),
                    "scenario_price_jpy_kwh": scenario_price,
                    "price_impact_jpy_kwh": scenario_price - base_price,
                }
            )
    expected = pd.DataFrame(expected_rows).sort_values(
        ["delivery_date", "time_code", "area_group", "demand_shift_mw"]
    ).reset_index(drop=True)

    pd.testing.assert_frame_equal(scenarios, expected)


def test_calculate_offer_stack_scenarios_reprices_demand_shift():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-05-31"] * 5,
            "time_code": [1] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    scenarios = calculate_offer_stack_scenarios(stack, demand_shifts_mw=(-1000, 1000))

    assert scenarios.loc[scenarios["demand_shift_mw"].eq(1000), "scenario_price_jpy_kwh"].iloc[0] == 15
    assert scenarios.loc[scenarios["demand_shift_mw"].eq(-1000), "scenario_price_jpy_kwh"].iloc[0] == 5


def test_calculate_offer_stack_shift_compares_current_and_prior_curves():
    prior = pd.DataFrame(
        {
            "delivery_date": ["2026-05-30"] * 3,
            "time_code": [37] * 3,
            "area_group": ["System Price"] * 3,
            "bid_price_jpy_kwh": [10, 20, 30],
            "sell_cumulative_mw": [1000, 2000, 3000],
            "buy_cumulative_mw": [5000, 4000, 3000],
        }
    )
    current = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 3,
            "time_code": [37] * 3,
            "area_group": ["System Price"] * 3,
            "bid_price_jpy_kwh": [10, 20, 30],
            "sell_cumulative_mw": [800, 1700, 2800],
            "buy_cumulative_mw": [5400, 4300, 3200],
        }
    )
    stack = pd.concat([prior, current], ignore_index=True)

    shift = calculate_offer_stack_shift(stack, "2026-05-30", "2026-06-02", 37, "System Price")

    assert shift.iloc[0]["sell_shift_mw"] == -200
    assert shift.iloc[0]["buy_shift_mw"] == 400
    assert shift.attrs["summary"]["sell_shift_at_clearing_mw"] == -200
    assert shift.attrs["summary"]["buy_shift_at_clearing_mw"] == 200
    assert shift.attrs["summary"]["current_clearing_price_estimate"] == 30


def test_compact_offer_stack_curves_samples_price_ladder():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 3,
            "time_code": [37] * 3,
            "area_group": ["System Price"] * 3,
            "bid_price_jpy_kwh": [10, 20, 30],
            "sell_cumulative_mw": [1000, 2000, 3000],
            "buy_cumulative_mw": [5000, 4000, 3000],
        }
    )

    compact = compact_offer_stack_curves(stack, price_levels=(10, 25, 30))

    assert compact["bid_price_jpy_kwh"].tolist() == [10, 25, 30]
    assert compact.loc[compact["bid_price_jpy_kwh"].eq(25), "sell_cumulative_mw"].iloc[0] == 2500
    assert compact.loc[compact["bid_price_jpy_kwh"].eq(25), "buy_cumulative_mw"].iloc[0] == 3500
    assert compact["source"].iloc[0] == "JEPX processed sampled bidding curve"


def test_generate_offer_stack_processed_artifacts_returns_depth_and_compact_curves():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 3,
            "time_code": [37] * 3,
            "area_group": ["System Price"] * 3,
            "bid_price_jpy_kwh": [10, 20, 30],
            "sell_cumulative_mw": [1000, 2000, 3000],
            "buy_cumulative_mw": [5000, 4000, 3000],
        }
    )

    depth, compact = generate_offer_stack_processed_artifacts(stack, price_bands=(5, 10), price_levels=(10, 20, 30))

    assert sorted(depth["price_band_jpy_kwh"].unique().tolist()) == [5.0, 10.0]
    assert len(compact) == 3


def test_calculate_offer_stack_price_sensitivity_reports_bidirectional_shocks():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 5,
            "time_code": [37] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    sensitivity = calculate_offer_stack_price_sensitivity(stack, shocks_mw=(-1000, 1000))

    assert sensitivity.loc[sensitivity["shock_mw"].eq(1000), "price_impact_jpy_kwh"].iloc[0] == 5
    assert sensitivity.loc[sensitivity["shock_mw"].eq(-1000), "price_impact_jpy_kwh"].iloc[0] == -5
    assert sensitivity.loc[sensitivity["shock_mw"].eq(1000), "sensitivity_jpy_kwh_per_100mw"].iloc[0] == 0.5
    assert sensitivity["reference_level"].unique().tolist() == ["clearing"]


def test_calculate_offer_stack_price_sensitivity_can_anchor_to_available_curve_level():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 5,
            "time_code": [37] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    sensitivity = calculate_offer_stack_price_sensitivity(stack, shocks_mw=(1000,), reference_prices=(15,))

    assert sensitivity.iloc[0]["reference_price_jpy_kwh"] == 15
    assert sensitivity.iloc[0]["reference_net_supply_mw"] == 2000
    assert sensitivity.iloc[0]["scenario_price_jpy_kwh"] == 20
    assert sensitivity.iloc[0]["reference_level"] == "price_15"


def test_calculate_offer_stack_shift_benchmarks_compares_latest_to_average_windows():
    rows = []
    for day, offset in zip(pd.date_range("2026-06-01", periods=8, freq="D"), range(8)):
        for price, sell, buy in [(10, 1000, 5000), (20, 2000, 4000), (30, 3000, 3000)]:
            rows.append(
                {
                    "delivery_date": day,
                    "time_code": 37,
                    "area_group": "System Price",
                    "bid_price_jpy_kwh": price,
                    "sell_cumulative_mw": sell + offset * 10,
                    "buy_cumulative_mw": buy - offset * 5,
                }
            )
    stack = pd.DataFrame(rows)

    benchmarks = calculate_offer_stack_shift_benchmarks(
        stack,
        current_date="2026-06-08",
        time_code=37,
        lookback_days=(7,),
        selected_start="2026-06-01",
        selected_end="2026-06-03",
    )

    avg7 = benchmarks[benchmarks["benchmark_label"].eq("7d_avg")]
    selected = benchmarks[benchmarks["benchmark_label"].eq("selected_avg")]
    assert avg7.loc[avg7["bid_price_jpy_kwh"].eq(20), "sell_shift_mw"].iloc[0] == 40
    assert avg7.loc[avg7["bid_price_jpy_kwh"].eq(20), "buy_shift_mw"].iloc[0] == -20
    assert selected.loc[selected["bid_price_jpy_kwh"].eq(20), "sell_shift_mw"].iloc[0] == 60


def test_calculate_offer_stack_period_shift_attributes_supply_and_demand_moves():
    prior = pd.DataFrame(
        {
            "delivery_date": ["2026-06-01"] * 5,
            "time_code": [37] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )
    current = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 5,
            "time_code": [37] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [500, 1500, 2500, 3500, 4500],
            "buy_cumulative_mw": [5500, 4500, 3500, 2500, 1500],
        }
    )

    shift = calculate_offer_stack_period_shift(pd.concat([prior, current], ignore_index=True), "2026-06-01", "2026-06-02")

    assert shift.iloc[0]["delivery_period"] == "Evening peak"
    assert shift.iloc[0]["supply_tightening_mw"] == 500
    assert shift.iloc[0]["demand_strength_mw"] == 500
    assert shift.iloc[0]["net_tightening_pressure_mw"] == 1000
    assert shift.iloc[0]["pressure_regime"] == "Tighter"


def test_calculate_tokyo_kansai_stack_tightness_spread_uses_area_depth_when_available():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 10,
            "time_code": [37] * 10,
            "area_group": ["Tokyo"] * 5 + ["Kansai"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20] * 2,
            "sell_cumulative_mw": [1000, 2000, 3000, 3600, 4200] + [1000, 2000, 3000, 5000, 7000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2400, 1800] + [5000, 6000, 3000, 1000, -1000],
        }
    )

    spread = calculate_tokyo_kansai_stack_tightness_spread(stack, price_band=5)

    assert spread.iloc[0]["tokyo_tightest_depth_mw"] == 1200
    assert spread.iloc[0]["kansai_tightest_depth_mw"] == 4000
    assert spread.iloc[0]["tightness_spread_mw"] == -2800
    assert spread.iloc[0]["tighter_area"] == "Tokyo"


def test_build_offer_stack_signal_payload_adds_stack_signal_fields():
    stack = pd.DataFrame(
        {
            "delivery_date": ["2026-06-02"] * 5,
            "time_code": [37] * 5,
            "area_group": ["System Price"] * 5,
            "bid_price_jpy_kwh": [0, 5, 10, 15, 20],
            "sell_cumulative_mw": [1000, 2000, 3000, 4000, 5000],
            "buy_cumulative_mw": [5000, 4000, 3000, 2000, 1000],
        }
    )

    payload = build_offer_stack_signal_payload(stack, shocks_mw=(-1000, 1000), price_band=5)

    assert payload.iloc[0]["stack_tightest_depth_mw"] == 2000
    assert payload.iloc[0]["stack_price_impact_up_1000mw_jpy_kwh"] == 5
    assert payload.iloc[0]["stack_price_impact_down_1000mw_jpy_kwh"] == -5
    assert payload.iloc[0]["stack_up_down_asymmetry_jpy_kwh"] == 0
