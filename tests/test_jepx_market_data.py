from io import StringIO

import pandas as pd

from src.jepx_market_data import (
    intraday_liquidity_by_day,
    normalize_jepx_baseload,
    normalize_jepx_intraday,
)


def test_normalize_jepx_intraday_translates_public_csv_schema():
    raw = pd.read_csv(
        StringIO(
            "年月日,時刻コード,始値(円/kWh),高値(円/kWh),安値(円/kWh),終値(円/kWh),平均(円/kWh),約定量合計(kWh),約定件数\n"
            "2026/04/01,1,20.10,22.61,8.52,9.48,16.72,301050,140\n"
        )
    )

    out = normalize_jepx_intraday(raw)

    assert out.iloc[0]["delivery_date"] == pd.Timestamp("2026-04-01")
    assert out.iloc[0]["time_code"] == 1
    assert out.iloc[0]["average_price_jpy_kwh"] == 16.72
    assert out.iloc[0]["total_volume_kwh"] == 301050
    assert out.iloc[0]["number_of_contracts"] == 140


def test_intraday_liquidity_by_day_calculates_range_and_activity():
    intraday = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-04-01", "2026-04-01"]),
            "time_code": [1, 2],
            "opening_price_jpy_kwh": [10, 12],
            "highest_price_jpy_kwh": [15, 18],
            "lowest_price_jpy_kwh": [8, 9],
            "last_price_jpy_kwh": [11, 13],
            "average_price_jpy_kwh": [12, 14],
            "total_volume_kwh": [1000, 3000],
            "number_of_contracts": [10, 30],
        }
    )
    spot = pd.DataFrame({"date": pd.to_datetime(["2026-04-01"]), "market": ["JEPX_SYSTEM"], "price": [13.0]})

    out = intraday_liquidity_by_day(intraday, spot)

    assert out.iloc[0]["intraday_average_price"] == 13
    assert out.iloc[0]["spot_price"] == 13
    assert out.iloc[0]["spot_intraday_spread"] == 0
    assert out.iloc[0]["total_volume_mwh"] == 4
    assert out.iloc[0]["number_of_contracts"] == 40


def test_normalize_jepx_baseload_translates_public_csv_schema():
    raw = pd.read_csv(
        StringIO(
            "商品名,基準価格エリア,約定日,約定価格(円/kWh),約定量(MW)\n"
            "BY2501B3,東京,2024/08/30,15.60,41.0\n"
            "BY2502B9,九州,2024/10/18,-,-\n"
        )
    )

    out = normalize_jepx_baseload(raw, fiscal_year=2025)

    assert out.iloc[0]["product_name"] == "BY2501B3"
    assert out.iloc[0]["area"] == "Tokyo"
    assert out.iloc[0]["trade_date"] == pd.Timestamp("2024-08-30")
    assert out.iloc[0]["clearing_price_jpy_kwh"] == 15.60
    assert out.iloc[1]["area"] == "Kyushu"
    assert pd.isna(out.iloc[1]["clearing_price_jpy_kwh"])
