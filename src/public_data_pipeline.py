from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import (
    JEPX_BASELOAD_PATH,
    JEPX_INTRADAY_PATH,
    JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
    JEPX_OFFER_STACK_DEPTH_PATH,
    NEWS_EVENTS_PATH,
    WEATHER_DATA_PATH,
)
from .data_freshness import build_manifest, dataset_record, freshness_status
from .jepx_market_data import (
    daily_jepx_spot_prices,
    fetch_jepx_baseload_year,
    fetch_jepx_intraday_year,
    fetch_jepx_spot_fiscal_year,
)
from .news import fetch_public_power_news_with_diagnostics, normalize_news_events
from .offer_stack import fetch_latest_month_jepx_offer_stack, generate_offer_stack_processed_artifacts
from .supply_mix_pipeline import (
    aggregate_daily_supply_shape,
    aggregate_monthly_generation_mix,
    aggregate_residual_thermal,
    complete_half_hourly_days,
    fetch_tokyo_kansai_half_hourly_supply,
)
from .weather import fetch_open_meteo_daily_temperatures, normalize_weather_data


@dataclass(frozen=True)
class PublishedArtifact:
    dataset_id: str
    label: str
    source: str
    filename: str
    observation_column: str
    stale_after_days: int
    frame: pd.DataFrame


COLLECTOR_ORDER = ("weather", "news", "jepx_market", "offer_stack", "supply_mix")


