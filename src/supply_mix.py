from __future__ import annotations

import pandas as pd


GENERATION_MIX_COLUMNS = [
    "month",
    "area",
    "generation_type",
    "generation_gwh",
    "source",
    "source_note",
]
GENERATION_MIX_REQUIRED = {"month", "area", "generation_type", "generation_gwh"}

GENERATION_ORDER = ["Gas", "Coal", "Nuclear", "Solar", "Hydro", "Wind", "Biomass", "Oil", "Other"]


def normalize_generation_mix(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    missing = GENERATION_MIX_REQUIRED.difference(out.columns)
    if missing:
        raise ValueError(f"Missing required generation mix columns: {', '.join(sorted(missing))}")
    if out.empty:
        raise ValueError("Generation mix dataset is empty.")

    out["month"] = pd.to_datetime(out["month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    out["area"] = out["area"].astype(str).str.strip().str.title()
    out["generation_type"] = out["generation_type"].astype(str).str.strip().str.title()
    out["generation_gwh"] = pd.to_numeric(out["generation_gwh"], errors="coerce")
    if out["month"].isna().any():
        raise ValueError("Generation mix data contains invalid month values.")
    if out["area"].eq("").any():
        raise ValueError("Generation mix data contains blank area values.")
    if out["generation_type"].eq("").any():
        raise ValueError("Generation mix data contains blank generation_type values.")
    if out["generation_gwh"].isna().any():
        raise ValueError("Generation mix data contains non-numeric or blank generation_gwh values.")
    if (out["generation_gwh"] < 0).any():
        raise ValueError("Generation mix data contains negative generation_gwh values.")

    for col, default in {
        "source": "uploaded_generation_mix",
        "source_note": "User-uploaded generation mix; verify regional boundary, gross/net basis, and fuel taxonomy.",
    }.items():
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default).astype(str)

    out = out[GENERATION_MIX_COLUMNS]
    return out.sort_values(["area", "month", "generation_type"]).reset_index(drop=True)


def add_generation_share(df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_generation_mix(df)
    totals = out.groupby(["month", "area"])["generation_gwh"].transform("sum")
    out["share_pct"] = (out["generation_gwh"] / totals * 100).where(totals > 0)
    out["generation_type"] = pd.Categorical(out["generation_type"], categories=GENERATION_ORDER, ordered=True)
    return out.sort_values(["area", "month", "generation_type"]).reset_index(drop=True)


def latest_generation_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    mix = add_generation_share(df)
    latest_month = mix.groupby("area")["month"].transform("max")
    latest = mix[mix["month"].eq(latest_month)].copy()
    return latest.sort_values(["area", "share_pct"], ascending=[True, False]).reset_index(drop=True)


def thermal_share_summary(df: pd.DataFrame) -> pd.DataFrame:
    mix = add_generation_share(df)
    mix["thermal_bucket"] = mix["generation_type"].astype(str).isin(["Gas", "Coal", "Oil"])
    summary = mix.groupby(["month", "area", "thermal_bucket"], as_index=False)["generation_gwh"].sum()
    total = summary.groupby(["month", "area"])["generation_gwh"].transform("sum")
    summary["share_pct"] = (summary["generation_gwh"] / total * 100).where(total > 0)
    summary["bucket"] = summary["thermal_bucket"].map({True: "Thermal", False: "Non-thermal"})
    return summary[["month", "area", "bucket", "generation_gwh", "share_pct"]]


def residual_thermal_summary(df: pd.DataFrame) -> pd.DataFrame:
    mix = add_generation_share(df)
    grouped = mix.pivot_table(
        index=["month", "area"],
        columns="generation_type",
        values="generation_gwh",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for col in GENERATION_ORDER:
        if col not in grouped.columns:
            grouped[col] = 0.0
    grouped["thermal_gwh"] = grouped[["Gas", "Coal", "Oil"]].sum(axis=1)
    grouped["clean_supply_gwh"] = grouped[["Nuclear", "Solar", "Hydro", "Wind", "Biomass"]].sum(axis=1)
    grouped["other_gwh"] = grouped["Other"]
    grouped["total_generation_gwh"] = grouped[["thermal_gwh", "clean_supply_gwh", "other_gwh"]].sum(axis=1)
    grouped["residual_thermal_share_pct"] = (
        grouped["thermal_gwh"] / grouped["total_generation_gwh"] * 100
    ).where(grouped["total_generation_gwh"] > 0)
    return grouped[
        [
            "month",
            "area",
            "thermal_gwh",
            "clean_supply_gwh",
            "other_gwh",
            "total_generation_gwh",
            "residual_thermal_share_pct",
        ]
    ].sort_values(["area", "month"]).reset_index(drop=True)


def source_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "JapanesePower.org regional half-hourly files",
                "coverage": "Tokyo/Kansai half-hourly demand and generation mix from 2024 onward",
                "use": "Best free lightweight source for dashboard aggregates: monthly mix, thermal dependency, solar shape, and curtailment watch.",
                "registration": "No API registration required for public CSV files; use processed monthly/daily outputs in the app.",
                "url": "https://japanesepower.org/downloadJapanesePowerMarketData.html",
            },
            {
                "source": "TEPCO Power Grid area download",
                "coverage": "Tokyo area demand/generation public 30-min files",
                "use": "Good for Tokyo area total generation and solar/wind public operational data; not full coal/gas split.",
                "registration": "No API registration found for public download.",
                "url": "https://www4.tepco.co.jp/forecast/html/area-download-j.html",
            },
            {
                "source": "METI Electricity Survey Statistics",
                "coverage": "Monthly Japan electricity statistics and fuel-type thermal tables",
                "use": "Useful official fuel-type reference; regional mapping may require workbook parsing and taxonomy checks.",
                "registration": "No API registration required for public workbooks.",
                "url": "https://www.enecho.meti.go.jp/statistics/electric_power/ep002/results_archive.html",
            },
            {
                "source": "IEA Monthly Electricity Statistics",
                "coverage": "Country-level monthly generation by source",
                "use": "Good national benchmark for coal/gas/nuclear/solar shares; not Tokyo/Kansai regional.",
                "registration": "Free download may require account/session depending on access route.",
                "url": "https://www.iea.org/data-and-statistics/data-tools/monthly-electricity-statistics",
            },
            {
                "source": "Ember monthly electricity data",
                "coverage": "Country-level monthly electricity generation by source",
                "use": "Good national benchmark and clean CSV structure; not Tokyo/Kansai regional.",
                "registration": "No API key needed for public CSV downloads.",
                "url": "https://ember-energy.org/data/monthly-electricity-data",
            },
        ]
    )
