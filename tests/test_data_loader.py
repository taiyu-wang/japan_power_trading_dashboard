from io import StringIO

import pandas as pd
import pytest

from src.data_loader import load_jepx_offer_stack_compact_curves, load_jepx_offer_stack_depth, load_uploaded_curve, normalize_forward_curve_upload, validate_forward_curve


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
