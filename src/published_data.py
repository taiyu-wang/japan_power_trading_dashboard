from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from .config import DATA_MANIFEST_PATH, PUBLIC_DATA_BASE_URL
from .data_freshness import build_manifest, freshness_status


def published_artifact_url(filename: str, base_url: str = PUBLIC_DATA_BASE_URL) -> str:
    return f"{base_url.rstrip('/')}/{filename.lstrip('/')}"


@st.cache_data(ttl=900, show_spinner=False)
def load_published_csv(
    filename: str,
    *,
    parse_dates: tuple[str, ...] = (),
    base_url: str = PUBLIC_DATA_BASE_URL,
    timeout: int = 8,
) -> pd.DataFrame:
    response = requests.get(published_artifact_url(filename, base_url), timeout=timeout)
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError(f"Published artifact is empty: {filename}")
    frame = pd.read_csv(StringIO(response.text))
    for column in parse_dates:
        if column not in frame.columns:
            raise ValueError(f"Published artifact {filename} is missing date column: {column}")
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _unavailable_manifest(warning: str) -> dict:
    return build_manifest([], pd.Timestamp.now(tz="UTC"), warnings=[warning])


def _read_local_manifest(path: str | Path) -> dict | None:
    local_path = Path(path)
    if not local_path.exists():
        return None
    try:
        manifest = json.loads(local_path.read_text())
        return manifest if isinstance(manifest, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _refresh_records(records: list[dict], now) -> list[dict]:
    refreshed = []
    for item in records:
        record = dict(item)
        record["status"] = freshness_status(
            record.get("observation_end"),
            now,
            int(record.get("stale_after_days", 1)),
        )
        refreshed.append(record)
    return refreshed


def _merge_manifests(remote: dict, local: dict | None) -> dict:
    now = pd.Timestamp.now(tz="UTC")
    records = {
        record["dataset_id"]: record
        for record in _refresh_records(list((local or {}).get("datasets", [])), now)
        if record.get("dataset_id")
    }
    records.update(
        {
            record["dataset_id"]: record
            for record in _refresh_records(list(remote.get("datasets", [])), now)
            if record.get("dataset_id")
        }
    )
    return build_manifest(
        [records[key] for key in sorted(records)],
        generated_at=remote.get("generated_at") or now,
        warnings=remote.get("warnings", []),
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_runtime_manifest(
    *,
    local_path: str | Path = DATA_MANIFEST_PATH,
    base_url: str = PUBLIC_DATA_BASE_URL,
    timeout: int = 8,
) -> tuple[dict, str]:
    try:
        response = requests.get(published_artifact_url("manifest.json", base_url), timeout=timeout)
        response.raise_for_status()
        manifest = response.json()
        if not isinstance(manifest, dict) or "datasets" not in manifest:
            raise ValueError("Published manifest has an invalid schema.")
        local = _read_local_manifest(local_path)
        merged = _merge_manifests(manifest, local)
        source = "scheduled public + bundled manifest" if local and local.get("datasets") else "scheduled public manifest"
        return merged, source
    except Exception as exc:
        manifest = _read_local_manifest(local_path)
        if manifest is not None:
            return _merge_manifests(manifest, None), "bundled manifest"
        return _unavailable_manifest(f"Freshness manifest unavailable: {type(exc).__name__}."), "unavailable"
