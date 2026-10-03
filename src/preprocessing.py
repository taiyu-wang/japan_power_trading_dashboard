import pandas as pd


def handle_missing_values(df: pd.DataFrame, group_col: str = "market", max_gap_days: int = 4) -> pd.DataFrame:
    out = df.sort_values([group_col, "date"]).copy()
    observed = out["date"].where(out["price"].notna()).groupby(out[group_col]).ffill()
    fillable = (out["date"] - observed).dt.days.le(max_gap_days)
    fillable &= ~out[group_col].astype(str).str.startswith("JEPX")
    out["price"] = out["price"].where(out["price"].notna() | ~fillable, out.groupby(group_col)["price"].ffill())
    return out


def winsorize_outliers(df: pd.DataFrame, group_col: str = "market", lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    out = df.copy()
    def cap(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile(lower), s.quantile(upper)
        return s.clip(lo, hi)
    out["price"] = out.groupby(group_col)["price"].transform(cap)
    return out


def convert_frequency(df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    rule_map = {"daily": "D", "weekly": "W-FRI", "monthly": "ME", "quarterly": "QE"}
    rule = rule_map.get(frequency.lower(), "D")
    if rule == "D":
        return df.copy()
    keys = ["market", "region", "asset_class", "currency", "unit"]
    return (
        df.set_index("date")
        .groupby(keys, dropna=False)["price"]
        .resample(rule)
        .mean()
        .reset_index()
        .assign(frequency=frequency.lower(), contract="spot")
    )


def add_calendar_columns(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    out["year"] = out[date_col].dt.year
    out["quarter"] = out[date_col].dt.quarter
    out["month"] = out[date_col].dt.month
    out["month_name"] = out[date_col].dt.month_name().str.slice(0, 3)
    out["week"] = out[date_col].dt.isocalendar().week.astype(int)
    out["weekday"] = out[date_col].dt.day_name()
    out["is_weekend"] = out[date_col].dt.weekday >= 5
    return out


def prepare_historical(df: pd.DataFrame, clean: bool = False) -> pd.DataFrame:
    out = df.sort_values(["market", "date"]).copy()
    if clean:
        out = winsorize_outliers(handle_missing_values(out))
    return add_calendar_columns(out)
