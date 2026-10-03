import numpy as np
import pandas as pd

from .transformations import calculate_curve_steepness, calculate_spread, pivot_prices
from .market_context import bounded_prices, japan_today


KCAL_TO_KJ = 4.1868
DEFAULT_COAL_MARKETS = ("CFR_JAPAN_COAL", "NEWCASTLE_COAL")


def coal_thermal_mwh_per_tonne(coal_kcal_kg: float = 6000.0) -> float:
    return coal_kcal_kg * 1000 * KCAL_TO_KJ / 3600 / 1000


def _select_coal_reference(prices: pd.DataFrame, coal_markets: tuple[str, ...] = DEFAULT_COAL_MARKETS) -> tuple[pd.Series | None, pd.Series | None]:
    selected = pd.Series(np.nan, index=prices.index, dtype=float)
    labels = pd.Series(None, index=prices.index, dtype=object)
    for market in coal_markets:
        if market in prices:
            mask = selected.isna() & prices[market].notna()
            selected.loc[mask] = prices.loc[mask, market]
            labels.loc[mask] = market
    return (selected, labels) if selected.notna().any() else (None, None)


def latest_snapshot(df: pd.DataFrame, as_of=None) -> pd.DataFrame:
    latest = df.sort_values("date").groupby("market", as_index=False).tail(1)
    candidates = df.merge(latest[["market", "date"]].rename(columns={"date": "quote_date"}), on="market")
    target = candidates["quote_date"] - pd.Timedelta(days=30)
    candidates = candidates[candidates["date"].le(target) & candidates["date"].ge(target - pd.Timedelta(days=7))]
    prev = candidates.sort_values("date").groupby("market", as_index=False).tail(1)[["market", "price"]].rename(columns={"price": "price_30d_ago"})
    out = latest.merge(prev, on="market", how="left")
    out["change_30d_pct"] = (out["price"] / out["price_30d_ago"] - 1) * 100
    current = pd.Timestamp(as_of).normalize() if as_of is not None else japan_today()
    out["age_days"] = (current - out["date"]).dt.days.clip(lower=0)
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
    if not 0 < gas_efficiency <= 1 or not 0 < coal_efficiency <= 1 or coal_kcal_kg <= 0:
        raise ValueError("Efficiencies must be in (0, 1] and coal heat content must be positive.")
    prices = bounded_prices(df)
    if prices.empty:
        return pd.DataFrame(columns=["date", "coal_srmc", "jkm_gas_srmc", "jcc_11_srmc", "jcc_13_srmc", "jepx_system", "coal_reference_market"])
    for market in ["JKM", "JCC", "USDJPY", "JEPX_SYSTEM"]:
        if market not in prices:
            prices[market] = np.nan
    coal_price, coal_reference_market = _select_coal_reference(prices, coal_markets)
    if coal_price is None:
        coal_price = pd.Series(np.nan, index=prices.index)

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
    ).dropna(subset=["jepx_system"], how="all")


def spread_suite(df: pd.DataFrame, **srmc_settings) -> pd.DataFrame:
    pairs = [
        ("JKM", "JCC_LINKED_LNG", "JKM minus JCC-linked LNG"),
        ("JEPX_TOKYO", "JEPX_KANSAI", "Tokyo minus Kansai"),
        ("JEPX_SYSTEM", "JEPX_INTRADAY", "Spot minus intraday"),
    ]
    frames = [calculate_spread(df, left, right, name) for left, right, name in pairs]
    for frame, (left, _, _) in zip(frames, pairs):
        frame["unit"] = "USD/MMBtu" if left == "JKM" else "JPY/kWh"
    srmc = calculate_srmc_comparison(df, **srmc_settings)
    if not srmc.empty:
        for name, left, right in [
            ("Gas minus coal SRMC", "jkm_gas_srmc", "coal_srmc"),
            ("Indicative gas margin", "jepx_system", "jkm_gas_srmc"),
            ("Indicative coal margin", "jepx_system", "coal_srmc"),
        ]:
            frames.append(pd.DataFrame({"date": srmc["date"], "market": name, "price": srmc[left] - srmc[right], "unit": "JPY/kWh"}))
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
    out = pd.DataFrame(rows, columns=["market", "curve_date", "front_month", "quarterly_average", "calendar_average", "front_month_premium", "rolling_carry"])
    if not steep.empty:
        out = out.merge(steep[["market", "curve_date", "steepness"]], on=["market", "curve_date"], how="left")
    return out


def detect_spikes(df: pd.DataFrame, market: str, z_threshold: float = 2.5) -> pd.DataFrame:
    subset = df[df["market"] == market].sort_values("date").copy()
    returns = subset["price"].pct_change()
    z = (returns - returns.rolling(60).mean()) / returns.rolling(60).std()
    subset["return_zscore"] = z
    return subset[subset["return_zscore"].abs() >= z_threshold]
