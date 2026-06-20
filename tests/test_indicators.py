import pandas as pd

from src.indicators import calculate_srmc_comparison, coal_thermal_mwh_per_tonne, daily_returns, latest_snapshot


def test_latest_snapshot_calculates_30d_change():
    dates = pd.date_range("2024-01-01", periods=40)
    df = pd.DataFrame(
        {
            "date": dates,
            "market": ["JKM"] * 40,
            "region": ["Japan"] * 40,
            "asset_class": ["LNG"] * 40,
            "frequency": ["daily"] * 40,
            "contract": ["spot"] * 40,
            "price": [10] * 10 + [20] * 30,
            "currency": ["USD"] * 40,
            "unit": ["MMBtu"] * 40,
        }
    )
    out = latest_snapshot(df)
    assert out.iloc[0]["price"] == 20
    assert out.iloc[0]["change_30d_pct"] == 100


def test_daily_returns_long_format():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "market": ["A"] * 3, "price": [100, 110, 99]})
    out = daily_returns(df)
    assert set(out.columns) == {"date", "market", "return_pct"}
    assert len(out) == 2


def _srmc_fixture() -> pd.DataFrame:
    date = pd.Timestamp("2026-01-01")
    rows = []
    prices = {
        "JKM": 10.0,
        "JCC": 70.0,
        "USDJPY": 150.0,
        "JEPX_SYSTEM": 18.0,
        "NEWCASTLE_COAL": 200.0,
        "CFR_JAPAN_COAL": 100.0,
    }
    for market, price in prices.items():
        rows.append(
            {
                "date": date,
                "market": market,
                "region": "Japan",
                "asset_class": "Power" if market.startswith("JEPX") else "Fuel",
                "frequency": "daily",
                "contract": "spot",
                "price": price,
                "currency": "JPY" if market.startswith("JEPX") else "USD",
                "unit": "kWh" if market.startswith("JEPX") else "unit",
            }
        )
    return pd.DataFrame(rows)


def test_coal_thermal_mwh_per_tonne_matches_6000_kcal_reference():
    assert round(coal_thermal_mwh_per_tonne(6000), 3) == 6.978


def test_coal_srmc_prefers_cfr_japan_over_newcastle_when_available():
    out = calculate_srmc_comparison(_srmc_fixture(), coal_efficiency=0.40, coal_vom_jpy_mwh=700.0)
    expected_jpy_kwh = (100.0 * 150.0 / (coal_thermal_mwh_per_tonne(6000) * 0.40) + 700.0) / 1000

    assert out.iloc[0]["coal_reference_market"] == "CFR_JAPAN_COAL"
    assert round(out.iloc[0]["coal_srmc"], 6) == round(expected_jpy_kwh, 6)


def test_coal_srmc_falls_back_to_newcastle_when_delivered_marker_missing():
    df = _srmc_fixture()
    df = df[df["market"] != "CFR_JAPAN_COAL"]
    out = calculate_srmc_comparison(df, coal_efficiency=0.40, coal_vom_jpy_mwh=700.0)

    assert out.iloc[0]["coal_reference_market"] == "NEWCASTLE_COAL"
