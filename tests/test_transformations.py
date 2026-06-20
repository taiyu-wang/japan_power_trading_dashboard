import pandas as pd

from src.transformations import calculate_curve_steepness, calculate_drawdown, calculate_percentile_rank, calculate_spread, normalize_to_100


def test_normalize_to_100_sets_first_observation_to_100():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=2), "market": ["JKM", "JKM"], "price": [10, 12]})
    out = normalize_to_100(df)
    assert out["normalized"].tolist() == [100, 120]


def test_calculate_spread_returns_left_minus_right():
    dates = pd.date_range("2024-01-01", periods=2)
    df = pd.DataFrame({"date": list(dates) * 2, "market": ["A", "A", "B", "B"], "price": [5, 7, 2, 3]})
    out = calculate_spread(df, "A", "B")
    assert out["price"].tolist() == [3, 4]


def test_drawdown_is_zero_at_new_high():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3), "market": ["A"] * 3, "price": [10, 8, 12]})
    out = calculate_drawdown(df)
    assert out["drawdown_pct"].round(4).tolist() == [0, -20, 0]


def test_curve_steepness_uses_twelfth_month_minus_front():
    curves = pd.DataFrame(
        {
            "curve_date": [pd.Timestamp("2024-01-01")] * 12,
            "contract_month": pd.date_range("2024-02-01", periods=12, freq="MS"),
            "market": ["JKM"] * 12,
            "price": list(range(1, 13)),
        }
    )
    out = calculate_curve_steepness(curves)
    assert out.iloc[0]["steepness"] == 11


def test_percentile_rank_can_be_computed_before_date_filtering():
    dates = pd.date_range("2026-01-01", periods=300)
    df = pd.DataFrame({"date": dates, "market": ["JEPX_SYSTEM"] * 300, "price": range(300)})

    ranked = calculate_percentile_rank(df, window=252)
    selected_window = ranked[ranked["date"] >= pd.Timestamp("2026-10-01")]

    assert selected_window["percentile_rank"].notna().all()
