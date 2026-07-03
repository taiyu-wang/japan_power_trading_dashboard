import pandas as pd
import pytest

from src.supply_mix import add_generation_share, normalize_generation_mix, residual_thermal_summary, thermal_share_summary
from src.supply_mix_pipeline import (
    aggregate_daily_supply_shape,
    aggregate_monthly_generation_mix,
    aggregate_residual_thermal,
    build_processed_supply_mix_artifacts,
    enrich_half_hourly_supply,
    normalize_regional_half_hourly_supply,
)


def test_generation_mix_share_sums_to_100_by_area_month():
    df = pd.DataFrame(
        {
            "month": ["2026-01", "2026-01", "2026-01", "2026-01"],
            "area": ["Tokyo", "Tokyo", "Kansai", "Kansai"],
            "generation_type": ["Gas", "Solar", "Nuclear", "Coal"],
            "generation_gwh": [80, 20, 60, 40],
        }
    )

    out = add_generation_share(df)
    totals = out.groupby(["month", "area"])["share_pct"].sum()

    assert totals.round(6).tolist() == [100.0, 100.0]


def test_generation_mix_rejects_negative_generation():
    df = pd.DataFrame(
        {
            "month": ["2026-01"],
            "area": ["Tokyo"],
            "generation_type": ["Gas"],
            "generation_gwh": [-1],
        }
    )

    with pytest.raises(ValueError, match="negative"):
        normalize_generation_mix(df)


def test_thermal_share_summary_uses_gas_coal_oil_bucket():
    df = pd.DataFrame(
        {
            "month": ["2026-01"] * 4,
            "area": ["Tokyo"] * 4,
            "generation_type": ["Gas", "Coal", "Solar", "Nuclear"],
            "generation_gwh": [40, 20, 25, 15],
        }
    )

    summary = thermal_share_summary(df)
    thermal = summary[summary["bucket"] == "Thermal"].iloc[0]

    assert thermal["generation_gwh"] == 60
    assert thermal["share_pct"] == 60


def test_half_hourly_supply_aggregates_generation_to_monthly_gwh():
    raw = pd.DataFrame(
        {
            "Datetime": ["2026-04-01 00:00:00", "2026-04-01 00:30:00"],
            "Date": ["2026-04-01", "2026-04-01"],
            "PeriodID(1 to 48)": [1, 2],
            "Area Demand (MW)": [1000, 1200],
            "Nuclear": [100, 100],
            "Thermal (LNG)": [300, 400],
            "Thermal (Coal)": [200, 200],
            "Thermal (Oil)": [10, 10],
            "Thermal (Other)": [20, 20],
            "Hydroelectric": [50, 50],
            "Geothermal": [5, 5],
            "Biomass": [20, 20],
            "Solar PV Output": [0, 10],
            "Solar PV Curtailment": [0, 2],
            "Wind Power Output": [5, 5],
            "Wind Power Curtailment": [0, 1],
            "Pumped Storage": [-30, -20],
            "Battery Storage": [0, 0],
            "Interconnected Lines": [100, 100],
            "Others": [5, 5],
            "Total": [1000, 1200],
        }
    )

    normalized = normalize_regional_half_hourly_supply(raw, "Tokyo")
    monthly = aggregate_monthly_generation_mix(normalized)

    gas = monthly[monthly["generation_type"].eq("Gas")].iloc[0]
    coal = monthly[monthly["generation_type"].eq("Coal")].iloc[0]
    solar = monthly[monthly["generation_type"].eq("Solar")].iloc[0]

    assert gas["generation_gwh"] == 0.35
    assert coal["generation_gwh"] == 0.2
    assert solar["generation_gwh"] == 0.005
    assert gas["source"] == "JapanesePower.org regional half-hourly supply mix"


