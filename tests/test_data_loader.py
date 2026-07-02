from io import StringIO

import pandas as pd
import pytest

from src.data_loader import (
    get_generation_mix,
    load_historical_prices,
    load_jepx_intraday,
    load_jepx_offer_stack_compact_curves,
    load_jepx_offer_stack_depth,
    load_processed_generation_mix,
    load_supply_mix_daily_shape,
    load_supply_mix_residual_thermal,
    load_uploaded_curve,
    normalize_forward_curve_upload,
    validate_forward_curve,
)


def test_historical_loader_overrides_bundled_jepx_with_published_daily(monkeypatch, tmp_path):
    local_path = tmp_path / "historical.csv"
    local_path.write_text(
        "date,market,region,asset_class,frequency,contract,price,currency,unit\n"
        "2026-06-08,JEPX_SYSTEM,Japan,Power,daily,spot,10.0,JPY,JPY/kWh\n"
        "2026-06-08,JKM,Japan,Fuel,daily,spot,12.0,USD,USD/MMBtu\n"
    )
    published_spot = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-08", "2026-07-01"]),
            "market": ["JEPX_SYSTEM", "JEPX_SYSTEM"],
            "region": ["Japan", "Japan"],
            "asset_class": ["Power", "Power"],
            "frequency": ["daily", "daily"],
            "contract": ["day-ahead physical", "day-ahead physical"],
            "price": [20.0, 30.0],
            "currency": ["JPY", "JPY"],
            "unit": ["JPY/kWh", "JPY/kWh"],
        }
    )
    published_intraday = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-07-01", "2026-07-01"]),
            "average_price_jpy_kwh": [15.0, 17.0],
        }
    )

    def published(filename, **kwargs):
        if filename == "jepx_spot_daily.csv":
            return published_spot.copy()
        if filename == "jepx_intraday.csv":
            return published_intraday.copy()
        raise OSError("not used")

    monkeypatch.setattr("src.data_loader.load_published_csv", published)
    load_historical_prices.clear()

    out = load_historical_prices(local_path, use_published=True)

    system = out[out["market"].eq("JEPX_SYSTEM")].set_index("date")["price"]
    assert system.loc[pd.Timestamp("2026-06-08")] == 20.0
    assert system.loc[pd.Timestamp("2026-07-01")] == 30.0
    assert len(system) == 2
    intraday = out[out["market"].eq("JEPX_INTRADAY")]
    assert intraday.iloc[0]["date"] == pd.Timestamp("2026-07-01")
    assert intraday.iloc[0]["price"] == 16.0
    assert out[out["market"].eq("JKM")].iloc[0]["price"] == 12.0


def test_generation_mix_prefers_scheduled_published_artifact(monkeypatch):
    remote = pd.DataFrame(
        {
            "month": ["2026-06-01"],
            "area": ["Tokyo"],
            "generation_type": ["Gas"],
            "generation_gwh": [100.0],
            "source": ["Public source"],
            "source_note": ["Complete month"],
        }
    )
    monkeypatch.setattr("src.data_loader.load_published_csv", lambda *args, **kwargs: remote.copy())
    load_processed_generation_mix.clear()

    out, warnings, source = get_generation_mix(True)

    assert out.iloc[0]["month"] == pd.Timestamp("2026-06-01")
    assert warnings == []
    assert source == "Processed JapanesePower.org Tokyo/Kansai aggregates (scheduled)"


def test_supply_shape_loaders_prefer_scheduled_artifacts(monkeypatch):
    frames = {
        "supply_mix_daily_shape.csv": pd.DataFrame(
            {"date": [pd.Timestamp("2026-07-01")], "area": ["Tokyo"], "thermal_ramp_mw": [500.0]}
        ),
        "supply_mix_residual_thermal.csv": pd.DataFrame(
            {"month": [pd.Timestamp("2026-06-01")], "area": ["Tokyo"], "residual_thermal_share_pct": [60.0]}
        ),
    }
    monkeypatch.setattr(
        "src.data_loader.load_published_csv",
        lambda filename, **kwargs: frames[filename].copy(),
    )
    load_supply_mix_daily_shape.clear()
    load_supply_mix_residual_thermal.clear()

    daily = load_supply_mix_daily_shape(use_published=True)
    residual = load_supply_mix_residual_thermal(use_published=True)

    assert daily.iloc[0]["date"] == pd.Timestamp("2026-07-01")
    assert residual.iloc[0]["month"] == pd.Timestamp("2026-06-01")


