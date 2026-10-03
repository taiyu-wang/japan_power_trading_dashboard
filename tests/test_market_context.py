from io import StringIO

import numpy as np
import pandas as pd
import pytest

from src.data_loader import load_uploaded_historical
from src.indicators import calculate_srmc_comparison, latest_snapshot, spread_suite
from src.market_context import aligned_changes, bounded_prices, eligible_history
from src.preprocessing import convert_frequency, handle_missing_values, prepare_historical


def history():
    rows = []
    for day in pd.date_range("2026-08-01", periods=63):
        for market, price, unit, currency in [
            ("JEPX_SYSTEM", 12, "kWh", "JPY"), ("JKM", 10, "MMBtu", "USD"),
            ("NEWCASTLE_COAL", 100, "tonne", "USD"), ("JCC", 70, "bbl", "USD"),
            ("USDJPY", 150, "JPY/USD", "JPY"),
        ]:
            rows.append(dict(date=day, market=market, price=price, unit=unit, currency=currency,
                             region="Japan", asset_class="Power" if market.startswith("JEPX") else "Fuel",
                             frequency="daily", contract="spot", source_type="public"))
    return pd.DataFrame(rows)


def test_raw_power_spikes_and_missing_prices_survive_default_preprocessing():
    df = history()
    df.loc[df["market"].eq("JEPX_SYSTEM") & df["date"].eq(df["date"].max()), "price"] = 500
    df.loc[df["market"].eq("JKM") & df["date"].eq(df["date"].min()), "price"] = np.nan
    out = prepare_historical(df)
    assert out.loc[out["market"].eq("JEPX_SYSTEM"), "price"].max() == 500
    assert pd.isna(out.loc[out["market"].eq("JKM")].iloc[0]["price"])
    assert pd.isna(handle_missing_values(df).loc[lambda f: f["market"].eq("JKM")].iloc[0]["price"])


@pytest.mark.parametrize("frequency,rows", [("monthly", 3), ("quarterly", 2)])
def test_frequency_conversion_supports_modern_pandas(frequency, rows):
    assert len(convert_frequency(history(), frequency).query("market == 'JKM'")) == rows


def test_srmc_stops_carrying_fuel_marks_but_keeps_current_power():
    df = history()
    missing = df["date"].ge(pd.Timestamp("2026-09-25")) & df["market"].isin(["JKM", "NEWCASTLE_COAL", "USDJPY"])
    df = df[~missing]
    prices = bounded_prices(df)
    assert prices.loc["2026-09-28", "JKM"] == 10
    assert pd.isna(prices.loc["2026-09-29", "JKM"])
    out = calculate_srmc_comparison(df)
    assert out["date"].max() == pd.Timestamp("2026-10-02")
    assert pd.isna(out.iloc[-1]["jkm_gas_srmc"])
    assert out.iloc[-1]["jepx_system"] == 12


def test_gas_cost_does_not_require_an_oil_linked_quote():
    df = history().query("market != 'JCC'")
    out = calculate_srmc_comparison(df)
    assert out["jkm_gas_srmc"].notna().all()
    assert out["jcc_11_srmc"].isna().all()


def test_snapshot_change_ends_at_each_market_quote_not_global_latest():
    df = history()
    df = df[~(df["market"].eq("JKM") & df["date"].gt("2026-09-05"))]
    df.loc[df["market"].eq("JKM") & df["date"].eq("2026-09-05"), "price"] = 15
    snapshot = latest_snapshot(df, as_of="2026-10-02").set_index("market")
    assert snapshot.loc["JKM", "change_30d_pct"] == 50
    assert snapshot.loc["JKM", "age_days"] == 27


def test_changes_use_calendar_days_and_common_observations():
    prices = pd.DataFrame({"JKM": [10, 20, 30], "COAL": [100, 110, np.nan]},
                          index=pd.to_datetime(["2026-08-31", "2026-09-30", "2026-10-02"]))
    changes, date = aligned_changes(prices, ["JKM", "COAL"])
    assert date == pd.Timestamp("2026-09-30")
    assert changes["JKM"] == 100
    assert changes["COAL"] == pytest.approx(10)


def test_spreads_are_economic_costs_or_same_unit_price_pairs():
    spreads = spread_suite(history())
    assert {"Gas minus coal SRMC", "Indicative gas margin", "Indicative coal margin"} <= set(spreads["market"])
    assert "JKM minus coal" not in set(spreads["market"])
    assert spreads.loc[spreads["price"].notna(), "unit"].eq("JPY/kWh").all()


def test_tomorrow_delivery_allowed_only_for_jepx_not_fuel_marks():
    df = history().iloc[:2].assign(date=pd.Timestamp("2026-10-03"))
    out = eligible_history(df, as_of="2026-10-02")
    assert out["market"].tolist() == ["JEPX_SYSTEM"]


@pytest.mark.parametrize("csv,error", [
    ("date,market,price,currency,unit\ninvalid,JKM,10,USD,MMBtu", "Invalid dates"),
    ("date,market,price,currency,unit\n2026-10-01,JKM,inf,USD,MMBtu", "non-finite"),
    ("date,market,price,currency,unit\n2026-10-01,JKM,10,JPY,kWh", "consistent analytics"),
    ("date,market,price,currency,unit\n2026-10-01,JKM,10,USD,MMBtu\n2026-10-01,JKM,12,USD,MMBtu", "Duplicate"),
])
def test_historical_upload_rejects_unsafe_inputs(csv, error):
    with pytest.raises(ValueError, match=error):
        load_uploaded_historical(StringIO(csv))


def test_historical_upload_is_explicitly_classified_and_dates_normalized():
    frame = load_uploaded_historical(StringIO("date,market,price,currency,unit\n2026-10-01T14:30:00,jkm,10,usd,MMBtu"))
    assert frame.iloc[0]["date"] == pd.Timestamp("2026-10-01")
    assert frame.iloc[0]["source_type"] == "uploaded"
    assert frame.iloc[0]["asset_class"] == "Fuel"
