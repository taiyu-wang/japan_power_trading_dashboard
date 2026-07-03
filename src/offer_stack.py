from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from .http_client import get_session


JEPX_BASE_URL = "https://www.jepx.jp"
JEPX_FETCH_MAX_WORKERS = 5
JEPX_BID_CURVE_DIR = "spot_bid_curves"
JEPX_AREA_DIR = "spot_splitting_areas"
JEPX_DATE_URL = f"{JEPX_BASE_URL}/js/get_graph_date.php?dir={JEPX_BID_CURVE_DIR}"
JEPX_SOURCE = "JEPX day-ahead bidding curve"
JEPX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{JEPX_BASE_URL}/en/electricpower/market-data/spot/bid_curves.html",
}

JEPX_OFFER_STACK_COLUMNS = [
    "delivery_date",
    "time_code",
    "area_group_code",
    "area_group",
    "bid_price_jpy_kwh",
    "sell_cumulative_mw",
    "buy_cumulative_mw",
    "source",
    "source_url",
    "downloaded_at",
]

DEFAULT_COMPACT_PRICE_LEVELS = (
    0,
    1,
    5,
    10,
    15,
    20,
    25,
    30,
    40,
    50,
    75,
    100,
    150,
    200,
    300,
    500,
    800,
    1000,
)

JEPX_BID_CURVE_RENAME = {
    "電力受渡日": "delivery_date",
    "商品コード": "time_code",
    "入札価格(円/kWh)": "bid_price_jpy_kwh",
    "売入札量累積(MW)": "sell_cumulative_mw",
    "買入札量累積(MW)": "buy_cumulative_mw",
    "分断エリア連番": "area_group_code",
}

JEPX_AREA_RENAME = {
    "電力受渡日": "delivery_date",
    "商品コード": "time_code",
    "エリアグループ": "area_group",
    "分断エリア連番": "area_group_code",
}

AREA_TRANSLATIONS = {
    "システムプライス": "System Price",
    "北海道": "Hokkaido",
    "東北": "Tohoku",
    "東京": "Tokyo",
    "中部": "Chubu",
    "北陸": "Hokuriku",
    "関西": "Kansai",
    "中国": "Chugoku",
    "四国": "Shikoku",
    "九州": "Kyushu",
}


@dataclass(frozen=True)
class AvailableOfferStackDates:
    oldest: pd.Timestamp
    latest: pd.Timestamp


def _jepx_date(value) -> pd.Timestamp:
    return pd.to_datetime(str(value), format="%Y%m%d", errors="coerce")


def _clean_area_group_code(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.replace(".0", "", regex=False).str.strip()


def _translate_area_group(value: str) -> str:
    text = str(value).strip()
    if not text:
        return "System Price"
    parts = [AREA_TRANSLATIONS.get(part, part) for part in text.split("・")]
    return " / ".join(parts)


def _jepx_csv_url(directory: str, delivery_date: pd.Timestamp) -> str:
    date_label = pd.Timestamp(delivery_date).strftime("%Y%m%d")
    return f"{JEPX_BASE_URL}/js/csv_read.php?dir={directory}&file={directory}_{date_label}.csv"


def parse_jepx_available_offer_stack_dates(text: str) -> AvailableOfferStackDates:
    parts = [part.strip() for part in str(text).split(",") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"Could not parse JEPX offer-stack availability response: {text!r}")
    latest = _jepx_date(parts[0])
    oldest = _jepx_date(parts[1])
    if pd.isna(latest) or pd.isna(oldest):
        raise ValueError(f"JEPX offer-stack availability contains invalid dates: {text!r}")
    return AvailableOfferStackDates(oldest=oldest, latest=latest)


def fetch_jepx_offer_stack_available_dates(timeout: int = 20) -> AvailableOfferStackDates:
    response = get_session().get(JEPX_DATE_URL, headers=JEPX_HEADERS, timeout=timeout)
    response.raise_for_status()
    return parse_jepx_available_offer_stack_dates(response.text)


def _read_jepx_csv(url: str, timeout: int = 20) -> pd.DataFrame:
    response = get_session().get(url, headers=JEPX_HEADERS, timeout=timeout)
    response.raise_for_status()
    if not response.text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(response.text))