def _atomic_csv_write(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json_write(payload: dict, path: Path) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temporary.replace(path)


def _record_for_artifact(artifact: PublishedArtifact, fetched_at) -> dict:
    if artifact.frame.empty:
        raise ValueError(f"{artifact.dataset_id} returned no rows.")
    return dataset_record(
        dataset_id=artifact.dataset_id,
        label=artifact.label,
        source=artifact.source,
        frame=artifact.frame,
        observation_column=artifact.observation_column,
        fetched_at=fetched_at,
        stale_after_days=artifact.stale_after_days,
        artifact=artifact.filename,
    )


def publish_artifacts(
    artifacts: Iterable[PublishedArtifact],
    output_dir: str | Path,
    *,
    fetched_at,
    warnings: Iterable[str] = (),
    retained_records: Iterable[dict] = (),
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = {record["dataset_id"]: dict(record) for record in retained_records}
    for artifact in artifacts:
        record = _record_for_artifact(artifact, fetched_at)
        _atomic_csv_write(artifact.frame, output / artifact.filename)
        records[artifact.dataset_id] = record
    ordered_records = [records[key] for key in sorted(records)]
    manifest = build_manifest(ordered_records, generated_at=fetched_at, warnings=warnings)
    _atomic_json_write(manifest, output / "manifest.json")
    return manifest


def _previous_manifest(output_dir: Path) -> dict:
    path = output_dir / "manifest.json"
    if not path.exists():
        return {"datasets": []}
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {"datasets": []}
    except (OSError, json.JSONDecodeError):
        return {"datasets": []}


def _retained_records(previous: dict, output_dir: Path, replaced_ids: set[str], now) -> list[dict]:
    retained = []
    for prior in previous.get("datasets", []):
        dataset_id = str(prior.get("dataset_id", ""))
        artifact = str(prior.get("artifact", ""))
        if not dataset_id or dataset_id in replaced_ids or not artifact or not (output_dir / artifact).exists():
            continue
        record = dict(prior)
        record["status"] = freshness_status(
            record.get("observation_end"),
            now,
            int(record.get("stale_after_days", 1)),
        )
        retained.append(record)
    return retained


def run_collectors(
    collectors: Mapping[str, Callable[[], list[PublishedArtifact]]],
    output_dir: str | Path,
    *,
    now=None,
) -> dict:
    fetched_at = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    output = Path(output_dir)
    previous = _previous_manifest(output)
    artifacts: list[PublishedArtifact] = []
    warnings: list[str] = []
    for name, collector in collectors.items():
        try:
            collected = list(collector())
            if not collected:
                raise ValueError("collector returned no artifacts")
            artifacts.extend(collected)
        except Exception as exc:
            warnings.append(f"{name} collector failed: {type(exc).__name__}.")
    replaced_ids = {artifact.dataset_id for artifact in artifacts}
    retained = _retained_records(previous, output, replaced_ids, fetched_at)
    manifest = publish_artifacts(
        artifacts,
        output,
        fetched_at=fetched_at,
        warnings=warnings,
        retained_records=retained,
    )
    if not artifacts and not retained:
        raise RuntimeError("No public datasets were published or retained.")
    return manifest


def _as_utc(now) -> pd.Timestamp:
    parsed = pd.Timestamp(now)
    return parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")


def collect_weather(now) -> list[PublishedArtifact]:
    current = _as_utc(now)
    end = current.normalize() - pd.Timedelta(days=5)
    start = end - pd.DateOffset(years=3)
    frame = fetch_open_meteo_daily_temperatures(start.date(), end.date())
    return [
        PublishedArtifact(
            dataset_id="weather",
            label="Tokyo/Kansai weather",
            source="Open-Meteo Historical Weather API",
            filename="weather_temperatures.csv",
            observation_column="date",
            stale_after_days=7,
            frame=frame,
        )
    ]


def collect_news() -> list[PublishedArtifact]:
    frame, _, sources = fetch_public_power_news_with_diagnostics()
    source = f"Public feeds: {', '.join(sources)}" if sources else "Public Japan power feeds"
    return [
        PublishedArtifact(
            dataset_id="news",
            label="Japan power news",
            source=source,
            filename="power_news.csv",
            observation_column="published_at",
            stale_after_days=7,
            frame=frame,
        )
    ]


def collect_jepx_market(now) -> list[PublishedArtifact]:
    year = _as_utc(now).year
    spot_frames = [fetch_jepx_spot_fiscal_year(value) for value in (year - 1, year)]
    spot = pd.concat([frame for frame in spot_frames if not frame.empty], ignore_index=True)
    spot_daily = daily_jepx_spot_prices(spot)
    intraday = fetch_jepx_intraday_year(year)
    baseload_frames = [fetch_jepx_baseload_year(value) for value in (year - 1, year)]
    baseload = pd.concat([frame for frame in baseload_frames if not frame.empty], ignore_index=True)
    return [
        PublishedArtifact(
            dataset_id="jepx_spot_daily",
            label="JEPX day-ahead spot prices",
            source="JEPX public day-ahead spot summary CSV",
            filename="jepx_spot_daily.csv",
            observation_column="date",
            stale_after_days=4,
            frame=spot_daily,
        ),
        PublishedArtifact(
            dataset_id="jepx_intraday",
            label="JEPX intraday",
            source="JEPX public intraday CSV",
            filename="jepx_intraday.csv",
            observation_column="delivery_date",
            stale_after_days=4,
            frame=intraday,
        ),
        PublishedArtifact(
            dataset_id="jepx_baseload",
            label="JEPX baseload",
            source="JEPX public baseload CSV",
            filename="jepx_baseload.csv",
            observation_column="trade_date",
            stale_after_days=180,
            frame=baseload,
        ),
    ]


def collect_offer_stack() -> list[PublishedArtifact]:
    raw = fetch_latest_month_jepx_offer_stack(days=7)
    depth, compact = generate_offer_stack_processed_artifacts(raw)
    return [
        PublishedArtifact(
            dataset_id="jepx_offer_stack_depth",
            label="JEPX offer-stack depth",
            source="JEPX processed aggregate bidding curves",
            filename="jepx_offer_stack_depth.csv",
            observation_column="delivery_date",
            stale_after_days=4,
            frame=depth,
        ),
        PublishedArtifact(
            dataset_id="jepx_offer_stack_curves",
            label="JEPX compact offer-stack curves",
            source="JEPX processed aggregate bidding curves",
            filename="jepx_offer_stack_curves.csv",
            observation_column="delivery_date",
            stale_after_days=4,
            frame=compact,
        ),
    ]


def collect_supply_mix(now) -> list[PublishedArtifact]:
    current = _as_utc(now).tz_convert("Asia/Tokyo").tz_localize(None)
    current_month = current.to_period("M").to_timestamp()
    complete_days = complete_half_hourly_days(fetch_tokyo_kansai_half_hourly_supply())
    closed_months = complete_days[complete_days["date"].lt(current_month)].copy()
    monthly = aggregate_monthly_generation_mix(closed_months)
    daily_shape = aggregate_daily_supply_shape(complete_days)
    residual = aggregate_residual_thermal(closed_months)
    return [
        PublishedArtifact(
            dataset_id="supply_mix",
            label="Tokyo/Kansai monthly generation mix",
            source="JapanesePower.org regional half-hourly supply mix",
            filename="supply_mix_monthly.csv",
            observation_column="month",
            stale_after_days=45,
            frame=monthly,
        ),
        PublishedArtifact(
            dataset_id="supply_mix_daily_shape",
            label="Tokyo/Kansai daily supply shape",
            source="JapanesePower.org regional half-hourly supply mix",
            filename="supply_mix_daily_shape.csv",
            observation_column="date",
            stale_after_days=4,
            frame=daily_shape,
        ),
        PublishedArtifact(
            dataset_id="supply_mix_residual_thermal",
            label="Tokyo/Kansai residual thermal",
            source="JapanesePower.org regional half-hourly supply mix",
            filename="supply_mix_residual_thermal.csv",
            observation_column="month",
            stale_after_days=45,
            frame=residual,
        ),
    ]


def build_default_collectors(now, selected: set[str] | None = None) -> dict[str, Callable[[], list[PublishedArtifact]]]:
    requested = set(COLLECTOR_ORDER if selected is None else selected)
    unknown = requested.difference(COLLECTOR_ORDER)
    if unknown:
        raise ValueError(f"Unknown public-data collectors: {', '.join(sorted(unknown))}")
    factories: dict[str, Callable[[], list[PublishedArtifact]]] = {
        "weather": lambda: collect_weather(now),
        "news": collect_news,
        "jepx_market": lambda: collect_jepx_market(now),
        "offer_stack": collect_offer_stack,
        "supply_mix": lambda: collect_supply_mix(now),
    }
    return {name: factories[name] for name in COLLECTOR_ORDER if name in requested}


def _read_seed_frame(path: Path, parse_dates: tuple[str, ...], normalizer=None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in parse_dates:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return normalizer(frame) if normalizer is not None else frame


def trim_latest_days(frame: pd.DataFrame, date_column: str, days: int) -> pd.DataFrame:
    if frame.empty or date_column not in frame.columns:
        return frame.copy()
    out = frame.copy()
    out[date_column] = pd.to_datetime(out[date_column], errors="coerce")
    latest = out[date_column].max()
    if pd.isna(latest):
        return out.iloc[0:0].copy()
    start = latest.normalize() - pd.Timedelta(days=days - 1)
    return out[out[date_column].between(start, latest)].reset_index(drop=True)


def build_local_seed_artifacts() -> list[PublishedArtifact]:
    specs = [
        (
            WEATHER_DATA_PATH,
            PublishedArtifact,
            dict(
                dataset_id="weather",
                label="Tokyo/Kansai weather",
                source="Bundled weather seed",
                filename="weather_temperatures.csv",
                observation_column="date",
                stale_after_days=7,
            ),
            ("date",),
            normalize_weather_data,
        ),
        (
            NEWS_EVENTS_PATH,
            PublishedArtifact,
            dict(
                dataset_id="news",
                label="Japan power news",
                source="Bundled news seed",
                filename="power_news.csv",
                observation_column="published_at",
                stale_after_days=7,
            ),
            ("published_at",),
            normalize_news_events,
        ),
        (
            JEPX_INTRADAY_PATH,
            PublishedArtifact,
            dict(
                dataset_id="jepx_intraday",
                label="JEPX intraday",
                source="Bundled JEPX intraday seed",
                filename="jepx_intraday.csv",
                observation_column="delivery_date",
                stale_after_days=4,
            ),
            ("delivery_date",),
            None,
        ),
        (
            JEPX_BASELOAD_PATH,
            PublishedArtifact,
            dict(
                dataset_id="jepx_baseload",
                label="JEPX baseload",
                source="Bundled JEPX baseload seed",
                filename="jepx_baseload.csv",
                observation_column="trade_date",
                stale_after_days=180,
            ),
            ("trade_date",),
            None,
        ),
        (
            JEPX_OFFER_STACK_DEPTH_PATH,
            PublishedArtifact,
            dict(
                dataset_id="jepx_offer_stack_depth",
                label="JEPX offer-stack depth",
                source="Bundled JEPX offer-stack seed",
                filename="jepx_offer_stack_depth.csv",
                observation_column="delivery_date",
                stale_after_days=4,
            ),
            ("delivery_date",),
            None,
        ),
        (
            JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
            PublishedArtifact,
            dict(
                dataset_id="jepx_offer_stack_curves",
                label="JEPX compact offer-stack curves",
                source="Bundled JEPX offer-stack seed",
                filename="jepx_offer_stack_curves.csv",
                observation_column="delivery_date",
                stale_after_days=4,
            ),
            ("delivery_date",),
            None,
        ),
    ]
    artifacts = []
    for path, artifact_type, values, parse_dates, normalizer in specs:
        frame = _read_seed_frame(Path(path), parse_dates, normalizer)
        if values["dataset_id"] in {"jepx_offer_stack_depth", "jepx_offer_stack_curves"}:
            frame = trim_latest_days(frame, "delivery_date", days=7)
        if not frame.empty:
            artifacts.append(artifact_type(frame=frame, **values))
    return artifacts


def _parse_selected(value: str) -> set[str] | None:
    if value.strip().lower() == "all":
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish compact public Japan power datasets.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--datasets", default="all", help="all or comma-separated collector lanes")
    parser.add_argument("--seed-local", action="store_true", help="Seed artifacts from bundled local datasets")
    args = parser.parse_args()
    now = pd.Timestamp.now(tz="UTC")
    if args.seed_local:
        manifest = publish_artifacts(build_local_seed_artifacts(), args.output_dir, fetched_at=now)
    else:
        manifest = run_collectors(
            build_default_collectors(now, _parse_selected(args.datasets)),
            args.output_dir,
            now=now,
        )
    print(
        f"Published {len(manifest['datasets'])} datasets; "
        f"status={manifest['overall_status']}; warnings={len(manifest['warnings'])}"
    )


if __name__ == "__main__":
    main()
