import pandas as pd
import pytest

from src.power_futures import normalize_power_futures, power_futures_front_snapshot, power_futures_peak_premium


def _sample_futures() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "curve_date": ["2026-05-30"] * 4,
            "contract_month": ["2026-06-01", "2026-06-01", "2026-06-01", "2026-06-01"],
            "area": ["Tokyo", "Tokyo", "Kansai", "Kansai"],
            "load_type": ["Baseload", "Peakload", "Baseload", "Peakload"],
            "settlement_price": [16.0, 19.0, 14.0, 16.5],
        }
    )


def test_power_futures_normalization_fills_defaults():
    out = normalize_power_futures(_sample_futures())

    assert {"currency", "unit", "contract_type", "source_note", "product"}.issubset(out.columns)
    assert out["currency"].eq("JPY").all()
    assert out["unit"].eq("kWh").all()


def test_power_futures_peak_premium_calculates_by_area():
    premium = power_futures_peak_premium(_sample_futures())

    tokyo = premium[premium["area"] == "Tokyo"].iloc[0]
    kansai = premium[premium["area"] == "Kansai"].iloc[0]
    assert tokyo["peak_premium"] == 3.0
    assert kansai["peak_premium"] == 2.5


def test_power_futures_rejects_invalid_price():
    bad = _sample_futures()
    bad.loc[0, "settlement_price"] = -1

    with pytest.raises(ValueError, match="non-positive"):
        normalize_power_futures(bad)


def test_power_futures_front_snapshot_has_one_point_per_product():
    snapshot = power_futures_front_snapshot(_sample_futures())

    assert len(snapshot) == 4
    assert set(snapshot["product"]) == {"Tokyo Baseload", "Tokyo Peakload", "Kansai Baseload", "Kansai Peakload"}
