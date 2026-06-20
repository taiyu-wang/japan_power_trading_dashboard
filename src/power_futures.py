from __future__ import annotations

import pandas as pd


POWER_FUTURES_COLUMNS = [
    "curve_date",
    "contract_month",
    "area",
    "load_type",
    "settlement_price",
    "currency",
    "unit",
    "contract_type",
    "source",
    "source_note",
]
POWER_FUTURES_REQUIRED = {"curve_date", "contract_month", "area", "load_type", "settlement_price"}


def normalize_power_futures(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    missing = POWER_FUTURES_REQUIRED.difference(out.columns)
    if missing:
        raise ValueError(f"Missing required power futures columns: {', '.join(sorted(missing))}")
    if out.empty:
        raise ValueError("Power futures dataset is empty.")

    out["curve_date"] = pd.to_datetime(out["curve_date"], errors="coerce").dt.tz_localize(None)
    out["contract_month"] = pd.to_datetime(out["contract_month"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    out["area"] = out["area"].astype(str).str.strip().str.title()
    out["load_type"] = out["load_type"].astype(str).str.strip().str.title()
    out["settlement_price"] = pd.to_numeric(out["settlement_price"], errors="coerce")

    if out["curve_date"].isna().any() or out["contract_month"].isna().any():
        raise ValueError("Power futures data contains invalid curve_date or contract_month values.")
    if out["area"].eq("").any():
        raise ValueError("Power futures data contains blank area values.")
    if out["load_type"].eq("").any():
        raise ValueError("Power futures data contains blank load_type values.")
    if out["settlement_price"].isna().any():
        raise ValueError("Power futures data contains non-numeric or blank settlement_price values.")
    if (out["settlement_price"] <= 0).any():
        raise ValueError("Power futures data contains non-positive settlement_price values.")

    defaults = {
        "currency": "JPY",
        "unit": "kWh",
        "contract_type": "monthly_cash_settled_futures",
        "source": "uploaded_power_futures",
        "source_note": "User-uploaded monthly Japan electricity futures; verify JSCC/JPX/vendor source and settlement basis.",
    }
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default).astype(str).str.strip()

    out["product"] = out["area"] + " " + out["load_type"]
    return out[POWER_FUTURES_COLUMNS + ["product"]].sort_values(["area", "load_type", "curve_date", "contract_month"]).reset_index(drop=True)


def latest_power_futures_curve(df: pd.DataFrame) -> pd.DataFrame:
    fut = normalize_power_futures(df)
    latest_curve = fut.groupby(["area", "load_type"])["curve_date"].transform("max")
    return fut[fut["curve_date"].eq(latest_curve)].sort_values(["area", "load_type", "contract_month"]).reset_index(drop=True)


def power_futures_front_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    latest = latest_power_futures_curve(df)
    return latest.groupby(["area", "load_type"], as_index=False).head(1).sort_values(["area", "load_type"]).reset_index(drop=True)


def power_futures_peak_premium(df: pd.DataFrame) -> pd.DataFrame:
    latest = latest_power_futures_curve(df)
    wide = latest.pivot_table(index=["curve_date", "contract_month", "area"], columns="load_type", values="settlement_price", aggfunc="mean").reset_index()
    if not {"Peakload", "Baseload"}.issubset(wide.columns):
        return pd.DataFrame(columns=["curve_date", "contract_month", "area", "peak_premium"])
    wide["peak_premium"] = wide["Peakload"] - wide["Baseload"]
    return wide[["curve_date", "contract_month", "area", "peak_premium"]].sort_values(["area", "contract_month"]).reset_index(drop=True)


def power_futures_source_notes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "JPX electricity futures contract specifications",
                "status": "Public reference",
                "note": "Monthly East/West baseload and peakload electricity futures are cash-settled by JSCC against JEPX monthly area averages.",
                "url": "https://www.jpx.co.jp/english/derivatives/products/energy/electricity-futures/01.html",
            },
            {
                "source": "JPX daily data page",
                "status": "Public notice / paid data path",
                "note": "JPX states TOCOM electricity and LNG daily settlement CSV data is available through JSCC paid service from April 2025.",
                "url": "https://www.jpx.co.jp/english/markets/derivatives/reference/electricity/",
            },
            {
                "source": "JPX final settlement prices",
                "status": "Public final settlement reference",
                "note": "Useful for expired/final settlement reference; not a complete live forward curve.",
                "url": "https://www.jpx.co.jp/english/markets/derivatives/special-quotation/index.html",
            },
            {
                "source": "JEPX monthly spot averages",
                "status": "Underlying physical reference",
                "note": "JEPX monthly Tokyo/Kansai baseload and peakload averages are the physical settlement reference, not futures marks.",
                "url": "https://www.jepx.jp/electricpower/market-data/spot/ave_month.html",
            },
        ]
    )
