from __future__ import annotations

from pathlib import Path

import pandas as pd


JAPANESE_POWER_BASE_URL = "https://japanesepower.org"
JAPANESE_POWER_AREA_FILES = {
    "Tokyo": "TokyoHalfHourlyData.csv",
    "Kansai": "KansaiHalfHourlyData.csv",
}
JAPANESE_POWER_SOURCE = "JapanesePower.org regional half-hourly supply mix"
JAPANESE_POWER_SOURCE_NOTE = (
    "Free public aggregate half-hourly regional demand/generation mix. "
    "Use processed aggregates for dashboard speed; verify licensing and source lineage before commercial use."
)

SUPPLY_COLUMNS = [
    "datetime",
    "date",
    "period_id",
    "area",
    "area_demand_mw",
    "nuclear_mw",
    "gas_mw",
    "coal_mw",
    "oil_mw",
    "thermal_other_mw",
    "hydro_mw",
    "geothermal_mw",
    "biomass_mw",
    "solar_mw",
    "solar_curtailment_mw",
    "wind_mw",
    "wind_curtailment_mw",
    "pumped_storage_mw",
    "battery_storage_mw",
    "interconnector_mw",
    "other_mw",
    "total_mw",
]

GENERATION_SOURCE_MAP = {
    "Nuclear": "nuclear_mw",
    "Gas": "gas_mw",
    "Coal": "coal_mw",
    "Oil": "oil_mw",
    "Hydro": "hydro_mw",
    "Biomass": "biomass_mw",
    "Solar": "solar_mw",
    "Wind": "wind_mw",
    "Other": ["thermal_other_mw", "geothermal_mw", "battery_storage_mw", "other_mw"],
}

RENAME_COLUMNS = {
    "Datetime": "datetime",
    "Date": "date",
    "PeriodID(1 to 48)": "period_id",
    "Area Demand (MW)": "area_demand_mw",
    "Nuclear": "nuclear_mw",
    "Thermal (LNG)": "gas_mw",
    "Thermal (Coal)": "coal_mw",
    "Thermal (Oil)": "oil_mw",
    "Thermal (Other)": "thermal_other_mw",
    "Hydroelectric": "hydro_mw",
    "Geothermal": "geothermal_mw",
    "Biomass": "biomass_mw",
    "Solar PV Output": "solar_mw",
    "Solar PV Curtailment": "solar_curtailment_mw",
    "Wind Power Output": "wind_mw",
    "Wind Power Curtailment": "wind_curtailment_mw",
    "Pumped Storage": "pumped_storage_mw",
    "Battery Storage": "battery_storage_mw",
    "Interconnected Lines": "interconnector_mw",
    "Others": "other_mw",
    "Total": "total_mw",
}


def source_url_for_area(area: str) -> str:
    file_name = JAPANESE_POWER_AREA_FILES[area]
    return f"{JAPANESE_POWER_BASE_URL}/{file_name}"


def normalize_regional_half_hourly_supply(df: pd.DataFrame, area: str) -> pd.DataFrame:
    out = df.rename(columns=RENAME_COLUMNS).copy()
    missing = sorted(set(SUPPLY_COLUMNS).difference(out.columns).difference({"area"}))
    if missing:
        raise ValueError(f"Regional supply file for {area} is missing columns: {', '.join(missing)}")

    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["period_id"] = pd.to_numeric(out["period_id"], errors="coerce").astype("Int64")
    out["area"] = str(area).strip().title()
    numeric_cols = [col for col in SUPPLY_COLUMNS if col.endswith("_mw") or col == "total_mw"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["datetime", "date", "period_id"])
    out["period_id"] = out["period_id"].astype(int)
    return out[SUPPLY_COLUMNS].sort_values(["area", "datetime"]).reset_index(drop=True)


def fetch_regional_half_hourly_supply(area: str) -> pd.DataFrame:
    if area not in JAPANESE_POWER_AREA_FILES:
        raise ValueError(f"Unsupported area for JapanesePower.org supply mix: {area}")
    return normalize_regional_half_hourly_supply(pd.read_csv(source_url_for_area(area)), area)


def fetch_tokyo_kansai_half_hourly_supply() -> pd.DataFrame:
    frames = [fetch_regional_half_hourly_supply(area) for area in ["Tokyo", "Kansai"]]
    return pd.concat(frames, ignore_index=True)


def _positive_gwh(series: pd.Series) -> pd.Series:
    return series.clip(lower=0) * 0.5 / 1000


