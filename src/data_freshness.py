from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


FRESHNESS_STATES = {"current", "delayed", "stale", "partial", "unavailable"}


def _timestamp(value) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def freshness_status(observation_date, now, stale_after_days: int) -> str:
    observed = _timestamp(observation_date)
    current = _timestamp(now)
    if observed is None or current is None:
        return "unavailable"
    age_days = max(0, (current.date() - observed.date()).days)
    if age_days <= stale_after_days:
        return "current"
    if age_days <= stale_after_days * 2:
        return "delayed"
    return "stale"


def dataset_record(
    *,
    dataset_id: str,
    label: str,
    source: str,
    frame: pd.DataFrame,
    observation_column: str,
    fetched_at,
    stale_after_days: int,
    artifact: str,
) -> dict:
    if observation_column not in frame.columns:
        raise ValueError(f"{dataset_id} is missing observation column: {observation_column}")
    observations = pd.to_datetime(frame[observation_column], errors="coerce", utc=True).dropna()
    observation_start = observations.min() if not observations.empty else None
    observation_end = observations.max() if not observations.empty else None
    fetched = _timestamp(fetched_at)
    return {
        "dataset_id": dataset_id,
        "label": label,
        "source": source,
        "artifact": artifact,
        "row_count": int(len(frame)),
        "observation_start": observation_start.date().isoformat() if observation_start is not None else None,
        "observation_end": observation_end.date().isoformat() if observation_end is not None else None,
        "fetched_at": fetched.isoformat() if fetched is not None else None,
        "stale_after_days": int(stale_after_days),
        "status": freshness_status(observation_end, fetched, stale_after_days),
    }


def _overall_status(records: Iterable[dict], warnings: list[str]) -> str:
    statuses = [str(record.get("status", "unavailable")) for record in records]
    if not statuses or all(status == "unavailable" for status in statuses):
        return "unavailable"
    if "stale" in statuses:
        return "stale"
    if warnings or "unavailable" in statuses or "partial" in statuses:
        return "partial"
    if "delayed" in statuses:
        return "delayed"
    return "current"


def build_manifest(records: Iterable[dict], generated_at, warnings: Iterable[str] = ()) -> dict:
    record_list = [dict(record) for record in records]
    warning_list = [str(warning) for warning in warnings if str(warning).strip()]
    generated = _timestamp(generated_at)
    return {
        "version": 1,
        "generated_at": generated.isoformat() if generated is not None else None,
        "overall_status": _overall_status(record_list, warning_list),
        "warnings": warning_list,
        "datasets": record_list,
    }


def summarize_manifest(manifest: dict) -> dict:
    records = list(manifest.get("datasets", []))
    observation_dates = [
        parsed
        for parsed in (_timestamp(record.get("observation_end")) for record in records)
        if parsed is not None
    ]
    latest = max(observation_dates).date().isoformat() if observation_dates else None
    return {
        "overall_status": manifest.get("overall_status", "unavailable"),
        "dataset_count": len(records),
        "latest_observation": latest,
        "generated_at": manifest.get("generated_at"),
        "warning_count": len(manifest.get("warnings", [])),
    }
