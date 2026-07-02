from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests


JEPX_BASE_URL = "https://www.jepx.jp"
JEPX_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.jepx.jp/electricpower/market-data/spot/"}

INTRADAY_RENAME = {
    "年月日": "delivery_date",
    "時刻コード": "time_code",
    "始値(円/kWh)": "opening_price_jpy_kwh",
    "高値(円/kWh)": "highest_price_jpy_kwh",
    "安値(円/kWh)": "lowest_price_jpy_kwh",
    "終値(円/kWh)": "last_price_jpy_kwh",
    "平均(円/kWh)": "average_price_jpy_kwh",
    "約定量合計(kWh)": "total_volume_kwh",
    "約定件数": "number_of_contracts",
}

SPOT_RENAME = {
    "受渡日": "delivery_date",
    "時刻コード": "time_code",
    "システムプライス(円/kWh)": "system_price_jpy_kwh",
    "エリアプライス東京(円/kWh)": "tokyo_price_jpy_kwh",
    "エリアプライス関西(円/kWh)": "kansai_price_jpy_kwh",
}

BASELOAD_RENAME = {
    "商品名": "product_name",
    "基準価格エリア": "area",
    "約定日": "trade_date",
    "約定価格(円/kWh)": "clearing_price_jpy_kwh",
    "約定量(MW)": "volume_mw",
}

AREA_TRANSLATIONS = {
    "北海道": "Hokkaido",
    "東京": "Tokyo",
    "関西": "Kansai",
    "九州": "Kyushu",
}


def _public_csv_url(directory: str, year: int) -> str:
    return f"{JEPX_BASE_URL}/js/csv_read.php?dir={directory}&file={directory}_{year}.csv"


def _fetch_jepx_csv(directory: str, year: int, timeout: int = 20) -> pd.DataFrame:
    response = requests.get(_public_csv_url(directory, year), headers=JEPX_HEADERS, timeout=timeout)
    response.raise_for_status()
    if not response.text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(response.text))


def normalize_jepx_spot(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns=SPOT_RENAME).copy()
    missing = sorted(set(SPOT_RENAME.values()).difference(out.columns))
    if missing:
        raise ValueError(f"JEPX spot data is missing required columns: {', '.join(missing)}")
    out["delivery_date"] = pd.to_datetime(out["delivery_date"], errors="coerce").dt.tz_localize(None)
    out["time_code"] = pd.to_numeric(out["time_code"], errors="coerce").astype("Int64")
    price_columns = ["system_price_jpy_kwh", "tokyo_price_jpy_kwh", "kansai_price_jpy_kwh"]
    for column in price_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["delivery_date", "time_code", *price_columns]).copy()
    out["time_code"] = out["time_code"].astype(int)
    out["source"] = "JEPX public day-ahead spot summary CSV"
    return out[["delivery_date", "time_code", *price_columns, "source"]].sort_values(
        ["delivery_date", "time_code"]
    ).reset_index(drop=True)


def _standardized_power_history(
    daily: pd.DataFrame,
    market_specs: dict[str, tuple[str, str]],
    *,
    contract: str,
) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(
            columns=["date", "market", "region", "asset_class", "frequency", "contract", "price", "currency", "unit"]
        )
    rows = []
    for price_column, (market, region) in market_specs.items():
        market_frame = daily[["delivery_date", price_column]].rename(
            columns={"delivery_date": "date", price_column: "price"}
        )
        market_frame["market"] = market
        market_frame["region"] = region
        rows.append(market_frame)
    out = pd.concat(rows, ignore_index=True)
    out["asset_class"] = "Power"
    out["frequency"] = "daily"
    out["contract"] = contract
    out["currency"] = "JPY"
    out["unit"] = "JPY/kWh"
    columns = ["date", "market", "region", "asset_class", "frequency", "contract", "price", "currency", "unit"]
    return out[columns].sort_values(["market", "date"]).reset_index(drop=True)


def daily_jepx_spot_prices(spot: pd.DataFrame) -> pd.DataFrame:
    if spot.empty:
        return _standardized_power_history(pd.DataFrame(), {}, contract="day-ahead physical")
    price_columns = ["system_price_jpy_kwh", "tokyo_price_jpy_kwh", "kansai_price_jpy_kwh"]
    daily = spot.groupby("delivery_date", as_index=False)[price_columns].mean()
    return _standardized_power_history(
        daily,
        {
            "system_price_jpy_kwh": ("JEPX_SYSTEM", "Japan"),
            "tokyo_price_jpy_kwh": ("JEPX_TOKYO", "Tokyo"),
            "kansai_price_jpy_kwh": ("JEPX_KANSAI", "Kansai"),
        },
        contract="day-ahead physical",
    )


def daily_jepx_intraday_prices(intraday: pd.DataFrame) -> pd.DataFrame:
    if intraday.empty:
        return _standardized_power_history(pd.DataFrame(), {}, contract="intraday physical")
    daily = intraday.groupby("delivery_date", as_index=False)["average_price_jpy_kwh"].mean()
    return _standardized_power_history(
        daily,
        {"average_price_jpy_kwh": ("JEPX_INTRADAY", "Japan")},
        contract="intraday physical",
    )


