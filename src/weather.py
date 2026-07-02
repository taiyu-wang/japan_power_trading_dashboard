from __future__ import annotations

import pandas as pd
import requests

from .config import WEATHER_LOCATIONS


WEATHER_REQUIRED_COLUMNS = {"date", "region", "temperature_mean_c"}
WEATHER_COLUMNS = [
    "date",
    "market",
    "region",
    "station",
    "temperature_mean_c",
    "temperature_max_c",
    "temperature_min_c",
    "cooling_degree_day",
    "heating_degree_day",
    "source",
    "source_note",
]


def calculate_degree_days(series: pd.Series, cooling_base_c: float = 22.0, heating_base_c: float = 18.0) -> pd.DataFrame:
    temp = pd.to_numeric(series, errors="coerce")
    return pd.DataFrame(
        {
            "cooling_degree_day": (temp - cooling_base_c).clip(lower=0),
            "heating_degree_day": (heating_base_c - temp).clip(lower=0),
        }
    )


def normalize_weather_data(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    missing = WEATHER_REQUIRED_COLUMNS.difference(out.columns)
    if missing:
        raise ValueError(f"Missing required weather columns: {', '.join(sorted(missing))}")
    if out.empty:
        return pd.DataFrame(columns=WEATHER_COLUMNS)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
    out["region"] = out["region"].astype(str).str.strip().str.title()
    out["temperature_mean_c"] = pd.to_numeric(out["temperature_mean_c"], errors="coerce")
    for col in ["temperature_max_c", "temperature_min_c"]:
        if col not in out.columns:
            out[col] = out["temperature_mean_c"]
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out["date"].isna().any():
        raise ValueError("Weather data contains invalid dates.")
    if out["region"].eq("").any():
        raise ValueError("Weather data contains blank regions.")
    if out["temperature_mean_c"].isna().any():
        raise ValueError("Weather data contains non-numeric or blank temperatures.")
    if "market" not in out.columns:
        out["market"] = out["region"].str.upper().map({"TOKYO": "TOKYO_TEMP", "KANSAI": "KANSAI_TEMP"}).fillna(out["region"].str.upper() + "_TEMP")
    if "station" not in out.columns:
        out["station"] = out["region"]
    for col, default in {
        "source": "uploaded_weather",
        "source_note": "User-provided weather data; verify source station, units, and timestamp basis.",
    }.items():
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default).astype(str)
    degree_days = calculate_degree_days(out["temperature_mean_c"])
    out["cooling_degree_day"] = pd.to_numeric(out.get("cooling_degree_day", degree_days["cooling_degree_day"]), errors="coerce").fillna(degree_days["cooling_degree_day"])
    out["heating_degree_day"] = pd.to_numeric(out.get("heating_degree_day", degree_days["heating_degree_day"]), errors="coerce").fillna(degree_days["heating_degree_day"])
    return (
        out[WEATHER_COLUMNS]
        .sort_values(["region", "date"])
        .drop_duplicates(["date", "region"], keep="last")
        .reset_index(drop=True)
    )


def fetch_open_meteo_daily_temperatures(start_date, end_date, timeout: int = 8) -> pd.DataFrame:
    rows = []
    for code, meta in WEATHER_LOCATIONS.items():
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": meta["latitude"],
                "longitude": meta["longitude"],
                "start_date": pd.Timestamp(start_date).date().isoformat(),
                "end_date": pd.Timestamp(end_date).date().isoformat(),
                "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min",
                "timezone": "Asia/Tokyo",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        daily = payload.get("daily", {})
        region = "Kansai" if code == "KANSAI" else "Tokyo"
        rows.append(
            pd.DataFrame(
                {
                    "date": daily.get("time", []),
                    "market": f"{code}_TEMP",
                    "region": region,
                    "station": meta["label"],
                    "temperature_mean_c": daily.get("temperature_2m_mean", []),
                    "temperature_max_c": daily.get("temperature_2m_max", []),
                    "temperature_min_c": daily.get("temperature_2m_min", []),
                    "source": "open_meteo_archive",
                    "source_note": "Open-Meteo Historical Weather API daily temperature; verify station/grid basis for production use.",
                }
            )
        )
    if not rows:
        return pd.DataFrame(columns=WEATHER_COLUMNS)
    combined = pd.concat(rows, ignore_index=True)
    combined["temperature_mean_c"] = pd.to_numeric(combined["temperature_mean_c"], errors="coerce")
    combined = combined.dropna(subset=["date", "temperature_mean_c"]).copy()
    for column in ["temperature_max_c", "temperature_min_c"]:
        combined[column] = pd.to_numeric(combined[column], errors="coerce").fillna(combined["temperature_mean_c"])
    return normalize_weather_data(combined)


def weather_power_join(weather: pd.DataFrame, power: pd.DataFrame) -> pd.DataFrame:
    if weather.empty or power.empty:
        return pd.DataFrame(columns=["date", "region", "power_market", "price", "temperature_mean_c", "cooling_degree_day", "heating_degree_day"])
    mapping = {"Tokyo": "JEPX_TOKYO", "Kansai": "JEPX_KANSAI"}
    weather_keyed = weather.copy()
    weather_keyed["power_market"] = weather_keyed["region"].map(mapping)
    power_keyed = power[power["market"].isin(mapping.values())][["date", "market", "price"]].rename(columns={"market": "power_market"})
    return weather_keyed.merge(power_keyed, on=["date", "power_market"], how="inner")


def weather_spread(weather: pd.DataFrame) -> pd.DataFrame:
    if weather.empty:
        return pd.DataFrame(columns=["date", "market", "value"])
    wide = weather.pivot_table(index="date", columns="region", values="temperature_mean_c", aggfunc="mean")
    if not {"Tokyo", "Kansai"}.issubset(wide.columns):
        return pd.DataFrame(columns=["date", "market", "value"])
    out = (wide["Tokyo"] - wide["Kansai"]).reset_index(name="value")
    out["market"] = "Tokyo minus Kansai temperature"
    return out


def rolling_weather_beta(joined: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    if joined.empty:
        return pd.DataFrame(columns=["date", "region", "weather_beta"])
    rows = []
    for region, group in joined.sort_values("date").groupby("region"):
        x = group["cooling_degree_day"] + group["heating_degree_day"]
        y = group["price"]
        beta = y.rolling(window).cov(x) / x.rolling(window).var()
        rows.append(pd.DataFrame({"date": group["date"], "region": region, "weather_beta": beta}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "region", "weather_beta"])