def test_daily_supply_shape_returns_trader_metrics():
    rows = []
    for period in range(1, 49):
        rows.append(
            {
                "Datetime": f"2026-04-01 {((period - 1) // 2):02d}:{'30' if period % 2 == 0 else '00'}:00",
                "Date": "2026-04-01",
                "PeriodID(1 to 48)": period,
                "Area Demand (MW)": 1000 + period,
                "Nuclear": 100,
                "Thermal (LNG)": 300 + period,
                "Thermal (Coal)": 200,
                "Thermal (Oil)": 10,
                "Thermal (Other)": 20,
                "Hydroelectric": 50,
                "Geothermal": 5,
                "Biomass": 20,
                "Solar PV Output": 300 if 21 <= period <= 28 else 0,
                "Solar PV Curtailment": 10 if 21 <= period <= 28 else 0,
                "Wind Power Output": 5,
                "Wind Power Curtailment": 1,
                "Pumped Storage": 0,
                "Battery Storage": 0,
                "Interconnected Lines": 0,
                "Others": 5,
                "Total": 1000 + period,
            }
        )

    normalized = normalize_regional_half_hourly_supply(pd.DataFrame(rows), "Kansai")
    shape = aggregate_daily_supply_shape(normalized)

    assert shape.iloc[0]["area"] == "Kansai"
    assert shape.iloc[0]["solar_midday_avg_mw"] == 300
    assert shape.iloc[0]["renewable_curtailment_mwh"] == 64
    assert shape.iloc[0]["residual_thermal_peak_mw"] > 0


def _half_hourly_supply_fixture() -> pd.DataFrame:
    frames = []
    for area in ["Tokyo", "Kansai"]:
        rows = []
        for date in ["2026-03-31", "2026-04-01"]:
            for period in range(1, 49):
                rows.append(
                    {
                        "Datetime": f"{date} {((period - 1) // 2):02d}:{'30' if period % 2 == 0 else '00'}:00",
                        "Date": date,
                        "PeriodID(1 to 48)": period,
                        "Area Demand (MW)": 1000 + period,
                        "Nuclear": 100,
                        "Thermal (LNG)": 300 + period,
                        "Thermal (Coal)": 200,
                        "Thermal (Oil)": -5 if period < 10 else 10,
                        "Thermal (Other)": 20,
                        "Hydroelectric": 50,
                        "Geothermal": 5,
                        "Biomass": 20,
                        "Solar PV Output": 300 if 21 <= period <= 28 else 0,
                        "Solar PV Curtailment": 10 if 21 <= period <= 28 else 0,
                        "Wind Power Output": 5,
                        "Wind Power Curtailment": 1,
                        "Pumped Storage": -30,
                        "Battery Storage": -2 if period % 2 else 2,
                        "Interconnected Lines": 100,
                        "Others": 5,
                        "Total": 1000 + period,
                    }
                )
        frames.append(normalize_regional_half_hourly_supply(pd.DataFrame(rows), area))
    return pd.concat(frames, ignore_index=True)


def test_aggregates_on_enriched_frame_match_standalone_results():
    raw = _half_hourly_supply_fixture()
    enriched = enrich_half_hourly_supply(raw)

    pd.testing.assert_frame_equal(aggregate_monthly_generation_mix(enriched), aggregate_monthly_generation_mix(raw))
    pd.testing.assert_frame_equal(aggregate_daily_supply_shape(enriched), aggregate_daily_supply_shape(raw))
    pd.testing.assert_frame_equal(aggregate_residual_thermal(enriched), aggregate_residual_thermal(raw))


def test_build_processed_supply_mix_artifacts_matches_individual_aggregates():
    raw = _half_hourly_supply_fixture()

    monthly, daily_shape, residual = build_processed_supply_mix_artifacts(raw)

    pd.testing.assert_frame_equal(monthly, aggregate_monthly_generation_mix(raw))
    pd.testing.assert_frame_equal(daily_shape, aggregate_daily_supply_shape(raw))
    pd.testing.assert_frame_equal(residual, aggregate_residual_thermal(raw))


def test_aggregate_residual_thermal_reports_monthly_share():
    raw = _half_hourly_supply_fixture()

    residual = aggregate_residual_thermal(raw)

    assert set(residual["month"]) == {pd.Timestamp("2026-03-01"), pd.Timestamp("2026-04-01")}
    assert set(residual["area"]) == {"Tokyo", "Kansai"}
    row = residual.iloc[0]
    assert row["thermal_gwh"] > 0
    assert row["demand_gwh"] > 0
    assert 0 < row["residual_thermal_share_pct"] < 100


def test_residual_thermal_summary_combines_thermal_and_clean_supply():
    df = pd.DataFrame(
        {
            "month": ["2026-01"] * 5,
            "area": ["Tokyo"] * 5,
            "generation_type": ["Gas", "Coal", "Solar", "Nuclear", "Hydro"],
            "generation_gwh": [40, 20, 25, 15, 10],
        }
    )

    residual = residual_thermal_summary(df)
    row = residual.iloc[0]

    assert row["thermal_gwh"] == 60
    assert row["clean_supply_gwh"] == 50
    assert round(row["residual_thermal_share_pct"], 1) == 54.5