def aggregate_monthly_generation_mix(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["month"] = pd.to_datetime(work["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    rows: list[pd.DataFrame] = []
    for generation_type, source_cols in GENERATION_SOURCE_MAP.items():
        cols = source_cols if isinstance(source_cols, list) else [source_cols]
        tmp = work[["month", "area"]].copy()
        tmp["generation_type"] = generation_type
        tmp["generation_gwh"] = sum(_positive_gwh(work[col]) for col in cols)
        rows.append(tmp)
    out = pd.concat(rows, ignore_index=True)
    monthly = out.groupby(["month", "area", "generation_type"], as_index=False)["generation_gwh"].sum()
    monthly["generation_gwh"] = monthly["generation_gwh"].round(3)
    monthly["source"] = JAPANESE_POWER_SOURCE
    monthly["source_note"] = JAPANESE_POWER_SOURCE_NOTE
    return monthly.sort_values(["area", "month", "generation_type"]).reset_index(drop=True)


def aggregate_daily_supply_shape(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    thermal_cols = ["gas_mw", "coal_mw", "oil_mw", "thermal_other_mw"]
    clean_cols = ["nuclear_mw", "hydro_mw", "biomass_mw", "solar_mw", "wind_mw", "geothermal_mw"]
    work["thermal_mw"] = work[thermal_cols].sum(axis=1)
    work["clean_supply_mw"] = work[clean_cols].sum(axis=1)
    work["residual_thermal_mw"] = work["area_demand_mw"] - work["clean_supply_mw"]
    work["renewable_curtailment_mwh"] = (work["solar_curtailment_mw"].clip(lower=0) + work["wind_curtailment_mw"].clip(lower=0)) * 0.5
    midday = work["period_id"].between(21, 28)
    evening = work["period_id"].between(35, 42)

    daily = (
        work.groupby(["date", "area"], as_index=False)
        .agg(
            demand_peak_mw=("area_demand_mw", "max"),
            demand_avg_mw=("area_demand_mw", "mean"),
            thermal_avg_mw=("thermal_mw", "mean"),
            residual_thermal_peak_mw=("residual_thermal_mw", "max"),
            renewable_curtailment_mwh=("renewable_curtailment_mwh", "sum"),
        )
    )
    block = (
        work.assign(
            solar_midday_mw=work["solar_mw"].where(midday),
            demand_midday_mw=work["area_demand_mw"].where(midday),
            thermal_midday_mw=work["thermal_mw"].where(midday),
            thermal_evening_mw=work["thermal_mw"].where(evening),
        )
        .groupby(["date", "area"], as_index=False)
        .agg(
            solar_midday_avg_mw=("solar_midday_mw", "mean"),
            demand_midday_avg_mw=("demand_midday_mw", "mean"),
            thermal_midday_avg_mw=("thermal_midday_mw", "mean"),
            thermal_evening_avg_mw=("thermal_evening_mw", "mean"),
        )
    )
    out = daily.merge(block, on=["date", "area"], how="left")
    out["thermal_ramp_mw"] = out["thermal_evening_avg_mw"] - out["thermal_midday_avg_mw"]
    out["solar_share_midday_pct"] = (
        out["solar_midday_avg_mw"] / out["demand_midday_avg_mw"] * 100
    ).where(out["demand_midday_avg_mw"] > 0)
    out["source"] = JAPANESE_POWER_SOURCE
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].round(3)
    return out.sort_values(["area", "date"]).reset_index(drop=True)


def aggregate_residual_thermal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    thermal_cols = ["gas_mw", "coal_mw", "oil_mw", "thermal_other_mw"]
    clean_cols = ["nuclear_mw", "hydro_mw", "biomass_mw", "solar_mw", "wind_mw", "geothermal_mw"]
    work["month"] = pd.to_datetime(work["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    work["thermal_gwh"] = sum(_positive_gwh(work[col]) for col in thermal_cols)
    work["clean_supply_gwh"] = sum(_positive_gwh(work[col]) for col in clean_cols)
    work["demand_gwh"] = work["area_demand_mw"].clip(lower=0) * 0.5 / 1000
    out = work.groupby(["month", "area"], as_index=False)[["thermal_gwh", "clean_supply_gwh", "demand_gwh"]].sum()
    out["residual_thermal_share_pct"] = (out["thermal_gwh"] / out["demand_gwh"] * 100).where(out["demand_gwh"] > 0)
    out["source"] = JAPANESE_POWER_SOURCE
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].round(3)
    return out.sort_values(["area", "month"]).reset_index(drop=True)


def build_processed_supply_mix_artifacts(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly = aggregate_monthly_generation_mix(raw)
    daily_shape = aggregate_daily_supply_shape(raw)
    residual = aggregate_residual_thermal(raw)
    return monthly, daily_shape, residual


def write_processed_supply_mix_artifacts(
    monthly_path: str | Path,
    daily_shape_path: str | Path,
    residual_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = fetch_tokyo_kansai_half_hourly_supply()
    monthly, daily_shape, residual = build_processed_supply_mix_artifacts(raw)
    for path, data in [(monthly_path, monthly), (daily_shape_path, daily_shape), (residual_path, residual)]:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(output, index=False)
    return monthly, daily_shape, residual


def main() -> None:
    from .config import SUPPLY_MIX_DAILY_SHAPE_PATH, SUPPLY_MIX_MONTHLY_PATH, SUPPLY_MIX_RESIDUAL_THERMAL_PATH

    monthly, daily_shape, residual = write_processed_supply_mix_artifacts(
        SUPPLY_MIX_MONTHLY_PATH,
        SUPPLY_MIX_DAILY_SHAPE_PATH,
        SUPPLY_MIX_RESIDUAL_THERMAL_PATH,
    )
    print(f"Wrote {len(monthly):,} monthly supply mix rows to {SUPPLY_MIX_MONTHLY_PATH}")
    print(f"Wrote {len(daily_shape):,} daily shape rows to {SUPPLY_MIX_DAILY_SHAPE_PATH}")
    print(f"Wrote {len(residual):,} residual thermal rows to {SUPPLY_MIX_RESIDUAL_THERMAL_PATH}")


if __name__ == "__main__":
    main()
