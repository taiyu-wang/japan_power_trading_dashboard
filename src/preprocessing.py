import numpy as np
import pandas as pd


def handle_missing_values(df: pd.DataFrame, group_col: str = "market") -> pd.DataFrame:
    out = df.sort_values([group_col, "date"]).copy()
    out["price"] = out.groupby(group_col)["price"].transform(lambda s: s.ffill().bfill())
    return out


def winsorize_outliers(df: pd.DataFrame, group_col: str = "market", lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    out = df.copy()
    def cap(s: pd.Series) -> pd.Series:
        lo, hi = s.quantile(lower), s.quantile(upper)
        return s.clip(lo, hi)
    out["price"] = out.groupby(group_col)["price"].transform(cap)
    return out


def convert_frequency(df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    rule_map = {"daily": "D", "weekly": "W-FRI", "monthly": "M", "quarterly": "Q"}
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


def prepare_historical(df: pd.DataFrame) -> pd.DataFrame:
    return add_calendar_columns(winsorize_outliers(handle_missing_values(df)))

