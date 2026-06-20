import numpy as np
import pandas as pd


def pivot_prices(df: pd.DataFrame, value_col: str = "price") -> pd.DataFrame:
    return df.pivot_table(index="date", columns="market", values=value_col, aggfunc="mean").sort_index()


def normalize_to_100(df: pd.DataFrame, group_col: str = "market", value_col: str = "price") -> pd.DataFrame:
    out = df.sort_values([group_col, "date"]).copy()
    first = out.groupby(group_col)[value_col].transform(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    out["normalized"] = out[value_col] / first * 100
    return out


def rolling_volatility(df: pd.DataFrame, window: int = 30, annualization: int = 252) -> pd.DataFrame:
    prices = pivot_prices(df)
    returns = prices.pct_change()
    vol = returns.rolling(window).std() * np.sqrt(annualization) * 100
    return vol.reset_index().melt("date", var_name="market", value_name=f"vol_{window}d")


def rolling_zscore(df: pd.DataFrame, window: int = 60, value_col: str = "price") -> pd.DataFrame:
    out = df.sort_values(["market", "date"]).copy()
    mean = out.groupby("market")[value_col].transform(lambda s: s.rolling(window).mean())
    std = out.groupby("market")[value_col].transform(lambda s: s.rolling(window).std())
    out["zscore"] = (out[value_col] - mean) / std
    return out


def calculate_spread(df: pd.DataFrame, left_market: str, right_market: str, spread_name: str | None = None) -> pd.DataFrame:
    prices = pivot_prices(df)
    if left_market not in prices or right_market not in prices:
        return pd.DataFrame(columns=["date", "market", "price", "left_market", "right_market"])
    spread = prices[left_market] - prices[right_market]
    return pd.DataFrame(
        {
            "date": spread.index,
            "market": spread_name or f"{left_market} - {right_market}",
            "price": spread.values,
            "left_market": left_market,
            "right_market": right_market,
        }
    )


def calculate_drawdown(df: pd.DataFrame) -> pd.DataFrame:
    prices = pivot_prices(df)
    running_max = prices.cummax()
    drawdown = prices / running_max - 1
    return drawdown.mul(100).reset_index().melt("date", var_name="market", value_name="drawdown_pct")


def calculate_correlation_matrix(df: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    prices = pivot_prices(df)
    returns = prices.pct_change().dropna(how="all")
    return returns.corr(method=method)


def calculate_percentile_rank(df: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    out = df.sort_values(["market", "date"]).copy()
    def pct_rank(s: pd.Series) -> pd.Series:
        return s.rolling(window).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False)
    out["percentile_rank"] = out.groupby("market")["price"].transform(pct_rank)
    return out


def calculate_curve_steepness(curve_df: pd.DataFrame, front_n: int = 1, back_n: int = 12) -> pd.DataFrame:
    rows = []
    for (market, curve_date), group in curve_df.groupby(["market", "curve_date"]):
        ordered = group.sort_values("contract_month")
        if len(ordered) >= back_n:
            front = ordered.head(front_n)["price"].mean()
            back = ordered.iloc[back_n - 1]["price"]
            rows.append({"market": market, "curve_date": curve_date, "front_price": front, "back_price": back, "steepness": back - front})
    return pd.DataFrame(rows)


def month_on_month_curve_shift(curve_df: pd.DataFrame) -> pd.DataFrame:
    out = curve_df.sort_values(["market", "contract_month", "curve_date"]).copy()
    out["prior_price"] = out.groupby(["market", "contract_month"])["price"].shift(1)
    out["shift"] = out["price"] - out["prior_price"]
    return out

