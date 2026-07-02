import numpy as np
import pandas as pd

from .transformations import calculate_curve_steepness, calculate_spread, pivot_prices


KCAL_TO_KJ = 4.1868
DEFAULT_COAL_MARKETS = ("CFR_JAPAN_COAL", "NEWCASTLE_COAL")


def coal_thermal_mwh_per_tonne(coal_kcal_kg: float = 6000.0) -> float:
    return coal_kcal_kg * 1000 * KCAL_TO_KJ / 3600 / 1000


def _select_coal_reference(prices: pd.DataFrame, coal_markets: tuple[str, ...] = DEFAULT_COAL_MARKETS) -> tuple[pd.Series | None, str | None]:
    for market in coal_markets:
        if market in prices.columns and prices[market].notna().any():
            return prices[market], market
    return None, None


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    latest = df.sort_values("date").groupby("market", as_index=False).tail(1)
    one_month_ago = df["date"].max() - pd.Timedelta(days=30)
    prev = (
        df[df["date"] <= one_month_ago]
        .sort_values("date")
        .groupby("market", as_index=False)
        .tail(1)[["market", "price"]]
        .rename(columns={"price": "price_30d_ago"})
    )
    out = latest.merge(prev, on="market", how="left")
    out["change_30d_pct"] = (out["price"] / out["price_30d_ago"] - 1) * 100
    return out


def daily_returns(df: pd.DataFrame) -> pd.DataFrame:
    prices = pivot_prices(df)
    returns = prices.pct_change() * 100
    return returns.reset_index().melt("date", var_name="market", value_name="return_pct").dropna()


def calculate_srmc_comparison(
    df: pd.DataFrame,
    gas_efficiency: float = 0.55,
    coal_efficiency: float = 0.40,
    coal_kcal_kg: float = 6000.0,
    coal_markets: tuple[str, ...] = DEFAULT_COAL_MARKETS,
    jcc_low_slope: float = 0.11,
    jcc_high_slope: float = 0.13,
    jcc_constant: float = 0.5,
    gas_vom_jpy_mwh: float = 500.0,
    coal_vom_jpy_mwh: float = 700.0,
) -> pd.DataFrame:
    prices = pivot_prices(df).ffill().bfill()
    required = ["JKM", "JCC", "USDJPY", "JEPX_SYSTEM"]
    missing = [market for market in required if market not in prices.columns]
    coal_price, coal_reference_market = _select_coal_reference(prices, coal_markets)
    if missing or coal_price is None:
        return pd.DataFrame(columns=["date", "coal_srmc", "jkm_gas_srmc", "jcc_11_srmc", "jcc_13_srmc", "jepx_system", "coal_reference_market"])

    heat_rate_mmbtu_mwh = 3.412 / gas_efficiency
    coal_energy_mwh_tonne = coal_thermal_mwh_per_tonne(coal_kcal_kg)

    jkm_gas_jpy_mwh = prices["JKM"] * prices["USDJPY"] * heat_rate_mmbtu_mwh + gas_vom_jpy_mwh
    jcc_11_lng = prices["JCC"] * jcc_low_slope + jcc_constant
    jcc_13_lng = prices["JCC"] * jcc_high_slope + jcc_constant
    jcc_11_jpy_mwh = jcc_11_lng * prices["USDJPY"] * heat_rate_mmbtu_mwh + gas_vom_jpy_mwh
    jcc_13_jpy_mwh = jcc_13_lng * prices["USDJPY"] * heat_rate_mmbtu_mwh + gas_vom_jpy_mwh
    coal_jpy_mwh = coal_price * prices["USDJPY"] / (coal_energy_mwh_tonne * coal_efficiency) + coal_vom_jpy_mwh

    return pd.DataFrame(
        {
            "date": prices.index,
            "coal_srmc": coal_jpy_mwh / 1000,
            "coal_reference_market": coal_reference_market,
            "coal_heat_content_kcal_kg": coal_kcal_kg,
            "coal_thermal_mwh_per_tonne": coal_energy_mwh_tonne,
            "jkm_gas_srmc": jkm_gas_jpy_mwh / 1000,
            "jcc_11_srmc": jcc_11_jpy_mwh / 1000,
            "jcc_13_srmc": jcc_13_jpy_mwh / 1000,
            "jepx_system": prices["JEPX_SYSTEM"],
        }
    ).dropna()


def spread_suite(df: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("JKM", "JCC_LINKED_LNG", "JKM minus JCC-linked LNG"),
        ("JKM", "NEWCASTLE_COAL", "LNG minus coal"),
        ("JEPX_TOKYO", "JEPX_KANSAI", "Tokyo minus Kansai"),
        ("JEPX_SYSTEM", "JEPX_INTRADAY", "Spot minus intraday"),
    ]
    frames = [calculate_spread(df, left, right, name) for left, right, name in pairs]
    prices = pivot_prices(df)
    fuel_cols = [c for c in ["JKM", "NEWCASTLE_COAL", "JCC_LINKED_LNG"] if c in prices]
    if fuel_cols and "JEPX_SYSTEM" in prices:
        basket = prices[fuel_cols].mean(axis=1)
        spread = prices["JEPX_SYSTEM"] - basket
        frames.append(pd.DataFrame({"date": spread.index, "market": "Power minus fuel basket", "price": spread.values}))
    return pd.concat(frames, ignore_index=True)


def forward_curve_metrics(curves: pd.DataFrame) -> pd.DataFrame:
    rows = []
    steep = calculate_curve_steepness(curves)
    for (market, curve_date), group in curves.groupby(["market", "curve_date"]):
        ordered = group.sort_values("contract_month")
        front = ordered.iloc[0]["price"]
        q_avg = ordered.head(3)["price"].mean()
        cal_avg = ordered.head(12)["price"].mean()
        carry = ordered.iloc[1]["price"] - front if len(ordered) > 1 else np.nan
        rows.append(
            {
                "market": market,
                "curve_date": curve_date,
                "front_month": front,
                "quarterly_average": q_avg,
                "calendar_average": cal_avg,
                "front_month_premium": front - q_avg,
                "rolling_carry": carry,
            }
        )
    out = pd.DataFrame(rows)
    if not steep.empty:
        out = out.merge(steep[["market", "curve_date", "steepness"]], on=["market", "curve_date"], how="left")
    return out


def detect_spikes(df: pd.DataFrame, market: str, z_threshold: float = 2.5) -> pd.DataFrame:
    subset = df[df["market"] == market].sort_values("date").copy()
    returns = subset["price"].pct_change()
    z = (returns - returns.rolling(60).mean()) / returns.rolling(60).std()
    subset["return_zscore"] = z
    return subset[subset["return_zscore"].abs() >= z_threshold]
