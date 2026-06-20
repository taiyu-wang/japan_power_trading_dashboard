import numpy as np
import pandas as pd

from .indicators import calculate_srmc_comparison, forward_curve_metrics, spread_suite
from .transformations import pivot_prices, rolling_volatility


POWER_MARKETS = ["JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI", "JEPX_INTRADAY"]
FUEL_MARKETS = ["JKM", "JCC_LINKED_LNG", "NEWCASTLE_COAL", "JCC", "BRENT", "USDJPY"]
CURVE_MARKETS = ["JKM", "DES_JAPAN_LNG", "JCC", "JCC_LINKED_LNG", "NEWCASTLE_COAL", "BRENT", "JAPAN_POWER_FUTURES"]


def _last_value(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.iloc[-1]) if not clean.empty else np.nan


def _pct_change(series: pd.Series, days: int) -> float:
    clean = series.dropna()
    if clean.empty:
        return np.nan
    lag = min(days + 1, len(clean))
    if lag <= 1:
        return np.nan
    base = clean.iloc[-lag]
    if base == 0 or pd.isna(base):
        return np.nan
    return float((clean.iloc[-1] / base - 1) * 100)


def _zscore(series: pd.Series, lookback: int = 90) -> float:
    clean = series.dropna().tail(lookback)
    if len(clean) < max(10, lookback // 3):
        return np.nan
    std = clean.std()
    if pd.isna(std) or std == 0:
        return np.nan
    return float((clean.iloc[-1] - clean.mean()) / std)


def _percentile_rank(series: pd.Series, lookback: int = 252) -> float:
    clean = series.dropna().tail(lookback)
    if clean.empty:
        return np.nan
    return float(clean.rank(pct=True).iloc[-1] * 100)


def _label_zscore(zscore: float, positive: str, negative: str, neutral: str = "Neutral") -> str:
    if pd.isna(zscore):
        return "Insufficient history"
    if zscore >= 1.0:
        return positive
    if zscore <= -1.0:
        return negative
    return neutral


def build_trader_snapshot(
    df: pd.DataFrame,
    curves: pd.DataFrame,
    gas_efficiency: float = 0.55,
    coal_efficiency: float = 0.40,
    gas_vom_jpy_mwh: float = 500.0,
    coal_vom_jpy_mwh: float = 700.0,
) -> dict[str, pd.DataFrame | list[str] | str | float]:
    prices = pivot_prices(df).ffill()
    srmc = calculate_srmc_comparison(
        df,
        gas_efficiency=gas_efficiency,
        coal_efficiency=coal_efficiency,
        gas_vom_jpy_mwh=gas_vom_jpy_mwh,
        coal_vom_jpy_mwh=coal_vom_jpy_mwh,
    ).reset_index(drop=True)
    snapshot = {
        "prices": prices,
        "srmc": srmc,
        "regime_cards": _market_regime(prices),
        "fuel_competitiveness": _fuel_competitiveness(srmc),
        "repricing": _power_repricing(srmc),
        "regional_basis": _regional_basis(df),
        "volatility": _volatility_table(df),
        "forward_context": _forward_context(curves),
    }
    snapshot["desk_commentary"] = _desk_commentary(snapshot)
    return snapshot


def _market_regime(prices: pd.DataFrame) -> pd.DataFrame:
    power = prices["JEPX_SYSTEM"] if "JEPX_SYSTEM" in prices else pd.Series(dtype=float)
    jkm = prices["JKM"] if "JKM" in prices else pd.Series(dtype=float)
    coal = prices["NEWCASTLE_COAL"] if "NEWCASTLE_COAL" in prices else pd.Series(dtype=float)

    power_30d = _pct_change(power, 30)
    jkm_30d = _pct_change(jkm, 30)
    coal_30d = _pct_change(coal, 30)
    vol_30d = power.pct_change().rolling(30).std().iloc[-1] * np.sqrt(252) * 100 if len(power.dropna()) >= 31 else np.nan
    vol_90d = power.pct_change().rolling(90).std().iloc[-1] * np.sqrt(252) * 100 if len(power.dropna()) >= 91 else np.nan
    vol_ratio = vol_30d / vol_90d if pd.notna(vol_30d) and pd.notna(vol_90d) and vol_90d else np.nan
    power_percentile = _percentile_rank(power, 252)

    if pd.notna(jkm_30d) and pd.notna(power_30d) and jkm_30d > 5 and power_30d < jkm_30d - 5:
        regime = "Fuel-led cost push"
    elif pd.notna(power_30d) and pd.notna(jkm_30d) and power_30d > jkm_30d + 5:
        regime = "Power-led tightness"
    elif pd.notna(power_30d) and pd.notna(jkm_30d) and power_30d < -5 and jkm_30d <= 0:
        regime = "Softening stack"
    elif pd.notna(vol_ratio) and vol_ratio >= 1.25:
        regime = "Volatility expansion"
    else:
        regime = "Range-bound repricing"

    stress_inputs = [
        min(100, max(0, power_percentile if pd.notna(power_percentile) else 50)),
        min(100, abs(power_30d) * 4 if pd.notna(power_30d) else 35),
        min(100, vol_ratio * 50 if pd.notna(vol_ratio) else 40),
        min(100, abs(jkm_30d) * 3 if pd.notna(jkm_30d) else 35),
    ]
    stress_score = float(np.nanmean(stress_inputs))

    return pd.DataFrame(
        [
            {"metric": "Market regime", "value": regime, "detail": "30d fuel/power momentum and volatility state"},
            {"metric": "JEPX system", "value": _last_value(power), "detail": f"{power_30d:.1f}% 30d" if pd.notna(power_30d) else "n/a"},
            {"metric": "JKM LNG", "value": _last_value(jkm), "detail": f"{jkm_30d:.1f}% 30d" if pd.notna(jkm_30d) else "n/a"},
            {"metric": "Newcastle coal", "value": _last_value(coal), "detail": f"{coal_30d:.1f}% 30d" if pd.notna(coal_30d) else "n/a"},
            {"metric": "Power vol ratio", "value": vol_ratio, "detail": "30d annualized vol / 90d annualized vol"},
            {"metric": "Stress score", "value": stress_score, "detail": "0-100 composite of level, momentum, and vol"},
        ]
    )


def _fuel_competitiveness(srmc: pd.DataFrame) -> pd.DataFrame:
    columns = ["fuel", "srmc_jpy_kwh", "margin_to_power", "premium_to_coal", "stance"]
    if srmc.empty:
        return pd.DataFrame(columns=columns)

    latest = srmc.sort_values("date").iloc[-1]
    coal = latest["coal_srmc"]
    jkm = latest["jkm_gas_srmc"]
    jcc_mid = (latest["jcc_11_srmc"] + latest["jcc_13_srmc"]) / 2
    power = latest["jepx_system"]
    fuel_values = {
        "Coal SRMC": coal,
        "JKM gas SRMC": jkm,
        "JCC-linked gas SRMC": jcc_mid,
    }
    cheapest = min(fuel_values, key=fuel_values.get)

    rows = []
    for fuel, value in fuel_values.items():
        premium = value - coal
        margin = power - value
        if fuel == cheapest:
            stance = "In merit"
        elif margin > 0:
            stance = "Covered by power"
        else:
            stance = "Out of merit"
        rows.append(
            {
                "fuel": fuel,
                "srmc_jpy_kwh": value,
                "margin_to_power": margin,
                "premium_to_coal": premium,
                "stance": stance,
            }
        )
    return pd.DataFrame(rows)


def _power_repricing(srmc: pd.DataFrame) -> pd.DataFrame:
    columns = ["market", "latest", "change_7d_pct", "change_30d_pct", "change_90d_pct", "zscore_90d"]
    if srmc.empty:
        return pd.DataFrame(columns=columns)
    series_map = {
        "JEPX system": srmc.set_index("date")["jepx_system"],
        "Coal SRMC": srmc.set_index("date")["coal_srmc"],
        "JKM gas SRMC": srmc.set_index("date")["jkm_gas_srmc"],
        "JCC 11-13% gas SRMC": srmc.set_index("date")[["jcc_11_srmc", "jcc_13_srmc"]].mean(axis=1),
    }
    rows = []
    for name, series in series_map.items():
        rows.append(
            {
                "market": name,
                "latest": _last_value(series),
                "change_7d_pct": _pct_change(series, 7),
                "change_30d_pct": _pct_change(series, 30),
                "change_90d_pct": _pct_change(series, 90),
                "zscore_90d": _zscore(series, 90),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _regional_basis(df: pd.DataFrame) -> pd.DataFrame:
    spreads = spread_suite(df)
    focus = {
        "Tokyo minus Kansai": ("Tokyo premium", "Kansai premium"),
        "Spot minus intraday": ("Spot premium", "Intraday premium"),
    }
    rows = []
    for name, labels in focus.items():
        subset = spreads[spreads["market"] == name].sort_values("date")
        if subset.empty:
            continue
        series = subset["price"]
        z = _zscore(series, 90)
        latest = _last_value(series)
        rows.append(
            {
                "basis": name,
                "latest": latest,
                "avg_20d": series.tail(20).mean(),
                "zscore_90d": z,
                "percentile_252d": _percentile_rank(series, 252),
                "stance": _label_zscore(z, labels[0], labels[1], "Balanced"),
            }
        )
    return pd.DataFrame(rows)


def _volatility_table(df: pd.DataFrame) -> pd.DataFrame:
    markets = [market for market in POWER_MARKETS + ["JKM", "NEWCASTLE_COAL"] if market in df["market"].unique()]
    subset = df[df["market"].isin(markets)]
    if subset.empty:
        return pd.DataFrame(columns=["market", "vol_30d", "vol_90d", "vol_ratio", "return_zscore"])
    vol30 = rolling_volatility(subset, 30).rename(columns={"vol_30d": "vol_30d"})
    vol90 = rolling_volatility(subset, 90).rename(columns={"vol_90d": "vol_90d"})
    latest30 = vol30.dropna().sort_values("date").groupby("market", as_index=False).tail(1)
    latest90 = vol90.dropna().sort_values("date").groupby("market", as_index=False).tail(1)
    out = latest30.merge(latest90, on=["date", "market"], how="outer")
    out["vol_ratio"] = out["vol_30d"] / out["vol_90d"]

    prices = pivot_prices(subset).ffill()
    zscores = []
    for market in markets:
        if market not in prices:
            continue
        returns = prices[market].pct_change() * 100
        zscores.append({"market": market, "return_zscore": _zscore(returns, 90)})
    out = out.merge(pd.DataFrame(zscores), on="market", how="left")
    return out[["market", "vol_30d", "vol_90d", "vol_ratio", "return_zscore"]].sort_values("vol_30d", ascending=False)


def _forward_context(curves: pd.DataFrame) -> pd.DataFrame:
    if curves.empty:
        return pd.DataFrame(columns=["market", "curve_date", "front_month", "quarterly_average", "calendar_average", "front_month_premium", "rolling_carry", "steepness", "structure"])
    metrics = forward_curve_metrics(curves[curves["market"].isin(CURVE_MARKETS)])
    if metrics.empty:
        metrics = _forward_context_from_available_tenors(curves[curves["market"].isin(CURVE_MARKETS)])
    elif "steepness" not in metrics.columns:
        fallback = _forward_context_from_available_tenors(curves[curves["market"].isin(CURVE_MARKETS)])
        metrics = metrics.merge(fallback[["market", "curve_date", "steepness"]], on=["market", "curve_date"], how="left")
    latest = metrics.sort_values("curve_date").groupby("market", as_index=False).tail(1).copy()
    if "steepness" not in latest.columns:
        latest["steepness"] = np.nan
    latest["structure"] = np.select(
        [latest["steepness"] > 0.5, latest["steepness"] < -0.5],
        ["Contango", "Backwardation"],
        default="Flat",
    )
    return latest.sort_values("market")


def _forward_context_from_available_tenors(curves: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (market, curve_date), group in curves.groupby(["market", "curve_date"]):
        ordered = group.sort_values("contract_month")
        if ordered.empty:
            continue
        front = ordered.iloc[0]["price"]
        q_avg = ordered.head(min(3, len(ordered)))["price"].mean()
        cal_avg = ordered.head(min(12, len(ordered)))["price"].mean()
        carry = ordered.iloc[1]["price"] - front if len(ordered) > 1 else np.nan
        back = ordered.iloc[-1]["price"]
        rows.append(
            {
                "market": market,
                "curve_date": curve_date,
                "front_month": front,
                "quarterly_average": q_avg,
                "calendar_average": cal_avg,
                "front_month_premium": front - q_avg,
                "rolling_carry": carry,
                "steepness": back - front,
            }
        )
    return pd.DataFrame(rows)


def _desk_commentary(snapshot: dict[str, pd.DataFrame | list[str] | str | float]) -> list[str]:
    comments = []
    regime = snapshot["regime_cards"]
    fuel = snapshot["fuel_competitiveness"]
    repricing = snapshot["repricing"]
    basis = snapshot["regional_basis"]
    vol = snapshot["volatility"]
    forward = snapshot["forward_context"]

    if isinstance(regime, pd.DataFrame) and not regime.empty:
        regime_name = regime.loc[regime["metric"] == "Market regime", "value"].iloc[0]
        stress = regime.loc[regime["metric"] == "Stress score", "value"].iloc[0]
        comments.append(f"{regime_name}: stress {stress:.0f}/100; watch fuel-power beta and realized vol.")

    if isinstance(fuel, pd.DataFrame) and not fuel.empty:
        leader = fuel.sort_values("srmc_jpy_kwh").iloc[0]
        laggard = fuel.sort_values("srmc_jpy_kwh").iloc[-1]
        comments.append(f"{leader['fuel']} is cheapest in the dispatch stack; {laggard['fuel']} screens {laggard['premium_to_coal']:.2f} JPY/kWh over coal.")

    if isinstance(repricing, pd.DataFrame) and not repricing.empty:
        power = repricing[repricing["market"] == "JEPX system"]
        gas = repricing[repricing["market"] == "JKM gas SRMC"]
        if not power.empty and not gas.empty:
            gap = gas.iloc[0]["change_30d_pct"] - power.iloc[0]["change_30d_pct"]
            if pd.notna(gap):
                if gap > 3:
                    comments.append(f"JEPX lagging gas SRMC by {gap:.1f} pts over 30d; repricing risk skewed higher.")
                elif gap < -3:
                    comments.append(f"JEPX has outrun gas SRMC by {abs(gap):.1f} pts over 30d; watch fade risk if demand softens.")
                else:
                    comments.append(f"JEPX is tracking gas SRMC within {abs(gap):.1f} pts over 30d.")

    if isinstance(basis, pd.DataFrame) and not basis.empty:
        stretched = basis.reindex(basis["zscore_90d"].abs().sort_values(ascending=False).index).iloc[0]
        comments.append(f"Regional basis watch: {stretched['basis']} is {stretched['stance'].lower()} at {stretched['zscore_90d']:.1f} z-score.")

    if isinstance(vol, pd.DataFrame) and not vol.empty:
        top = vol.iloc[0]
        comments.append(f"Volatility leadership is in {top['market']} with 30d annualized vol at {top['vol_30d']:.1f}%.")

    if isinstance(forward, pd.DataFrame) and not forward.empty:
        backwardated = forward[forward["structure"] == "Backwardation"]
        if not backwardated.empty:
            row = backwardated.iloc[0]
            comments.append(f"Forward curve context flags {row['market']} backwardation, consistent with prompt tightness.")
        else:
            row = forward.iloc[0]
            comments.append(f"Forward curves screen mostly {row['structure'].lower()}; check carry/roll before adding outright exposure.")

    return comments or ["Insufficient data in the selected window for a full trader read."]