def test_uploaded_curve_accepts_minimal_schema_and_fills_defaults():
    csv = StringIO("curve_date,contract_month,market,price\n2026-05-27,2026-06-01,jkm,12.4\n")
    out = load_uploaded_curve(csv)

    assert out.iloc[0]["market"] == "JKM"
    assert out.iloc[0]["contract_type"] == "uploaded_curve"
    assert {"region", "currency", "unit", "source_note"}.issubset(out.columns)


def test_uploaded_curve_rejects_missing_required_columns():
    csv = StringIO("curve_date,market,price\n2026-05-27,JKM,12.4\n")

    with pytest.raises(ValueError, match="contract_month"):
        load_uploaded_curve(csv)


def test_forward_curve_validation_flags_invalid_dates_and_prices():
    raw = pd.DataFrame(
        {
            "curve_date": ["bad-date"],
            "contract_month": ["2026-06-01"],
            "market": ["JKM"],
            "price": ["not-a-number"],
        }
    )
    normalized = normalize_forward_curve_upload(raw)
    diagnostics = validate_forward_curve(normalized)

    assert not diagnostics.ok
    assert any("prices" in error for error in diagnostics.errors)
    assert any("curve_date" in error for error in diagnostics.errors)


def test_processed_offer_stack_loaders_parse_dates(tmp_path):
    depth_path = tmp_path / "depth.csv"
    depth_path.write_text(
        "delivery_date,time_code,area_group,clearing_price_estimate,upside_depth_mw,downside_depth_mw,tightest_depth_mw,price_band_jpy_kwh,stack_regime\n"
        "2026-06-02,37,System Price,27,1000,1200,1000,5,Balanced stack\n"
    )
    compact_path = tmp_path / "compact.csv"
    compact_path.write_text(
        "delivery_date,time_code,area_group,bid_price_jpy_kwh,sell_cumulative_mw,buy_cumulative_mw,net_supply_mw,source\n"
        "2026-06-02,37,System Price,25,30000,31000,-1000,JEPX processed sampled bidding curve\n"
    )

    depth = load_jepx_offer_stack_depth(depth_path)
    compact = load_jepx_offer_stack_compact_curves(compact_path)

    assert depth.iloc[0]["delivery_date"] == pd.Timestamp("2026-06-02")
    assert compact.iloc[0]["delivery_date"] == pd.Timestamp("2026-06-02")


def test_intraday_loader_prefers_published_artifact(monkeypatch, tmp_path):
    local_path = tmp_path / "intraday.csv"
    local_path.write_text(
        "delivery_date,time_code,average_price_jpy_kwh\n"
        "2026-06-01,1,10.0\n"
    )
    remote = pd.DataFrame(
        {
            "delivery_date": [pd.Timestamp("2026-06-30")],
            "time_code": [1],
            "average_price_jpy_kwh": [20.0],
        }
    )
    monkeypatch.setattr("src.data_loader.load_published_csv", lambda *args, **kwargs: remote.copy())
    load_jepx_intraday.clear()

    out = load_jepx_intraday(local_path, use_published=True)

    assert out.iloc[0]["delivery_date"] == pd.Timestamp("2026-06-30")
    assert out.iloc[0]["average_price_jpy_kwh"] == 20.0


def test_intraday_loader_falls_back_to_local_file(monkeypatch, tmp_path):
    local_path = tmp_path / "intraday.csv"
    local_path.write_text(
        "delivery_date,time_code,average_price_jpy_kwh\n"
        "2026-06-01,1,10.0\n"
    )

    def failed_remote(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr("src.data_loader.load_published_csv", failed_remote)
    load_jepx_intraday.clear()

    out = load_jepx_intraday(local_path, use_published=True)

    assert out.iloc[0]["delivery_date"] == pd.Timestamp("2026-06-01")
    assert out.iloc[0]["average_price_jpy_kwh"] == 10.0
