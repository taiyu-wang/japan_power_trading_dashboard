import json

import pandas as pd

from src.published_data import (
    load_published_csv,
    load_runtime_manifest,
    published_artifact_url,
)


class FakeResponse:
    def __init__(self, *, text: str = "", payload: dict | None = None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_published_artifact_url_joins_base_and_filename():
    assert (
        published_artifact_url("weather_temperatures.csv", "https://example.test/data/")
        == "https://example.test/data/weather_temperatures.csv"
    )


def test_load_published_csv_parses_requested_dates(monkeypatch):
    def fake_get(url, timeout):
        assert url.endswith("/jepx_intraday.csv")
        assert timeout == 8
        return FakeResponse(text="delivery_date,time_code\n2026-06-30,1\n")

    monkeypatch.setattr("src.published_data.requests.get", fake_get)
    load_published_csv.clear()

    frame = load_published_csv(
        "jepx_intraday.csv",
        parse_dates=("delivery_date",),
        base_url="https://example.test/data",
    )

    assert frame.iloc[0]["delivery_date"] == pd.Timestamp("2026-06-30")


def test_runtime_manifest_falls_back_to_local_json(monkeypatch, tmp_path):
    def failed_get(url, timeout):
        raise OSError("network unavailable")

    local_manifest = {
        "version": 1,
        "overall_status": "stale",
        "generated_at": "2026-06-08T00:00:00+00:00",
        "warnings": [],
        "datasets": [],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(local_manifest))
    monkeypatch.setattr("src.published_data.requests.get", failed_get)
    load_runtime_manifest.clear()

    manifest, source = load_runtime_manifest(
        local_path=path,
        base_url="https://example.test/data",
    )

    assert manifest["generated_at"] == local_manifest["generated_at"]
    assert manifest["datasets"] == []
    assert manifest["overall_status"] == "unavailable"
    assert source == "bundled manifest"


def test_runtime_manifest_merges_remote_records_with_bundled_snapshot(monkeypatch, tmp_path):
    remote_manifest = {
        "version": 1,
        "overall_status": "current",
        "generated_at": "2026-07-01T00:00:00+00:00",
        "warnings": [],
        "datasets": [
            {
                "dataset_id": "weather",
                "label": "Weather",
                "source": "Open-Meteo",
                "artifact": "weather_temperatures.csv",
                "row_count": 2,
                "observation_start": "2026-06-29",
                "observation_end": "2026-06-30",
                "fetched_at": "2026-07-01T00:00:00+00:00",
                "stale_after_days": 3,
                "status": "current",
            }
        ],
    }
    local_manifest = {
        "version": 1,
        "overall_status": "stale",
        "generated_at": "2026-06-08T00:00:00+00:00",
        "warnings": [],
        "datasets": [
            {
                "dataset_id": "historical_prices",
                "label": "Historical prices",
                "source": "Bundled sample",
                "artifact": "sample_historical_prices.csv",
                "row_count": 100,
                "observation_start": "2023-01-01",
                "observation_end": "2026-06-08",
                "fetched_at": "2026-06-08T00:00:00+00:00",
                "stale_after_days": 3,
                "status": "stale",
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(local_manifest))
    monkeypatch.setattr(
        "src.published_data.requests.get",
        lambda url, timeout: FakeResponse(payload=remote_manifest),
    )
    load_runtime_manifest.clear()

    manifest, source = load_runtime_manifest(
        local_path=path,
        base_url="https://example.test/data",
    )

    assert {record["dataset_id"] for record in manifest["datasets"]} == {"historical_prices", "weather"}
    assert manifest["overall_status"] == "stale"
    assert source == "scheduled public + bundled manifest"
