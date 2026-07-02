from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DATA_DIR, FORWARD_CURVES_PATH, HISTORICAL_DATA_PATH, MARKET_MAPPING_PATH, NEWS_EVENTS_PATH, POWER_FUTURES_PATH, SUPPLY_MIX_PATH, WEATHER_DATA_PATH
from .news import sample_power_news


def _mean_reverting_series(n: int, start: float, mean: float, vol: float, speed: float, rng: np.random.Generator) -> np.ndarray:
    values = np.zeros(n)
    values[0] = start
    for i in range(1, n):
        shock = rng.normal(0, vol)
        values[i] = max(0.01, values[i - 1] + speed * (mean - values[i - 1]) + shock)
    return values


def generate_historical_data(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=365 * 3 + 45, freq="D")
    n = len(dates)
    dayofyear = dates.dayofyear.to_numpy()
    seasonal_winter = 1 + 0.18 * np.cos((dayofyear - 20) / 365 * 2 * np.pi)
    seasonal_summer = 1 + 0.13 * np.cos((dayofyear - 220) / 365 * 2 * np.pi)
    fuel_season = np.maximum(seasonal_winter, seasonal_summer)
    weather = generate_weather_data(dates=dates, seed=seed + 101)
    weather_wide = weather.pivot_table(index="date", columns="region", values="temperature_mean_c", aggfunc="mean").reindex(dates).ffill().bfill()
    tokyo_weather_stress = np.maximum(weather_wide["Tokyo"].to_numpy() - 22, 0) + 0.65 * np.maximum(18 - weather_wide["Tokyo"].to_numpy(), 0)
    kansai_weather_stress = np.maximum(weather_wide["Kansai"].to_numpy() - 22, 0) + 0.55 * np.maximum(18 - weather_wide["Kansai"].to_numpy(), 0)

    brent = _mean_reverting_series(n, 82, 78, 1.25, 0.015, rng)
    jcc = brent * 0.92 + rng.normal(0, 1.4, n)
    coal = _mean_reverting_series(n, 170, 145, 3.0, 0.018, rng) * (0.95 + 0.08 * fuel_season)
    cfr_coal = coal + rng.normal(7, 2.0, n)
    jkm = _mean_reverting_series(n, 15, 13.5, 0.42, 0.02, rng) * fuel_season
    des_japan = jkm + rng.normal(0.45, 0.18, n)
    jcc_linked = (jcc * 0.1485 + 0.7) + rng.normal(0, 0.12, n)
    usdjpy = _mean_reverting_series(n, 142, 146, 0.65, 0.01, rng)

    fuel_index = 0.55 * jkm + 0.025 * cfr_coal + 0.04 * jcc
    power_base = 7.5 + 1.05 * fuel_index * fuel_season + 0.11 * (tokyo_weather_stress + kansai_weather_stress) + rng.normal(0, 1.4, n)
    spike_days = rng.choice(n, size=34, replace=False)
    power_base[spike_days] += rng.uniform(12, 45, size=len(spike_days))
    system = np.clip(power_base, 3, None)
    tokyo = system * (1.05 + 0.05 * seasonal_summer) + 0.18 * tokyo_weather_stress + rng.normal(0, 1.7, n)
    kansai = system * (0.94 + 0.03 * seasonal_winter) + 0.15 * kansai_weather_stress + rng.normal(0, 1.4, n)
    intraday = system + rng.normal(0.4, 1.8, n)
    futures = pd.Series(system).rolling(20, min_periods=1).mean().to_numpy() + rng.normal(1.8, 1.1, n)

    specs = [
        ("JKM", "Japan/Korea", "LNG", jkm, "USD", "MMBtu"),
        ("DES_JAPAN_LNG", "Japan", "LNG", des_japan, "USD", "MMBtu"),
        ("JCC", "Japan", "Crude", jcc, "USD", "bbl"),
        ("JCC_LINKED_LNG", "Japan", "LNG", jcc_linked, "USD", "MMBtu"),
        ("NEWCASTLE_COAL", "Australia", "Coal", coal, "USD", "tonne"),
        ("CFR_JAPAN_COAL", "Japan", "Coal", cfr_coal, "USD", "tonne"),
        ("BRENT", "Global", "Crude", brent, "USD", "bbl"),
        ("USDJPY", "Japan", "FX", usdjpy, "JPY", "USD"),
        ("JEPX_SYSTEM", "Japan", "Power", system, "JPY", "kWh"),
        ("JEPX_INTRADAY", "Japan", "Power", intraday, "JPY", "kWh"),
        ("JEPX_TOKYO", "Tokyo", "Power", tokyo, "JPY", "kWh"),
        ("JEPX_KANSAI", "Kansai", "Power", kansai, "JPY", "kWh"),
        ("JAPAN_POWER_FUTURES", "Japan", "Power", futures, "JPY", "kWh"),
    ]
    rows = []
    for market, region, asset_class, values, currency, unit in specs:
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "market": market,
                    "region": region,
                    "asset_class": asset_class,
                    "frequency": "daily",
                    "contract": "spot",
                    "price": np.round(values, 4),
                    "currency": currency,
                    "unit": unit,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def generate_weather_data(dates: pd.DatetimeIndex | None = None, seed: int = 143) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if dates is None:
        dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=365 * 3 + 45, freq="D")
    dayofyear = dates.dayofyear.to_numpy()
    summer_cycle = np.cos((dayofyear - 220) / 365 * 2 * np.pi)
    winter_cycle = np.cos((dayofyear - 20) / 365 * 2 * np.pi)
    location_specs = [
        ("TOKYO_TEMP", "Tokyo", "Tokyo", 16.8, 9.3, 0.0, 1.7),
        ("KANSAI_TEMP", "Kansai", "Osaka", 17.5, 9.8, 0.8, 1.8),
    ]
    rows = []
    for market, region, station, base, amplitude, offset, noise in location_specs:
        mean_temp = base + amplitude * summer_cycle + 0.9 * winter_cycle + offset + rng.normal(0, noise, len(dates))
        max_temp = mean_temp + rng.normal(4.2, 0.9, len(dates))
        min_temp = mean_temp - rng.normal(4.0, 0.8, len(dates))
        cdd = np.maximum(mean_temp - 22.0, 0)
        hdd = np.maximum(18.0 - mean_temp, 0)
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "market": market,
                    "region": region,
                    "station": station,
                    "temperature_mean_c": np.round(mean_temp, 2),
                    "temperature_max_c": np.round(max_temp, 2),
                    "temperature_min_c": np.round(min_temp, 2),
                    "cooling_degree_day": np.round(cdd, 2),
                    "heating_degree_day": np.round(hdd, 2),
                    "source": "synthetic_sample_weather",
                    "source_note": "Synthetic daily temperature shaped around Tokyo/Osaka seasonality; replace with JMA, Open-Meteo, or vendor weather data for production.",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def generate_forward_curves(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    curve_dates = pd.to_datetime([
        pd.Timestamp.today().normalize() - pd.Timedelta(days=60),
        pd.Timestamp.today().normalize() - pd.Timedelta(days=30),
        pd.Timestamp.today().normalize(),
    ])
    contract_months = pd.date_range(pd.Timestamp.today().normalize() + pd.offsets.MonthBegin(1), periods=24, freq="MS")
    markets = {
        "JKM": ("Japan/Korea", "USD", "MMBtu", 13.8, -0.030, 1.1, "seasonal", "financial_forward_proxy", "Synthetic LNG forward proxy. Replace with licensed JKM forward assessments."),
        "DES_JAPAN_LNG": ("Japan", "USD", "MMBtu", 14.2, -0.024, 1.0, "seasonal", "physical_forward_proxy", "Synthetic DES Japan LNG delivered forward proxy."),
        "JCC": ("Japan", "USD", "bbl", 73.0, 0.004, 1.4, "crude", "monthly_customs_proxy", "Synthetic monthly JCC customs-cleared crude proxy derived from Brent-style oil structure; not an exchange-traded future."),
        "JCC_LINKED_LNG": ("Japan", "USD", "MMBtu", 11.3, 0.004, 0.25, "lng_oil_linked", "physical_contract_proxy", "Synthetic 11-13.5% oil-linked LNG proxy. Replace with contract-specific slope and constant."),
        "NEWCASTLE_COAL": ("Australia", "USD", "tonne", 142.0, 0.010, 8.0, "light_seasonal", "financial_forward_proxy", "Synthetic Newcastle coal forward proxy."),
        "CFR_JAPAN_COAL": ("Japan", "USD", "tonne", 151.0, 0.009, 8.5, "light_seasonal", "physical_forward_proxy", "Synthetic CFR Japan coal delivered forward proxy."),
        "BRENT": ("Global", "USD", "bbl", 79.0, 0.002, 1.8, "crude", "financial_futures", "Synthetic Brent futures curve proxy. Production source should use ICE Brent futures settlements."),
        "JAPAN_POWER_FUTURES": ("Japan", "JPY", "kWh", 17.2, -0.004, 1.4, "power", "prompt_month_cash_settled_futures", "Synthetic prompt-month Japan power futures proxy; cash-settled financial future, not physical delivery."),
        "JEPX_SYSTEM": ("Japan", "JPY", "kWh", 16.5, -0.006, 2.2, "power", "physical_day_ahead_forward_proxy", "Synthetic JEPX day-ahead system price forward proxy; physical spot reference."),
        "JEPX_TOKYO": ("Tokyo", "JPY", "kWh", 18.0, -0.007, 2.4, "power", "physical_day_ahead_forward_proxy", "Synthetic Tokyo area day-ahead forward proxy; physical spot reference."),
        "JEPX_KANSAI": ("Kansai", "JPY", "kWh", 15.6, -0.005, 2.0, "power", "physical_day_ahead_forward_proxy", "Synthetic Kansai area day-ahead forward proxy; physical spot reference."),
    }
    rows = []
    for curve_i, curve_date in enumerate(curve_dates):
        curve_shift = rng.normal(0, 0.4)
        for market, (region, currency, unit, front, slope, noise, shape, contract_type, source_note) in markets.items():
            for i, month in enumerate(contract_months):
                if shape == "crude":
                    seasonal = 1.0
                    market_shift = curve_shift * 0.35
                elif shape == "lng_oil_linked":
                    seasonal = 1.0 + 0.02 * np.cos((month.month - 1) / 12 * 2 * np.pi)
                    market_shift = curve_shift * 0.2
                elif shape == "light_seasonal":
                    seasonal = 1.0 + 0.035 * np.cos((month.month - 1) / 12 * 2 * np.pi)
                    market_shift = curve_shift * 2.0
                else:
                    seasonal = 1 + 0.10 * np.cos((month.month - 1) / 12 * 2 * np.pi) + 0.07 * np.exp(-((month.month - 8) / 2.2) ** 2)
                    market_shift = curve_shift
                price = (front + market_shift + slope * i * front) * seasonal + rng.normal(0, noise * 0.05)
                rows.append(
                    {
                        "curve_date": curve_date,
                        "contract_month": month,
                        "market": market,
                        "region": region,
                        "price": round(max(price, 0.01), 4),
                        "currency": currency,
                        "unit": unit,
                        "contract_type": contract_type,
                        "source_note": source_note,
                    }
                )
    return pd.DataFrame(rows)


def generate_power_futures_data(seed: int = 73) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    curve_dates = pd.to_datetime([
        pd.Timestamp.today().normalize() - pd.Timedelta(days=30),
        pd.Timestamp.today().normalize(),
    ])
    contract_months = pd.date_range(pd.Timestamp.today().normalize() + pd.offsets.MonthBegin(1), periods=18, freq="MS")
    specs = [
        ("Tokyo", "Baseload", 16.8, 2.2),
        ("Tokyo", "Peakload", 19.2, 2.9),
        ("Kansai", "Baseload", 14.9, 1.9),
        ("Kansai", "Peakload", 17.1, 2.5),
    ]
    rows = []
    for curve_date in curve_dates:
        curve_shift = rng.normal(0, 0.35)
        for area, load_type, front, amp in specs:
            for idx, month in enumerate(contract_months):
                summer = np.exp(-((month.month - 8) / 2.0) ** 2)
                winter = np.exp(-((month.month - 1) / 2.0) ** 2)
                seasonal = amp * (0.65 * summer + 0.45 * winter)
                slope = -0.025 * idx
                price = front + seasonal + slope + curve_shift + rng.normal(0, 0.15)
                rows.append(
                    {
                        "curve_date": curve_date,
                        "contract_month": month,
                        "area": area,
                        "load_type": load_type,
                        "settlement_price": round(max(price, 0.01), 4),
                        "currency": "JPY",
                        "unit": "kWh",
                        "contract_type": "monthly_cash_settled_futures",
                        "source": "synthetic_jpx_power_futures",
                        "source_note": "Synthetic monthly Japan electricity futures proxy. Replace with JSCC paid service, JPX/vendor settlements, or user-uploaded broker marks for production.",
                    }
                )
    return pd.DataFrame(rows)


def generate_market_mapping() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("JKM", "LNG", "Japan/Korea", "USD", "MMBtu", "Platts JKM LNG benchmark proxy"),
            ("DES_JAPAN_LNG", "LNG", "Japan", "USD", "MMBtu", "Delivered ex-ship Japan LNG proxy"),
            ("JCC", "Crude", "Japan", "USD", "bbl", "Synthetic Japan customs-cleared crude proxy. Real JCC is a monthly customs statistic, not an exchange futures contract."),
            ("JCC_LINKED_LNG", "LNG", "Japan", "USD", "MMBtu", "Oil-linked LNG contract proxy"),
            ("NEWCASTLE_COAL", "Coal", "Australia", "USD", "tonne", "Newcastle thermal coal benchmark proxy"),
            ("CFR_JAPAN_COAL", "Coal", "Japan", "USD", "tonne", "CFR Japan coal delivered proxy"),
            ("BRENT", "Crude", "Global", "USD", "bbl", "Synthetic Brent crude benchmark proxy. Production source should use EIA Brent spot history or ICE Brent futures settlements."),
            ("USDJPY", "FX", "Japan", "JPY", "USD", "USDJPY FX rate"),
            ("JEPX_SYSTEM", "Power", "Japan", "JPY", "kWh", "JEPX day-ahead system price proxy"),
            ("JEPX_INTRADAY", "Power", "Japan", "JPY", "kWh", "JEPX intraday price proxy"),
            ("JEPX_TOKYO", "Power", "Tokyo", "JPY", "kWh", "Tokyo area power price proxy"),
            ("JEPX_KANSAI", "Power", "Kansai", "JPY", "kWh", "Kansai area power price proxy"),
            ("JAPAN_POWER_FUTURES", "Power", "Japan", "JPY", "kWh", "Prompt-month cash-settled Japan power futures proxy; financial futures, not physical delivery."),
        ],
        columns=["market", "asset_class", "region", "currency", "unit", "description"],
    )


