from __future__ import annotations

import pandas as pd


VERIFIED_SOURCES = {"public", "uploaded", "vendor"}
MARKET_LABELS = {
    "JKM": "JKM LNG", "JCC": "JCC crude", "BRENT": "Brent crude",
    "JCC_LINKED_LNG": "Oil-linked LNG", "DES_JAPAN_LNG": "DES Japan LNG",
    "NEWCASTLE_COAL": "Newcastle coal", "CFR_JAPAN_COAL": "CFR Japan coal",
    "JEPX_SYSTEM": "JEPX system", "JEPX_TOKYO": "Tokyo power",
    "JEPX_KANSAI": "Kansai power", "JEPX_INTRADAY": "JEPX intraday",
    "JAPAN_POWER_FUTURES": "Japan power futures", "USDJPY": "USD/JPY",
}


def japan_today() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Tokyo").normalize().tz_localize(None)


def eligible_history(df: pd.DataFrame, as_of=None, max_age_days: int = 4) -> pd.DataFrame:
    """Exclude demonstration data and dated-out inputs from current desk alerts."""
    if df.empty or "source_type" not in df:
        return df.iloc[:0].copy()
    cutoff = pd.Timestamp(as_of).normalize() if as_of is not None else japan_today()
    out = df[df["source_type"].isin(VERIFIED_SOURCES)].copy()
    allowance = pd.to_timedelta(out["market"].str.startswith("JEPX").astype(int), unit="D")
    out = out[out["date"].le(cutoff + allowance) & out["price"].notna()]
    latest = out.groupby("market")["date"].transform("max")
    return out[latest.ge(cutoff - pd.Timedelta(days=max_age_days))]


def aligned_changes(prices: pd.DataFrame, markets: list[str], days: int = 30) -> tuple[dict, pd.Timestamp | None]:
    if not set(markets).issubset(prices.columns):
        return {}, None
    common = prices[markets].dropna().sort_index()
    if common.empty:
        return {}, None
    end = common.index[-1]
    target = end - pd.Timedelta(days=days)
    baseline = common.loc[common.index <= target]
    if baseline.empty or (target - baseline.index[-1]).days > 7:
        return {}, end
    values = (common.iloc[-1] / baseline.iloc[-1].replace(0, float("nan")) - 1) * 100
    return values.to_dict(), end


def bounded_prices(df: pd.DataFrame, limits: dict[str, int] | None = None) -> pd.DataFrame:
    """Carry marks only across short publication gaps; never back-fill history."""
    prices = df.pivot_table(index="date", columns="market", values="price", aggfunc="mean").sort_index()
    limits = limits or {"JCC": 45}
    for market in prices:
        observed = pd.Series(prices.index, index=prices.index).where(prices[market].notna()).ffill()
        age = (pd.Series(prices.index, index=prices.index) - observed).dt.days
        limit = limits.get(market, 0 if market.startswith("JEPX") else 4)
        prices[market] = prices[market].ffill().where(age.le(limit))
    return prices
