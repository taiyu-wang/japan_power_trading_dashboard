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
                    "source_type": "public",
                }
            )
    return pd.DataFrame(rows)


def test_generate_trading_signals_returns_typed_empty_frame_when_quiet():
    frame = _flat_history()
    out = generate_trading_signals(frame, pd.DataFrame(), as_of=frame["date"].max())

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

    out = generate_trading_signals(df, curves, as_of=df["date"].max())

    assert not out.empty
    assert out["signal_time_sgt"].str.endswith("SGT").all()
    assert out["market_data_as_of"].eq(df["date"].max().strftime("%Y-%m-%d")).all()
    assert out["rationale"].notna().all()
    assert out["trader_interpretation"].notna().all()
    assert out["invalidation"].notna().all()
    assert out["evidence_strength"].isin(["Strong", "Moderate", "Limited"]).all()


def test_stale_synthetic_and_unlabelled_inputs_do_not_emit_current_alerts():
    df = _flat_history(periods=80)
    df.loc[(df["market"] == "JKM") & (df["date"] > df["date"].max() - pd.Timedelta(days=30)), "price"] = 20
    assert generate_trading_signals(df, pd.DataFrame(), as_of="2026-10-02").empty
    assert generate_trading_signals(df.assign(source_type="synthetic"), pd.DataFrame(), as_of=df["date"].max()).empty
    assert generate_trading_signals(df.drop(columns="source_type"), pd.DataFrame(), as_of=df["date"].max()).empty


def test_curve_alerts_exclude_samples_and_expired_contracts_and_use_curve_date():
    curves = pd.DataFrame({
        "curve_date": pd.to_datetime(["2026-10-01"] * 13),
        "contract_month": pd.date_range("2026-09-01", periods=13, freq="MS"),
        "market": ["JKM"] * 13, "price": [200] + [10 + i for i in range(12)], "source_type": ["uploaded"] * 13,
    })
    empty = _flat_history().iloc[:0]
    out = generate_trading_signals(empty, curves, as_of="2026-10-02")
    assert out["signal_name"].tolist() == ["Curve contango"]
    assert out["market_data_as_of"].tolist() == ["2026-10-01"]
    assert generate_trading_signals(empty, curves.assign(source_type="synthetic"), as_of="2026-10-02").empty
    assert generate_trading_signals(empty, curves, as_of="2026-10-10").empty


def test_calendar_season_alone_is_not_a_signal():
    df = _flat_history("2026-04-01", 95)
    assert generate_trading_signals(df, pd.DataFrame(), as_of=df["date"].max()).empty


def test_coal_benchmark_signal_does_not_claim_confirmed_dispatch_advantage():
    df = _flat_history(periods=80)
    latest = df["date"].max()
    df.loc[df["market"].eq("NEWCASTLE_COAL") & df["date"].gt(latest - pd.Timedelta(days=30)), "price"] = 120.0
    out = generate_trading_signals(df, pd.DataFrame(), as_of=latest)
    signal = out[out["signal_name"].eq("Coal competitiveness shift")].iloc[0]
    assert signal["direction"] == "Coal benchmark outperforming LNG"
    assert "delivered SRMC" in signal["trader_interpretation"]


def test_signal_methodology_documents_rule_inputs_and_confidence():
    methodology = signal_methodology()

    assert {"signal_name", "trigger", "inputs", "confidence", "read"}.issubset(methodology.columns)
    assert "Gas SRMC premium widening" in set(methodology["signal_name"])
    assert methodology["trigger"].str.len().gt(20).all()
    assert methodology["confidence"].str.len().gt(5).all()