def normalize_jepx_intraday(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns=INTRADAY_RENAME).copy()
    missing = sorted(set(INTRADAY_RENAME.values()).difference(out.columns))
    if missing:
        raise ValueError(f"JEPX intraday data is missing required columns: {', '.join(missing)}")
    out["delivery_date"] = pd.to_datetime(out["delivery_date"], errors="coerce").dt.tz_localize(None)
    out["time_code"] = pd.to_numeric(out["time_code"], errors="coerce").astype("Int64")
    for col in [
        "opening_price_jpy_kwh",
        "highest_price_jpy_kwh",
        "lowest_price_jpy_kwh",
        "last_price_jpy_kwh",
        "average_price_jpy_kwh",
        "total_volume_kwh",
        "number_of_contracts",
    ]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["delivery_date", "time_code"]).copy()
    out["time_code"] = out["time_code"].astype(int)
    out["source"] = "JEPX public intraday CSV"
    return out[
        [
            "delivery_date",
            "time_code",
            "opening_price_jpy_kwh",
            "highest_price_jpy_kwh",
            "lowest_price_jpy_kwh",
            "last_price_jpy_kwh",
            "average_price_jpy_kwh",
            "total_volume_kwh",
            "number_of_contracts",
            "source",
        ]
    ].sort_values(["delivery_date", "time_code"]).reset_index(drop=True)


def intraday_liquidity_by_day(intraday: pd.DataFrame, spot_prices: pd.DataFrame | None = None) -> pd.DataFrame:
    if intraday.empty:
        return pd.DataFrame()
    daily = (
        intraday.assign(price_range_jpy_kwh=intraday["highest_price_jpy_kwh"] - intraday["lowest_price_jpy_kwh"])
        .groupby("delivery_date", as_index=False)
        .agg(
            intraday_average_price=("average_price_jpy_kwh", "mean"),
            intraday_last_price=("last_price_jpy_kwh", "mean"),
            intraday_high_low_range=("price_range_jpy_kwh", "mean"),
            total_volume_kwh=("total_volume_kwh", "sum"),
            number_of_contracts=("number_of_contracts", "sum"),
        )
    )
    daily["total_volume_mwh"] = daily["total_volume_kwh"] / 1000
    daily["liquidity_score"] = daily["total_volume_mwh"].rank(pct=True) * 50 + daily["number_of_contracts"].rank(pct=True) * 50
    if spot_prices is not None and not spot_prices.empty:
        spot = spot_prices[spot_prices["market"].eq("JEPX_SYSTEM")][["date", "price"]].rename(
            columns={"date": "delivery_date", "price": "spot_price"}
        )
        spot["delivery_date"] = pd.to_datetime(spot["delivery_date"], errors="coerce").dt.normalize()
        daily["delivery_date"] = pd.to_datetime(daily["delivery_date"], errors="coerce").dt.normalize()
        daily = daily.merge(spot, on="delivery_date", how="left")
        daily["spot_intraday_spread"] = daily["spot_price"] - daily["intraday_average_price"]
    else:
        daily["spot_price"] = pd.NA
        daily["spot_intraday_spread"] = pd.NA
    return daily.sort_values("delivery_date").reset_index(drop=True)


def normalize_jepx_baseload(df: pd.DataFrame, fiscal_year: int | None = None) -> pd.DataFrame:
    out = df.rename(columns=BASELOAD_RENAME).copy()
    missing = sorted(set(BASELOAD_RENAME.values()).difference(out.columns))
    if missing:
        raise ValueError(f"JEPX baseload data is missing required columns: {', '.join(missing)}")
    out["area"] = out["area"].map(lambda value: AREA_TRANSLATIONS.get(str(value), str(value)))
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.tz_localize(None)
    out["clearing_price_jpy_kwh"] = pd.to_numeric(out["clearing_price_jpy_kwh"], errors="coerce")
    out["volume_mw"] = pd.to_numeric(out["volume_mw"], errors="coerce")
    if fiscal_year is None:
        fiscal_year = int(out["trade_date"].dropna().dt.year.max()) if out["trade_date"].notna().any() else pd.NA
    out["fiscal_year"] = fiscal_year
    out["source"] = "JEPX public baseload CSV"
    return out[["fiscal_year", "product_name", "area", "trade_date", "clearing_price_jpy_kwh", "volume_mw", "source"]].reset_index(drop=True)


def fetch_jepx_intraday_year(year: int, timeout: int = 20) -> pd.DataFrame:
    return normalize_jepx_intraday(_fetch_jepx_csv("intraday", year, timeout=timeout))


def fetch_jepx_spot_fiscal_year(year: int, timeout: int = 20) -> pd.DataFrame:
    return normalize_jepx_spot(_fetch_jepx_csv("spot_summary", year, timeout=timeout))


def fetch_jepx_baseload_year(year: int, timeout: int = 20) -> pd.DataFrame:
    return normalize_jepx_baseload(_fetch_jepx_csv("baseload", year, timeout=timeout), fiscal_year=year)


def write_jepx_public_market_data(
    intraday_path: str | Path,
    baseload_path: str | Path,
    intraday_year: int,
    baseload_years: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    intraday = fetch_jepx_intraday_year(intraday_year)
    baseload_frames = [fetch_jepx_baseload_year(year) for year in baseload_years]
    baseload = pd.concat([frame for frame in baseload_frames if not frame.empty], ignore_index=True) if baseload_frames else pd.DataFrame()
    intraday_output = Path(intraday_path)
    baseload_output = Path(baseload_path)
    intraday_output.parent.mkdir(parents=True, exist_ok=True)
    baseload_output.parent.mkdir(parents=True, exist_ok=True)
    intraday.to_csv(intraday_output, index=False)
    baseload.to_csv(baseload_output, index=False)
    return intraday, baseload
