import pandas as pd

from src.signals import SIGNAL_COLUMNS, generate_trading_signals, signal_methodology


def _flat_history(start: str = "2026-03-01", periods: int = 45) -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="D")
    markets = {
        "JKM": 10.0,
        "NEWCASTLE_COAL": 100.0,
        "JCC_LINKED_LNG": 9.5,
        "JEPX_SYSTEM": 12.0,
        "JEPX_TOKYO": 12.0,
        "JEPX_KANSAI": 12.0,
        "JEPX_INTRADAY": 12.0,
        "JCC": 70.0,
        "USDJPY": 150.0,
    }
    rows = []
    for market, price in markets.items():
        for date in dates:
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
                    "unit": "kWh" if market.startswith("JEPX") else "MMBtu",
                }
            )
    return pd.DataFrame(rows)


def test_generate_trading_signals_returns_typed_empty_frame_when_quiet():
    out = generate_trading_signals(_flat_history(), pd.DataFrame())

    assert list(out.columns) == SIGNAL_COLUMNS


def test_every_signal_has_trader_rationale_and_invalidation():
    df = _flat_history(periods=80)
    df.loc[(df["market"] == "JKM") & (df["date"] > df["date"].max() - pd.Timedelta(days=30)), "price"] = 14.0
    curves = pd.DataFrame(
        {
            "curve_date": [pd.Timestamp("2026-05-27")] * 12,
            "contract_month": pd.date_range("2026-06-01", periods=12, freq="MS"),
            "market": ["JKM"] * 12,
            "region": ["Japan"] * 12,
            "price": [12 - i * 0.2 for i in range(12)],
            "currency": ["USD"] * 12,
            "unit": ["MMBtu"] * 12,
        }
    )

    out = generate_trading_signals(df, curves)

    assert not out.empty
    assert out["signal_time_sgt"].str.endswith("SGT").all()
    assert out["market_data_as_of"].eq(df["date"].max().strftime("%Y-%m-%d")).all()
    assert out["rationale"].notna().all()
    assert out["trader_interpretation"].notna().all()
    assert out["invalidation"].notna().all()


def test_signal_methodology_documents_rule_inputs_and_confidence():
    methodology = signal_methodology()

    assert {"signal_name", "trigger", "inputs", "confidence", "read"}.issubset(methodology.columns)
    assert "Gas SRMC premium widening" in set(methodology["signal_name"])
    assert methodology["trigger"].str.len().gt(20).all()
    assert methodology["confidence"].str.len().gt(5).all()
