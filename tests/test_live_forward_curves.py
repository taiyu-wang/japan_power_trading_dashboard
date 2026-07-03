import pandas as pd

import src.live_forward_curves as live_forward_curves_module
from src.live_forward_curves import LIVE_CURVE_COLUMNS, LiveCurveResult, fetch_live_forward_curves


def _brent_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "curve_date": pd.Timestamp("2026-07-01"),
                "contract_month": pd.Timestamp("2026-09-01"),
                "market": "BRENT",
                "region": "Global",
                "price": 80.0,
                "currency": "USD",
                "unit": "bbl",
                "contract_type": "financial_futures",
                "source_note": "fixture",
            }
        ]
    )


def test_fetch_live_forward_curves_fails_fast_on_empty_brent(monkeypatch):
    monkeypatch.setattr(
        live_forward_curves_module,
        "fetch_brent_curve_oilprice",
        lambda: pd.DataFrame(columns=["curve_date", "contract_month", "market", "price"]),
    )

    result = fetch_live_forward_curves()

    assert isinstance(result, LiveCurveResult)
    assert result.data.empty
    assert list(result.data.columns) == LIVE_CURVE_COLUMNS
    assert any("no contract rows" in warning for warning in result.warnings)


def test_fetch_live_forward_curves_derives_jcc_curves_from_brent(monkeypatch):
    monkeypatch.setattr(live_forward_curves_module, "fetch_brent_curve_oilprice", _brent_fixture)

    result = fetch_live_forward_curves()

    assert set(result.data["market"]) == {"BRENT", "JCC", "JCC_LINKED_LNG"}
    # tenor_label is only added once quarterly strips exist, so a monthly-only curve omits it.
    assert set(LIVE_CURVE_COLUMNS).difference({"tenor_label"}).issubset(result.data.columns)
    assert result.data["price"].notna().all()