def normalize_jepx_offer_stack(
    bid_curve: pd.DataFrame,
    area_mapping: pd.DataFrame | None = None,
    source_url: str = "",
) -> pd.DataFrame:
    if bid_curve.empty:
        return pd.DataFrame(columns=JEPX_OFFER_STACK_COLUMNS)

    out = bid_curve.rename(columns=JEPX_BID_CURVE_RENAME).copy()
    required = set(JEPX_BID_CURVE_RENAME.values())
    missing = sorted(required.difference(out.columns))
    if missing:
        raise ValueError(f"JEPX offer-stack data is missing required columns: {', '.join(missing)}")

    out["delivery_date"] = out["delivery_date"].map(_jepx_date)
    out["time_code"] = pd.to_numeric(out["time_code"], errors="coerce").astype("Int64")
    out["area_group_code"] = _clean_area_group_code(out["area_group_code"])
    for col in ["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if area_mapping is not None and not area_mapping.empty:
        areas = area_mapping.rename(columns=JEPX_AREA_RENAME).copy()
        areas["delivery_date"] = areas["delivery_date"].map(_jepx_date)
        areas["time_code"] = pd.to_numeric(areas["time_code"], errors="coerce").astype("Int64")
        areas["area_group_code"] = _clean_area_group_code(areas["area_group_code"])
        areas["area_group"] = areas["area_group"].map(_translate_area_group)
        areas = areas[["delivery_date", "time_code", "area_group_code", "area_group"]].drop_duplicates()
        out = out.merge(areas, on=["delivery_date", "time_code", "area_group_code"], how="left")
    else:
        out["area_group"] = ""

    out["area_group"] = out["area_group"].fillna("System Price").map(_translate_area_group)
    out["source"] = JEPX_SOURCE
    out["source_url"] = source_url
    out["downloaded_at"] = pd.Timestamp.now(tz="UTC").tz_convert(None).floor("s")
    out = out.dropna(subset=["delivery_date", "time_code", "bid_price_jpy_kwh"])
    out["time_code"] = out["time_code"].astype(int)
    return out[JEPX_OFFER_STACK_COLUMNS].sort_values(
        ["delivery_date", "time_code", "area_group_code", "bid_price_jpy_kwh", "sell_cumulative_mw"]
    ).reset_index(drop=True)


def normalize_jepx_offer_stack_upload(df: pd.DataFrame) -> pd.DataFrame:
    if set(JEPX_BID_CURVE_RENAME).issubset(df.columns):
        return normalize_jepx_offer_stack(df)

    missing = sorted(set(JEPX_OFFER_STACK_COLUMNS).difference(df.columns))
    if missing:
        raise ValueError(f"JEPX offer-stack upload is missing required columns: {', '.join(missing)}")

    out = df[JEPX_OFFER_STACK_COLUMNS].copy()
    out["delivery_date"] = pd.to_datetime(out["delivery_date"], errors="coerce").dt.tz_localize(None)
    out["downloaded_at"] = pd.to_datetime(out["downloaded_at"], errors="coerce").dt.tz_localize(None)
    out["time_code"] = pd.to_numeric(out["time_code"], errors="coerce").astype("Int64")
    out["area_group_code"] = _clean_area_group_code(out["area_group_code"])
    out["area_group"] = out["area_group"].fillna("System Price").astype(str).str.strip()
    for col in ["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["source"] = out["source"].fillna(JEPX_SOURCE).astype(str)
    out["source_url"] = out["source_url"].fillna("").astype(str)
    out = out.dropna(subset=["delivery_date", "time_code", "bid_price_jpy_kwh"])
    out["time_code"] = out["time_code"].astype(int)
    return out.sort_values(
        ["delivery_date", "time_code", "area_group_code", "bid_price_jpy_kwh", "sell_cumulative_mw"]
    ).reset_index(drop=True)


def prepare_offer_stack_curve(
    df: pd.DataFrame,
    delivery_date,
    time_code: int,
    area_group: str = "System Price",
) -> pd.DataFrame:
    if df.empty:
        curve = pd.DataFrame(columns=["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw", "net_supply_mw"])
        curve.attrs["clearing_price_estimate"] = pd.NA
        return curve

    target_date = pd.Timestamp(delivery_date).normalize()
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    mask = (
        work["delivery_date"].eq(target_date)
        & pd.to_numeric(work["time_code"], errors="coerce").eq(int(time_code))
        & work["area_group"].astype(str).eq(area_group)
    )
    curve = work.loc[mask, ["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]].copy()
    if curve.empty:
        curve.attrs["clearing_price_estimate"] = pd.NA
        return curve

    for col in ["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]:
        curve[col] = pd.to_numeric(curve[col], errors="coerce")
    curve = curve.dropna().sort_values("bid_price_jpy_kwh").drop_duplicates("bid_price_jpy_kwh", keep="last")
    curve["net_supply_mw"] = curve["sell_cumulative_mw"] - curve["buy_cumulative_mw"]
    if curve.empty:
        curve.attrs["clearing_price_estimate"] = pd.NA
        return curve

    crossing_idx = curve["net_supply_mw"].abs().idxmin()
    curve.attrs["clearing_price_estimate"] = float(curve.loc[crossing_idx, "bid_price_jpy_kwh"])
    return curve.reset_index(drop=True)


def _nearest_price_index(prices: np.ndarray, target: float) -> int:
    """Positional index of the price nearest to ``target`` on a sorted price array.

    Matches ``(series - target).abs().idxmin()`` exactly, including first-occurrence
    tie-breaking when ``target`` is equidistant from two prices or the nearest price
    is duplicated, while replacing the full-array scan with a binary search.
    """
    position = int(np.searchsorted(prices, target, side="left"))
    if position >= len(prices):
        position = len(prices) - 1
    elif position > 0 and (target - prices[position - 1]) <= (prices[position] - target):
        position -= 1
    return int(np.searchsorted(prices, prices[position], side="left"))


def _price_at_net_supply_arrays(prices: np.ndarray, net_supply: np.ndarray, target_net_supply_mw: float) -> float:
    if len(prices) == 0:
        return float("nan")
    if target_net_supply_mw > 0:
        at_or_above = net_supply >= target_net_supply_mw
        if at_or_above.any():
            return float(prices[int(np.argmax(at_or_above))])
    elif target_net_supply_mw < 0:
        at_or_below = net_supply <= target_net_supply_mw
        if at_or_below.any():
            return float(prices[len(net_supply) - 1 - int(np.argmax(at_or_below[::-1]))])
    return float(prices[int(np.argmin(np.abs(net_supply - target_net_supply_mw)))])


def _price_at_net_supply(curve: pd.DataFrame, target_net_supply_mw: float) -> float:
    if curve.empty:
        return float("nan")
    return _price_at_net_supply_arrays(
        curve["bid_price_jpy_kwh"].to_numpy(dtype=float),
        curve["net_supply_mw"].to_numpy(dtype=float),
        float(target_net_supply_mw),
    )


def _stack_regime(upside_depth_mw: float, downside_depth_mw: float) -> str:
    if pd.isna(upside_depth_mw) or pd.isna(downside_depth_mw):
        return "Insufficient curve"
    tight = min(upside_depth_mw, downside_depth_mw)
    if upside_depth_mw < 500:
        return "Scarcity stack"
    if downside_depth_mw < 500:
        return "Solar compression stack"
    if tight < 1500:
        return "Thin stack"
    return "Balanced stack"


def calculate_offer_stack_depth(df: pd.DataFrame, price_band: float = 5.0) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Offer-stack depth calculation is missing required columns: {', '.join(missing)}")

    rows: list[dict] = []
    group_cols = ["delivery_date", "time_code", "area_group"]
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    for (delivery_date, time_code, area_group), group in work.groupby(group_cols, dropna=False):
        curve = prepare_offer_stack_curve(group, delivery_date, int(time_code), str(area_group))
        clearing = curve.attrs.get("clearing_price_estimate", pd.NA)
        if curve.empty or pd.isna(clearing):
            continue
        prices = curve["bid_price_jpy_kwh"].to_numpy(dtype=float)
        net_supply = curve["net_supply_mw"].to_numpy(dtype=float)
        at_clear = net_supply[_nearest_price_index(prices, float(clearing))]
        up_price = float(clearing) + float(price_band)
        down_price = float(clearing) - float(price_band)
        up_net = net_supply[_nearest_price_index(prices, up_price)]
        down_net = net_supply[_nearest_price_index(prices, down_price)]
        upside_depth = abs(float(up_net) - float(at_clear))
        downside_depth = abs(float(at_clear) - float(down_net))
        rows.append(
            {
                "delivery_date": delivery_date,
                "time_code": int(time_code),
                "area_group": str(area_group),
                "clearing_price_estimate": float(clearing),
                "upside_depth_mw": upside_depth,
                "downside_depth_mw": downside_depth,
                "tightest_depth_mw": min(upside_depth, downside_depth),
                "price_band_jpy_kwh": float(price_band),
                "stack_regime": _stack_regime(upside_depth, downside_depth),
            }
        )
    return pd.DataFrame(rows).sort_values(["delivery_date", "time_code", "area_group"]).reset_index(drop=True)


def calculate_offer_stack_scenarios(
    df: pd.DataFrame,
    demand_shifts_mw: tuple[int, ...] = (-1000, -500, 500, 1000),
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Offer-stack depth calculation is missing required columns: {', '.join(missing)}")

    rows: list[dict] = []
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    for (delivery_date, time_code, area_group), group in work.groupby(["delivery_date", "time_code", "area_group"], dropna=False):
        curve = prepare_offer_stack_curve(group, delivery_date, int(time_code), str(area_group))
        clearing = curve.attrs.get("clearing_price_estimate", pd.NA)
        if curve.empty or pd.isna(clearing):
            continue
        prices = curve["bid_price_jpy_kwh"].to_numpy(dtype=float)
        net_supply = curve["net_supply_mw"].to_numpy(dtype=float)
        base_price = float(clearing)
        for shift in demand_shifts_mw:
            scenario_price = _price_at_net_supply_arrays(prices, net_supply, float(shift))
            rows.append(
                {
                    "delivery_date": delivery_date,
                    "time_code": int(time_code),
                    "area_group": str(area_group),
                    "base_price_jpy_kwh": base_price,
                    "demand_shift_mw": int(shift),
                    "scenario_price_jpy_kwh": scenario_price,
                    "price_impact_jpy_kwh": scenario_price - base_price,
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["delivery_date", "time_code", "area_group", "demand_shift_mw"]).reset_index(drop=True)


def _shock_column_suffix(shock_mw: float) -> str:
    direction = "up" if shock_mw > 0 else "down"
    return f"{direction}_{abs(int(shock_mw))}mw"


def calculate_offer_stack_price_sensitivity(
    df: pd.DataFrame,
    shocks_mw: tuple[int, ...] = (-1000, -500, 500, 1000),
    reference_prices: tuple[float, ...] | None = None,
) -> pd.DataFrame:
    """Estimate price response to +/- MW shocks at clearing or selected curve levels."""
    if df.empty:
        return pd.DataFrame()
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Offer-stack price sensitivity is missing required columns: {', '.join(missing)}")

    rows: list[dict] = []
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    for (delivery_date, time_code, area_group), group in work.groupby(["delivery_date", "time_code", "area_group"], dropna=False):
        curve = prepare_offer_stack_curve(group, delivery_date, int(time_code), str(area_group))
        if curve.empty:
            continue

        clearing = curve.attrs.get("clearing_price_estimate", pd.NA)
        anchors: list[tuple[str, float]] = []
        if reference_prices is None:
            if pd.isna(clearing):
                continue
            anchors.append(("clearing", float(clearing)))
        else:
            anchors.extend((f"price_{float(price):g}", float(price)) for price in reference_prices)

        prices = curve["bid_price_jpy_kwh"].to_numpy(dtype=float)
        net_supply = curve["net_supply_mw"].to_numpy(dtype=float)
        for reference_level, reference_price in anchors:
            reference_idx = _nearest_price_index(prices, float(reference_price))
            base_price = float(prices[reference_idx])
            base_net = float(net_supply[reference_idx])
            for shock in shocks_mw:
                scenario_price = _price_at_net_supply_arrays(prices, net_supply, base_net + float(shock))
                impact = scenario_price - base_price
                rows.append(
                    {
                        "delivery_date": delivery_date,
                        "time_code": int(time_code),
                        "area_group": str(area_group),
                        "reference_level": reference_level,
                        "reference_price_jpy_kwh": base_price,
                        "reference_net_supply_mw": base_net,
                        "shock_mw": int(shock),
                        "scenario_net_supply_mw": base_net + float(shock),
                        "scenario_price_jpy_kwh": scenario_price,
                        "price_impact_jpy_kwh": impact,
                        "sensitivity_jpy_kwh_per_100mw": impact / (abs(float(shock)) / 100.0) if shock else float("nan"),
                    }
                )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["delivery_date", "time_code", "area_group", "reference_level", "shock_mw"]
    ).reset_index(drop=True)


def calculate_offer_stack_shift(
    df: pd.DataFrame,
    prior_date,
    current_date,
    time_code: int,
    area_group: str = "System Price",
) -> pd.DataFrame:
    prior_curve = prepare_offer_stack_curve(df, prior_date, time_code, area_group)
    current_curve = prepare_offer_stack_curve(df, current_date, time_code, area_group)
    if prior_curve.empty or current_curve.empty:
        shift = pd.DataFrame(
            columns=[
                "bid_price_jpy_kwh",
                "prior_sell_cumulative_mw",
                "current_sell_cumulative_mw",
                "sell_shift_mw",
                "prior_buy_cumulative_mw",
                "current_buy_cumulative_mw",
                "buy_shift_mw",
            ]
        )
        shift.attrs["summary"] = {}
        return shift

    prior = prior_curve[["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]].rename(
        columns={
            "sell_cumulative_mw": "prior_sell_cumulative_mw",
            "buy_cumulative_mw": "prior_buy_cumulative_mw",
        }
    )
    current = current_curve[["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]].rename(
        columns={
            "sell_cumulative_mw": "current_sell_cumulative_mw",
            "buy_cumulative_mw": "current_buy_cumulative_mw",
        }
    )
    shift = current.merge(prior, on="bid_price_jpy_kwh", how="inner").sort_values("bid_price_jpy_kwh")
    shift["sell_shift_mw"] = shift["current_sell_cumulative_mw"] - shift["prior_sell_cumulative_mw"]
    shift["buy_shift_mw"] = shift["current_buy_cumulative_mw"] - shift["prior_buy_cumulative_mw"]

    clearing = current_curve.attrs.get("clearing_price_estimate")
    if shift.empty or clearing is None or pd.isna(clearing):
        summary = {}
    else:
        idx = (shift["bid_price_jpy_kwh"] - float(clearing)).abs().idxmin()
        summary = {
            "prior_date": pd.Timestamp(prior_date).normalize(),
            "current_date": pd.Timestamp(current_date).normalize(),
            "time_code": int(time_code),
            "area_group": area_group,
            "current_clearing_price_estimate": float(clearing),
            "sell_shift_at_clearing_mw": float(shift.loc[idx, "sell_shift_mw"]),
            "buy_shift_at_clearing_mw": float(shift.loc[idx, "buy_shift_mw"]),
            "net_depth_shift_at_clearing_mw": float(shift.loc[idx, "sell_shift_mw"] - shift.loc[idx, "buy_shift_mw"]),
        }
    shift.attrs["summary"] = summary
    return shift.reset_index(drop=True)


def offer_stack_time_period(time_code: int) -> str:
    hour = (int(time_code) - 1) / 2
    if hour < 6:
        return "Overnight"
    if hour < 14:
        return "Solar belly"
    if hour < 17:
        return "Afternoon ramp"
    if hour < 21:
        return "Evening peak"
    return "Late peak"


def _estimate_clearing_price_from_components(sell_curve: pd.DataFrame, buy_curve: pd.DataFrame) -> float:
    if sell_curve.empty or buy_curve.empty:
        return float("nan")
    sell = sell_curve[["bid_price_jpy_kwh", "sell_cumulative_mw"]].dropna().sort_values("bid_price_jpy_kwh")
    buy = buy_curve[["bid_price_jpy_kwh", "buy_cumulative_mw"]].dropna().sort_values("bid_price_jpy_kwh")
    if sell.empty or buy.empty:
        return float("nan")
    prices = np.array(sorted(set(sell["bid_price_jpy_kwh"]).union(set(buy["bid_price_jpy_kwh"]))), dtype=float)
    if len(prices) == 0:
        return float("nan")
    sell_depth = np.interp(prices, sell["bid_price_jpy_kwh"].to_numpy(dtype=float), sell["sell_cumulative_mw"].to_numpy(dtype=float))
    buy_depth = np.interp(prices, buy["bid_price_jpy_kwh"].to_numpy(dtype=float), buy["buy_cumulative_mw"].to_numpy(dtype=float))
    net = sell_depth - buy_depth
    return float(prices[np.nanargmin(np.abs(net))])


def _pressure_regime(net_tightening_pressure_mw: float) -> str:
    if pd.isna(net_tightening_pressure_mw):
        return "Unavailable"
    if net_tightening_pressure_mw > 500:
        return "Tighter"
    if net_tightening_pressure_mw < -500:
        return "Looser"
    return "Stable"


def calculate_offer_stack_period_shift(
    df: pd.DataFrame,
    prior_date,
    current_date,
    area_group: str = "System Price",
) -> pd.DataFrame:
    """Attribute aggregate offer-stack shifts by half-hour block and trader time period.

    Public JEPX data is aggregate. These metrics describe buy/sell curve movement,
    not participant-level behavior.
    """
    if df.empty:
        return pd.DataFrame()
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Offer-stack period shift is missing required columns: {', '.join(missing)}")

    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    prior = pd.Timestamp(prior_date).normalize()
    current = pd.Timestamp(current_date).normalize()
    area_work = work[work["area_group"].astype(str).eq(area_group)].copy()
    if area_work.empty:
        return pd.DataFrame()
    prior_codes = set(pd.to_numeric(area_work.loc[area_work["delivery_date"].eq(prior), "time_code"], errors="coerce").dropna().astype(int))
    current_codes = set(pd.to_numeric(area_work.loc[area_work["delivery_date"].eq(current), "time_code"], errors="coerce").dropna().astype(int))
    time_codes = sorted(prior_codes.intersection(current_codes))
    rows: list[dict] = []
    for time_code in time_codes:
        prior_curve = prepare_offer_stack_curve(area_work, prior, int(time_code), area_group)
        current_curve = prepare_offer_stack_curve(area_work, current, int(time_code), area_group)
        if prior_curve.empty or current_curve.empty:
            continue
        shift = calculate_offer_stack_shift(area_work, prior, current, int(time_code), area_group)
        summary = shift.attrs.get("summary", {})
        if not summary:
            continue

        prior_price = _estimate_clearing_price_from_components(prior_curve, prior_curve)
        supply_only_price = _estimate_clearing_price_from_components(current_curve, prior_curve)
        demand_only_price = _estimate_clearing_price_from_components(prior_curve, current_curve)
        current_price = _estimate_clearing_price_from_components(current_curve, current_curve)
        supply_contribution = supply_only_price - prior_price
        demand_contribution = demand_only_price - prior_price
        price_change = current_price - prior_price
        interaction = price_change - supply_contribution - demand_contribution
        sell_shift = float(summary["sell_shift_at_clearing_mw"])
        buy_shift = float(summary["buy_shift_at_clearing_mw"])
        net_depth_shift = float(summary["net_depth_shift_at_clearing_mw"])
        net_pressure = buy_shift - sell_shift
        rows.append(
            {
                "prior_date": prior,
                "current_date": current,
                "time_code": int(time_code),
                "delivery_period": offer_stack_time_period(int(time_code)),
                "area_group": area_group,
                "prior_clearing_price_estimate": prior_price,
                "current_clearing_price_estimate": current_price,
                "price_change_jpy_kwh": price_change,
                "supply_price_contribution_jpy_kwh": supply_contribution,
                "demand_price_contribution_jpy_kwh": demand_contribution,
                "interaction_jpy_kwh": interaction,
                "sell_shift_at_clearing_mw": sell_shift,
                "buy_shift_at_clearing_mw": buy_shift,
                "net_depth_shift_at_clearing_mw": net_depth_shift,
                "supply_tightening_mw": -sell_shift,
                "demand_strength_mw": buy_shift,
                "net_tightening_pressure_mw": net_pressure,
                "pressure_regime": _pressure_regime(net_pressure),
            }
        )
    if not rows:
        return pd.DataFrame()
    period_order = {"Overnight": 0, "Solar belly": 1, "Afternoon ramp": 2, "Evening peak": 3, "Late peak": 4}
    out = pd.DataFrame(rows)
    out["_period_order"] = out["delivery_period"].map(period_order)
    return out.sort_values(["_period_order", "time_code"]).drop(columns="_period_order").reset_index(drop=True)


def _average_offer_stack_curve(
    df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    time_code: int,
    area_group: str,
) -> pd.DataFrame:
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    mask = (
        work["delivery_date"].between(start_date, end_date, inclusive="both")
        & pd.to_numeric(work["time_code"], errors="coerce").eq(int(time_code))
        & work["area_group"].astype(str).eq(area_group)
    )
    cols = ["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"]
    sample = work.loc[mask, cols].copy()
    if sample.empty:
        return pd.DataFrame(columns=cols + ["net_supply_mw"])
    for col in cols:
        sample[col] = pd.to_numeric(sample[col], errors="coerce")
    avg = sample.dropna().groupby("bid_price_jpy_kwh", as_index=False)[["sell_cumulative_mw", "buy_cumulative_mw"]].mean()
    avg["net_supply_mw"] = avg["sell_cumulative_mw"] - avg["buy_cumulative_mw"]
    return avg.sort_values("bid_price_jpy_kwh").reset_index(drop=True)


def calculate_offer_stack_shift_benchmarks(
    df: pd.DataFrame,
    current_date=None,
    time_code: int | None = None,
    area_group: str = "System Price",
    lookback_days: tuple[int, ...] = (7, 30),
    selected_start=None,
    selected_end=None,
) -> pd.DataFrame:
    """Compare the latest curve with rolling average and selected-period benchmark curves."""
    if df.empty:
        return pd.DataFrame()
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Offer-stack benchmark shift is missing required columns: {', '.join(missing)}")

    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    area_work = work[work["area_group"].astype(str).eq(area_group)].copy()
    if area_work.empty:
        return pd.DataFrame()
    current = pd.Timestamp(current_date).normalize() if current_date is not None else area_work["delivery_date"].max()
    if time_code is None:
        codes = area_work.loc[area_work["delivery_date"].eq(current), "time_code"]
        if codes.empty:
            return pd.DataFrame()
        time_code = int(pd.to_numeric(codes, errors="coerce").dropna().iloc[0])

    current_curve = prepare_offer_stack_curve(area_work, current, int(time_code), area_group)
    if current_curve.empty:
        return pd.DataFrame()
    current_curve = current_curve[["bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw", "net_supply_mw"]].rename(
        columns={
            "sell_cumulative_mw": "latest_sell_cumulative_mw",
            "buy_cumulative_mw": "latest_buy_cumulative_mw",
            "net_supply_mw": "latest_net_supply_mw",
        }
    )

    benchmark_specs: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    for days in lookback_days:
        start = current - pd.Timedelta(days=int(days))
        end = current - pd.Timedelta(days=1)
        benchmark_specs.append((f"{int(days)}d_avg", start, end))
    if selected_start is not None and selected_end is not None:
        benchmark_specs.append(("selected_avg", pd.Timestamp(selected_start).normalize(), pd.Timestamp(selected_end).normalize()))

    frames: list[pd.DataFrame] = []
    for label, start, end in benchmark_specs:
        benchmark = _average_offer_stack_curve(area_work, start, end, int(time_code), area_group)
        if benchmark.empty:
            continue
        benchmark = benchmark.rename(
            columns={
                "sell_cumulative_mw": "benchmark_sell_cumulative_mw",
                "buy_cumulative_mw": "benchmark_buy_cumulative_mw",
                "net_supply_mw": "benchmark_net_supply_mw",
            }
        )
        shift = current_curve.merge(benchmark, on="bid_price_jpy_kwh", how="inner")
        if shift.empty:
            continue
        shift["benchmark_label"] = label
        shift["benchmark_start_date"] = start
        shift["benchmark_end_date"] = end
        shift["current_date"] = current
        shift["time_code"] = int(time_code)
        shift["area_group"] = area_group
        shift["sell_shift_mw"] = shift["latest_sell_cumulative_mw"] - shift["benchmark_sell_cumulative_mw"]
        shift["buy_shift_mw"] = shift["latest_buy_cumulative_mw"] - shift["benchmark_buy_cumulative_mw"]
        shift["net_supply_shift_mw"] = shift["latest_net_supply_mw"] - shift["benchmark_net_supply_mw"]
        frames.append(shift)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["benchmark_label", "bid_price_jpy_kwh"]).reset_index(drop=True)


def _pick_area_depth(depth: pd.DataFrame, area_name: str) -> pd.DataFrame:
    area = depth["area_group"].astype(str).str.lower()
    exact = depth.loc[area.eq(area_name.lower())].copy()
    if not exact.empty:
        return exact
    return depth.loc[area.str.contains(area_name.lower(), regex=False)].copy()


def calculate_tokyo_kansai_stack_tightness_spread(df: pd.DataFrame, price_band: float = 5.0) -> pd.DataFrame:
    """Return Tokyo minus Kansai tightness when both area curves are available."""
    if df.empty:
        return pd.DataFrame()
    if {"tightest_depth_mw", "clearing_price_estimate", "price_band_jpy_kwh"}.issubset(df.columns):
        depth = df.copy()
    else:
        depth = calculate_offer_stack_depth(df, price_band=price_band)
    if depth.empty or "area_group" not in depth.columns:
        return pd.DataFrame()

    tokyo = _pick_area_depth(depth, "Tokyo")
    kansai = _pick_area_depth(depth, "Kansai")
    if tokyo.empty or kansai.empty:
        return pd.DataFrame()

    keys = ["delivery_date", "time_code", "price_band_jpy_kwh"]
    tokyo = tokyo[keys + ["clearing_price_estimate", "tightest_depth_mw", "stack_regime"]].rename(
        columns={
            "clearing_price_estimate": "tokyo_clearing_price_estimate",
            "tightest_depth_mw": "tokyo_tightest_depth_mw",
            "stack_regime": "tokyo_stack_regime",
        }
    )
    kansai = kansai[keys + ["clearing_price_estimate", "tightest_depth_mw", "stack_regime"]].rename(
        columns={
            "clearing_price_estimate": "kansai_clearing_price_estimate",
            "tightest_depth_mw": "kansai_tightest_depth_mw",
            "stack_regime": "kansai_stack_regime",
        }
    )
    spread = tokyo.merge(kansai, on=keys, how="inner")
    if spread.empty:
        return spread
    spread["tightness_spread_mw"] = spread["tokyo_tightest_depth_mw"] - spread["kansai_tightest_depth_mw"]
    spread["clearing_price_spread_jpy_kwh"] = (
        spread["tokyo_clearing_price_estimate"] - spread["kansai_clearing_price_estimate"]
    )
    spread["tighter_area"] = np.where(
        spread["tokyo_tightest_depth_mw"] < spread["kansai_tightest_depth_mw"],
        "Tokyo",
        np.where(spread["kansai_tightest_depth_mw"] < spread["tokyo_tightest_depth_mw"], "Kansai", "Even"),
    )
    return spread.sort_values(["delivery_date", "time_code", "price_band_jpy_kwh"]).reset_index(drop=True)


def build_offer_stack_signal_payload(
    df: pd.DataFrame,
    depth: pd.DataFrame | None = None,
    shocks_mw: tuple[int, ...] = (-1000, -500, 500, 1000),
    price_band: float = 5.0,
) -> pd.DataFrame:
    """Build stack-derived fields intended for later Trading_Signals joins."""
    if df.empty and (depth is None or depth.empty):
        return pd.DataFrame()

    depth_frame = depth.copy() if depth is not None else calculate_offer_stack_depth(df, price_band=price_band)
    if depth_frame.empty:
        return pd.DataFrame()
    base = depth_frame.copy()
    base["delivery_date"] = pd.to_datetime(base["delivery_date"], errors="coerce").dt.normalize()
    base = base.rename(
        columns={
            "clearing_price_estimate": "stack_clearing_price_estimate",
            "upside_depth_mw": "stack_upside_depth_mw",
            "downside_depth_mw": "stack_downside_depth_mw",
            "tightest_depth_mw": "stack_tightest_depth_mw",
            "price_band_jpy_kwh": "stack_price_band_jpy_kwh",
            "stack_regime": "stack_regime",
        }
    )

    if not df.empty:
        sensitivity = calculate_offer_stack_price_sensitivity(df, shocks_mw=shocks_mw)
    else:
        sensitivity = pd.DataFrame()
    if not sensitivity.empty:
        pivot = sensitivity[sensitivity["reference_level"].eq("clearing")].copy()
        pivot["impact_col"] = pivot["shock_mw"].map(lambda value: f"stack_price_impact_{_shock_column_suffix(value)}_jpy_kwh")
        impact = pivot.pivot_table(
            index=["delivery_date", "time_code", "area_group"],
            columns="impact_col",
            values="price_impact_jpy_kwh",
            aggfunc="first",
        ).reset_index()
        impact.columns.name = None
        base = base.merge(impact, on=["delivery_date", "time_code", "area_group"], how="left")

    up_cols = [col for col in base.columns if col.startswith("stack_price_impact_up_")]
    down_cols = [col for col in base.columns if col.startswith("stack_price_impact_down_")]
    if up_cols and down_cols:
        base["stack_up_down_asymmetry_jpy_kwh"] = base[up_cols].max(axis=1) + base[down_cols].min(axis=1)
    else:
        base["stack_up_down_asymmetry_jpy_kwh"] = np.nan

    keep = [
        col
        for col in base.columns
        if col in {"delivery_date", "time_code", "area_group"}
        or col.startswith("stack_")
    ]
    return base[keep].sort_values(["delivery_date", "time_code", "area_group"]).reset_index(drop=True)


def compact_offer_stack_curves(
    df: pd.DataFrame,
    price_levels: tuple[float, ...] = DEFAULT_COMPACT_PRICE_LEVELS,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "delivery_date",
                "time_code",
                "area_group",
                "bid_price_jpy_kwh",
                "sell_cumulative_mw",
                "buy_cumulative_mw",
                "net_supply_mw",
                "source",
            ]
        )
    required = {"delivery_date", "time_code", "area_group", "bid_price_jpy_kwh", "sell_cumulative_mw", "buy_cumulative_mw"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"Compact offer-stack curves are missing required columns: {', '.join(missing)}")

    rows: list[pd.DataFrame] = []
    work = df.copy()
    work["delivery_date"] = pd.to_datetime(work["delivery_date"], errors="coerce").dt.normalize()
    levels = np.array(sorted(float(level) for level in price_levels), dtype=float)
    for (delivery_date, time_code, area_group), group in work.groupby(["delivery_date", "time_code", "area_group"], dropna=False):
        curve = prepare_offer_stack_curve(group, delivery_date, int(time_code), str(area_group))
        if curve.empty:
            continue
        prices = curve["bid_price_jpy_kwh"].to_numpy(dtype=float)
        sell = curve["sell_cumulative_mw"].to_numpy(dtype=float)
        buy = curve["buy_cumulative_mw"].to_numpy(dtype=float)
        sampled = pd.DataFrame(
            {
                "delivery_date": delivery_date,
                "time_code": int(time_code),
                "area_group": str(area_group),
                "bid_price_jpy_kwh": levels,
                "sell_cumulative_mw": np.interp(levels, prices, sell),
                "buy_cumulative_mw": np.interp(levels, prices, buy),
            }
        )
        sampled["net_supply_mw"] = sampled["sell_cumulative_mw"] - sampled["buy_cumulative_mw"]
        sampled["source"] = "JEPX processed sampled bidding curve"
        rows.append(sampled)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(
        ["delivery_date", "time_code", "area_group", "bid_price_jpy_kwh"]
    ).reset_index(drop=True)


def generate_offer_stack_processed_artifacts(
    df: pd.DataFrame,
    price_bands: tuple[float, ...] = (5.0, 10.0, 20.0),
    price_levels: tuple[float, ...] = DEFAULT_COMPACT_PRICE_LEVELS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    depth_frames = [calculate_offer_stack_depth(df, price_band=band) for band in price_bands]
    depth = pd.concat([frame for frame in depth_frames if not frame.empty], ignore_index=True) if depth_frames else pd.DataFrame()
    compact = compact_offer_stack_curves(df, price_levels=price_levels)
    return depth, compact


def write_offer_stack_processed_artifacts(
    raw_path: str | Path,
    depth_path: str | Path,
    compact_curves_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(raw_path, parse_dates=["delivery_date"])
    depth, compact = generate_offer_stack_processed_artifacts(raw)
    depth_output = Path(depth_path)
    compact_output = Path(compact_curves_path)
    depth_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    depth.to_csv(depth_output, index=False)
    compact.to_csv(compact_output, index=False)
    return depth, compact


def fetch_jepx_offer_stack_for_date(delivery_date, timeout: int = 20) -> pd.DataFrame:
    date_value = pd.Timestamp(delivery_date)
    bid_url = _jepx_csv_url(JEPX_BID_CURVE_DIR, date_value)
    area_url = _jepx_csv_url(JEPX_AREA_DIR, date_value)
    bid_curve = _read_jepx_csv(bid_url, timeout=timeout)
    area_mapping = _read_jepx_csv(area_url, timeout=timeout)
    return normalize_jepx_offer_stack(bid_curve, area_mapping, source_url=bid_url)


def fetch_jepx_offer_stack_range(start_date, end_date, timeout: int = 20) -> pd.DataFrame:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    frames: list[pd.DataFrame] = []
    for delivery_date in pd.date_range(start, end, freq="D"):
        day = fetch_jepx_offer_stack_for_date(delivery_date, timeout=timeout)
        if not day.empty:
            frames.append(day)
    if not frames:
        return pd.DataFrame(columns=JEPX_OFFER_STACK_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def fetch_latest_month_jepx_offer_stack(days: int = 31, timeout: int = 20) -> pd.DataFrame:
    available = fetch_jepx_offer_stack_available_dates(timeout=timeout)
    start = max(available.oldest, available.latest - pd.Timedelta(days=days - 1))
    return fetch_jepx_offer_stack_range(start, available.latest, timeout=timeout)


def write_latest_month_jepx_offer_stack(output_path: str | Path, days: int = 31, timeout: int = 20) -> pd.DataFrame:
    data = fetch_latest_month_jepx_offer_stack(days=days, timeout=timeout)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(output, index=False)
    return data


def main() -> None:
    from .config import JEPX_OFFER_STACK_CURVES_COMPACT_PATH, JEPX_OFFER_STACK_DEPTH_PATH, JEPX_OFFER_STACK_LATEST_MONTH_PATH

    data = write_latest_month_jepx_offer_stack(JEPX_OFFER_STACK_LATEST_MONTH_PATH)
    depth, compact = write_offer_stack_processed_artifacts(
        JEPX_OFFER_STACK_LATEST_MONTH_PATH,
        JEPX_OFFER_STACK_DEPTH_PATH,
        JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
    )
    start = data["delivery_date"].min().date() if not data.empty else "n/a"
    end = data["delivery_date"].max().date() if not data.empty else "n/a"
    print(f"Wrote {len(data):,} JEPX offer-stack rows to {JEPX_OFFER_STACK_LATEST_MONTH_PATH}")
    print(f"Wrote {len(depth):,} compact depth rows to {JEPX_OFFER_STACK_DEPTH_PATH}")
    print(f"Wrote {len(compact):,} compact curve rows to {JEPX_OFFER_STACK_CURVES_COMPACT_PATH}")
    print(f"Coverage: {start} to {end}")


if __name__ == "__main__":
    main()