def generate_supply_mix_data(seed: int = 311) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.date_range(end=pd.Timestamp.today().normalize().to_period("M").to_timestamp(), periods=30, freq="MS")
    rows = []
    base_profiles = {
        "Tokyo": {
            "Gas": 0.49,
            "Coal": 0.22,
            "Nuclear": 0.00,
            "Solar": 0.09,
            "Hydro": 0.06,
            "Wind": 0.02,
            "Biomass": 0.04,
            "Oil": 0.03,
            "Other": 0.05,
        },
        "Kansai": {
            "Gas": 0.27,
            "Coal": 0.19,
            "Nuclear": 0.29,
            "Solar": 0.08,
            "Hydro": 0.08,
            "Wind": 0.02,
            "Biomass": 0.03,
            "Oil": 0.02,
            "Other": 0.02,
        },
    }
    demand_base = {"Tokyo": 24500, "Kansai": 11800}
    for month in months:
        summer = np.exp(-((month.month - 8) / 2.2) ** 2)
        winter = np.exp(-((month.month - 1) / 2.0) ** 2)
        solar_lift = 0.035 * np.cos((month.month - 5) / 12 * 2 * np.pi)
        for area, profile in base_profiles.items():
            total = demand_base[area] * (1 + 0.08 * summer + 0.06 * winter + rng.normal(0, 0.025))
            adjusted = profile.copy()
            adjusted["Solar"] = max(0.01, adjusted["Solar"] + solar_lift)
            adjusted["Gas"] = max(0.05, adjusted["Gas"] + 0.035 * summer + 0.02 * winter)
            adjusted["Hydro"] = max(0.02, adjusted["Hydro"] + 0.02 * np.cos((month.month - 7) / 12 * 2 * np.pi))
            noise = {fuel: 0.0 if profile[fuel] == 0 else max(0.001, share + rng.normal(0, 0.008)) for fuel, share in adjusted.items()}
            share_total = sum(noise.values())
            for fuel, share in noise.items():
                rows.append(
                    {
                        "month": month,
                        "area": area,
                        "generation_type": fuel,
                        "generation_gwh": round(total * share / share_total, 2),
                        "source": "synthetic_regional_generation_mix",
                        "source_note": "Synthetic monthly Tokyo/Kansai generation mix for dashboard workflow. Replace with OCCTO/TSO/METI/vendor regional generation data before production use.",
                    }
                )
    return pd.DataFrame(rows)


def write_sample_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generate_historical_data().to_csv(HISTORICAL_DATA_PATH, index=False)
    generate_forward_curves().to_csv(FORWARD_CURVES_PATH, index=False)
    generate_power_futures_data().to_csv(POWER_FUTURES_PATH, index=False)
    generate_weather_data().to_csv(WEATHER_DATA_PATH, index=False)
    generate_supply_mix_data().to_csv(SUPPLY_MIX_PATH, index=False)
    sample_power_news().to_csv(NEWS_EVENTS_PATH, index=False)
    generate_market_mapping().to_csv(MARKET_MAPPING_PATH, index=False)


if __name__ == "__main__":
    write_sample_data()
