import pandas as pd

from src.data_freshness import build_manifest, dataset_record, freshness_status, summarize_manifest


NOW = pd.Timestamp("2026-07-01 00:00:00", tz="UTC")


def test_freshness_status_uses_current_delayed_stale_boundaries():
    assert freshness_status("2026-06-30", NOW, stale_after_days=2) == "current"
    assert freshness_status("2026-06-27", NOW, stale_after_days=2) == "delayed"
    assert freshness_status("2026-06-20", NOW, stale_after_days=2) == "stale"
    assert freshness_status(None, NOW, stale_after_days=2) == "unavailable"


def test_dataset_record_reports_coverage_and_row_count():
    frame = pd.DataFrame({"date": ["2026-06-28", "2026-06-30"], "value": [1, 2]})

    record = dataset_record(
        dataset_id="weather",
        label="Tokyo/Kansai weather",
        source="Open-Meteo",
        frame=frame,
        observation_column="date",
        fetched_at=NOW,
        stale_after_days=3,
        artifact="weather_temperatures.csv",
    )

    assert record["row_count"] == 2
    assert record["observation_start"] == "2026-06-28"
    assert record["observation_end"] == "2026-06-30"
    assert record["status"] == "current"


def test_manifest_is_partial_when_collector_warning_preserves_other_data():
    records = [
        {
            "dataset_id": "weather",
            "label": "Weather",
            "source": "Open-Meteo",
            "artifact": "weather_temperatures.csv",
            "row_count": 2,
            "observation_start": "2026-06-28",
            "observation_end": "2026-06-30",
            "fetched_at": NOW.isoformat(),
            "stale_after_days": 3,
            "status": "current",
        }
    ]

    manifest = build_manifest(records, generated_at=NOW, warnings=["JEPX unavailable"])
    summary = summarize_manifest(manifest)

    assert manifest["overall_status"] == "partial"
    assert summary["overall_status"] == "partial"
    assert summary["dataset_count"] == 1
    assert summary["latest_observation"] == "2026-06-30"
