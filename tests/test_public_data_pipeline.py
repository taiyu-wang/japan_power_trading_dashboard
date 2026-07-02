import json

import pandas as pd

from src.public_data_pipeline import (
    PublishedArtifact,
    build_default_collectors,
    collect_jepx_market,
    collect_supply_mix,
    publish_artifacts,
    run_collectors,
    trim_latest_days,
)


NOW = pd.Timestamp("2026-07-01 00:00:00", tz="UTC")


def weather_artifact() -> PublishedArtifact:
    return PublishedArtifact(
        dataset_id="weather",
        label="Tokyo/Kansai weather",
        source="Open-Meteo",
        filename="weather_temperatures.csv",
        observation_column="date",
        stale_after_days=3,
        frame=pd.DataFrame({"date": ["2026-06-30"], "temperature_mean_c": [25.0]}),
    )


def test_publish_artifacts_writes_csv_and_manifest(tmp_path):
    manifest = publish_artifacts([weather_artifact()], tmp_path, fetched_at=NOW)

    assert (tmp_path / "weather_temperatures.csv").exists()
    saved = json.loads((tmp_path / "manifest.json").read_text())
    assert saved == manifest
    assert saved["datasets"][0]["dataset_id"] == "weather"
    assert saved["datasets"][0]["status"] == "current"


def test_run_collectors_keeps_previous_record_when_one_collector_fails(tmp_path):
    previous_news = {
        "dataset_id": "news",
        "label": "Japan power news",
        "source": "Official public feeds",
        "artifact": "power_news.csv",
        "row_count": 1,
        "observation_start": "2026-06-29",
        "observation_end": "2026-06-29",
        "fetched_at": "2026-06-29T00:00:00+00:00",
        "stale_after_days": 2,
        "status": "current",
    }
    (tmp_path / "power_news.csv").write_text("published_at,title\n2026-06-29,Existing item\n")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "generated_at": "2026-06-29T00:00:00+00:00",
                "overall_status": "current",
                "warnings": [],
                "datasets": [previous_news],
            }
        )
    )

    def failed_news():
        raise RuntimeError("feed unavailable")

    manifest = run_collectors(
        {"weather": lambda: [weather_artifact()], "news": failed_news},
        tmp_path,
        now=NOW,
    )

    records = {record["dataset_id"]: record for record in manifest["datasets"]}
    assert set(records) == {"weather", "news"}
    assert (tmp_path / "power_news.csv").exists()
    assert any("news" in warning and "RuntimeError" in warning for warning in manifest["warnings"])
    assert manifest["overall_status"] == "partial"


def test_build_default_collectors_filters_requested_lanes():
    collectors = build_default_collectors(NOW, selected={"weather", "news"})

    assert list(collectors) == ["weather", "news"]


def test_collect_supply_mix_publishes_complete_month_and_latest_complete_day(monkeypatch):
    rows = []
    for area in ["Tokyo", "Kansai"]:
        for date in pd.date_range("2026-06-30", "2026-07-01", freq="D"):
            for period in range(1, 49):
                rows.append(
                    {
                        "datetime": date + pd.Timedelta(minutes=30 * (period - 1)),
                        "date": date,
                        "period_id": period,
                        "area": area,
                        "area_demand_mw": 1000,
                        "nuclear_mw": 100,
                        "gas_mw": 300,
                        "coal_mw": 200,
                        "oil_mw": 10,
                        "thermal_other_mw": 20,
                        "hydro_mw": 50,
                        "geothermal_mw": 5,
                        "biomass_mw": 20,
                        "solar_mw": 50,
                        "solar_curtailment_mw": 0,
                        "wind_mw": 5,
                        "wind_curtailment_mw": 0,
                        "pumped_storage_mw": 0,
                        "battery_storage_mw": 0,
                        "interconnector_mw": 0,
                        "other_mw": 5,
                        "total_mw": 1000,
                    }
                )
    monkeypatch.setattr(
        "src.public_data_pipeline.fetch_tokyo_kansai_half_hourly_supply",
        lambda: pd.DataFrame(rows),
    )

    artifacts = collect_supply_mix(pd.Timestamp("2026-07-02", tz="UTC"))
    by_id = {artifact.dataset_id: artifact for artifact in artifacts}

    assert set(by_id) == {"supply_mix", "supply_mix_daily_shape", "supply_mix_residual_thermal"}
    assert by_id["supply_mix"].frame["month"].max() == pd.Timestamp("2026-06-01")
    assert by_id["supply_mix_daily_shape"].frame["date"].max() == pd.Timestamp("2026-07-01")
    assert by_id["supply_mix_residual_thermal"].frame["month"].max() == pd.Timestamp("2026-06-01")


def test_collect_jepx_market_includes_daily_spot_artifact(monkeypatch):
    half_hourly = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-07-01"]),
            "time_code": [1],
            "system_price_jpy_kwh": [12.0],
            "tokyo_price_jpy_kwh": [14.0],
            "kansai_price_jpy_kwh": [10.0],
        }
    )
    intraday = pd.DataFrame({"delivery_date": pd.to_datetime(["2026-07-01"])})
    baseload = pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-30"])})
    monkeypatch.setattr("src.public_data_pipeline.fetch_jepx_spot_fiscal_year", lambda year: half_hourly.copy())
    monkeypatch.setattr("src.public_data_pipeline.fetch_jepx_intraday_year", lambda year: intraday.copy())
    monkeypatch.setattr("src.public_data_pipeline.fetch_jepx_baseload_year", lambda year: baseload.copy())

    artifacts = collect_jepx_market(NOW)

    spot = next(item for item in artifacts if item.dataset_id == "jepx_spot_daily")
    assert spot.filename == "jepx_spot_daily.csv"
    assert spot.frame.iloc[0]["date"] == pd.Timestamp("2026-07-01")
    assert set(spot.frame["market"]) == {"JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI"}


def test_trim_latest_days_keeps_bounded_delivery_window():
    frame = pd.DataFrame(
        {
            "delivery_date": pd.date_range("2026-06-01", periods=12, freq="D"),
            "value": range(12),
        }
    )

    trimmed = trim_latest_days(frame, "delivery_date", days=7)

    assert trimmed["delivery_date"].min() == pd.Timestamp("2026-06-06")
    assert trimmed["delivery_date"].max() == pd.Timestamp("2026-06-12")
