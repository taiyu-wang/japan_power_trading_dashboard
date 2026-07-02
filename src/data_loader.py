from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from .config import (
    FORWARD_CURVES_PATH,
    HISTORICAL_DATA_PATH,
    JEPX_BASELOAD_PATH,
    JEPX_INTRADAY_PATH,
    JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
    JEPX_OFFER_STACK_DEPTH_PATH,
    JEPX_OFFER_STACK_LATEST_MONTH_PATH,
    MARKET_MAPPING_PATH,
    NEWS_EVENTS_PATH,
    PUBLISHED_ARTIFACTS,
    POWER_FUTURES_PATH,
    SUPPLY_MIX_DAILY_SHAPE_PATH,
    SUPPLY_MIX_MONTHLY_PATH,
    SUPPLY_MIX_PATH,
    SUPPLY_MIX_RESIDUAL_THERMAL_PATH,
    WEATHER_DATA_PATH,
)
from .live_forward_curves import fetch_live_forward_curves
from .news import fetch_public_power_news_with_diagnostics, normalize_news_events, sample_power_news
from .offer_stack import fetch_latest_month_jepx_offer_stack, normalize_jepx_offer_stack_upload
from .jepx_market_data import daily_jepx_intraday_prices, normalize_jepx_baseload, normalize_jepx_intraday
from .power_futures import normalize_power_futures
from .published_data import load_published_csv
from .supply_mix import normalize_generation_mix
from .weather import fetch_open_meteo_daily_temperatures, normalize_weather_data


HISTORICAL_COLUMNS = ["date", "market", "region", "asset_class", "frequency", "contract", "price", "currency", "unit"]
FORWARD_CURVE_COLUMNS = ["curve_date", "contract_month", "market", "region", "price", "currency", "unit"]
FORWARD_CURVE_REQUIRED = {"curve_date", "contract_month", "market", "price"}


@dataclass(frozen=True)
class DatasetDiagnostics:
    """Compact validation result safe to surface in Streamlit."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def _published_or_local_csv(
    *,
    path: str | Path,
    default_path: str | Path,
    artifact: str,
    parse_dates: tuple[str, ...] = (),
    use_published: bool | None = None,
) -> pd.DataFrame:
    prefer_published = Path(path) == Path(default_path) if use_published is None else use_published
    if prefer_published:
        try:
            return load_published_csv(artifact, parse_dates=parse_dates)
        except Exception:
            pass
    local_path = Path(path)
    if not local_path.exists():
        return pd.DataFrame()
    return pd.read_csv(local_path, parse_dates=list(parse_dates) or None)


def _overlay_market_history(base: pd.DataFrame, updates: list[pd.DataFrame]) -> pd.DataFrame:
    valid_updates = [frame.copy() for frame in updates if frame is not None and not frame.empty]
    if not valid_updates:
        return base
    replacement = pd.concat(valid_updates, ignore_index=True)
    replacement["date"] = pd.to_datetime(replacement["date"], errors="coerce").dt.tz_localize(None)
    replacement = replacement.dropna(subset=["date", "market", "price"]).drop_duplicates(
        ["date", "market"], keep="last"
    )
    replacement_keys = pd.MultiIndex.from_frame(replacement[["date", "market"]])
    base_keys = pd.MultiIndex.from_frame(base[["date", "market"]])
    retained = base.loc[~base_keys.isin(replacement_keys)].copy()
    return pd.concat([retained, replacement], ignore_index=True, sort=False)


@st.cache_data(ttl=900, show_spinner=False)
def load_historical_prices(
    path: str | Path = HISTORICAL_DATA_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    df["market"] = df["market"].astype(str)
    prefer_published = Path(path) == Path(HISTORICAL_DATA_PATH) if use_published is None else use_published
    if prefer_published:
        updates = []
        try:
            updates.append(
                load_published_csv(
                    PUBLISHED_ARTIFACTS["jepx_spot_daily"],
                    parse_dates=("date",),
                )
            )
        except Exception:
            pass
        try:
            published_intraday = load_published_csv(
                PUBLISHED_ARTIFACTS["jepx_intraday"],
                parse_dates=("delivery_date",),
            )
            updates.append(daily_jepx_intraday_prices(published_intraday))
        except Exception:
            pass
        df = _overlay_market_history(df, updates)
    return df.sort_values(["market", "date"]).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_forward_curves(path: str | Path = FORWARD_CURVES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["curve_date", "contract_month"])
    return df.sort_values(["market", "curve_date", "contract_month"]).reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def load_live_forward_curves() -> tuple[pd.DataFrame, list[str]]:
    result = fetch_live_forward_curves()
    return result.data.sort_values(["market", "curve_date", "contract_month"]).reset_index(drop=True), result.warnings


def get_forward_curves(use_live: bool = False) -> tuple[pd.DataFrame, list[str], str]:
    if not use_live:
        return load_forward_curves(), [], "Bundled fallback CSV"
    try:
        curves, warnings = load_live_forward_curves()
        return curves, warnings, "Live public sources"
    except Exception as exc:
        return load_forward_curves(), [f"Live forward curve fetch failed, using bundled CSV fallback: {exc}"], "Bundled fallback CSV"


@st.cache_data(show_spinner=False)
def load_market_mapping(path: str | Path = MARKET_MAPPING_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_weather_temperatures(path: str | Path = WEATHER_DATA_PATH) -> pd.DataFrame:
    return normalize_weather_data(pd.read_csv(path))


@st.cache_data(ttl=1800, show_spinner=False)
def load_live_weather_temperatures(start_date, end_date) -> pd.DataFrame:
    return fetch_open_meteo_daily_temperatures(start_date, end_date)


def get_weather_temperatures(use_live: bool = False, start_date=None, end_date=None) -> tuple[pd.DataFrame, list[str], str]:
    if not use_live:
        try:
            published = load_published_csv(
                PUBLISHED_ARTIFACTS["weather"],
                parse_dates=("date",),
            )
            return normalize_weather_data(published), [], "Scheduled Open-Meteo snapshot"
        except Exception:
            return load_weather_temperatures(), [], "Bundled sample weather CSV"
    try:
        if start_date is None or end_date is None:
            fallback = load_weather_temperatures()
            start_date = fallback["date"].min()
            end_date = fallback["date"].max()
        return load_live_weather_temperatures(start_date, end_date), [], "Open-Meteo Historical Weather API"
    except Exception as exc:
        return load_weather_temperatures(), [f"Live weather refresh failed, using bundled sample weather: {exc}"], "Bundled sample weather CSV"


@st.cache_data(show_spinner=False)
def load_generation_mix(path: str | Path = SUPPLY_MIX_PATH) -> pd.DataFrame:
    return normalize_generation_mix(pd.read_csv(path))


@st.cache_data(ttl=900, show_spinner=False)
def load_processed_generation_mix(
    path: str | Path = SUPPLY_MIX_MONTHLY_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    prefer_published = Path(path) == Path(SUPPLY_MIX_MONTHLY_PATH) if use_published is None else use_published
    if prefer_published:
        try:
            frame = normalize_generation_mix(
                load_published_csv(PUBLISHED_ARTIFACTS["supply_mix"], parse_dates=("month",))
            )
            frame.attrs["published"] = True
            return frame
        except Exception:
            pass
    if not Path(path).exists():
        return pd.DataFrame()
    frame = normalize_generation_mix(pd.read_csv(path))
    frame.attrs["published"] = False
    return frame


@st.cache_data(ttl=900, show_spinner=False)
def load_supply_mix_daily_shape(
    path: str | Path = SUPPLY_MIX_DAILY_SHAPE_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=SUPPLY_MIX_DAILY_SHAPE_PATH,
        artifact=PUBLISHED_ARTIFACTS["supply_mix_daily_shape"],
        parse_dates=("date",),
        use_published=use_published,
    )


@st.cache_data(ttl=900, show_spinner=False)
def load_supply_mix_residual_thermal(
    path: str | Path = SUPPLY_MIX_RESIDUAL_THERMAL_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=SUPPLY_MIX_RESIDUAL_THERMAL_PATH,
        artifact=PUBLISHED_ARTIFACTS["supply_mix_residual_thermal"],
        parse_dates=("month",),
        use_published=use_published,
    )


def get_generation_mix(use_processed: bool = True) -> tuple[pd.DataFrame, list[str], str]:
    if use_processed:
        processed = load_processed_generation_mix()
        if not processed.empty:
            source = (
                "Processed JapanesePower.org Tokyo/Kansai aggregates (scheduled)"
                if processed.attrs.get("published")
                else "Bundled processed JapanesePower.org Tokyo/Kansai aggregates"
            )
            return processed, [], source
        return load_generation_mix(), ["Processed public generation mix is unavailable; using bundled synthetic sample."], "Bundled synthetic regional generation mix"
    return load_generation_mix(), [], "Bundled synthetic regional generation mix"


def load_uploaded_generation_mix(uploaded_file) -> pd.DataFrame:
    return normalize_generation_mix(pd.read_csv(uploaded_file))


@st.cache_data(show_spinner=False)
def load_power_futures(path: str | Path = POWER_FUTURES_PATH) -> pd.DataFrame:
    return normalize_power_futures(pd.read_csv(path))


def load_uploaded_power_futures(uploaded_file) -> pd.DataFrame:
    return normalize_power_futures(pd.read_csv(uploaded_file))


@st.cache_data(show_spinner=False)
def load_power_news(path: str | Path = NEWS_EVENTS_PATH) -> pd.DataFrame:
    if Path(path).exists():
        return normalize_news_events(pd.read_csv(path))
    return sample_power_news()


@st.cache_data(ttl=900, show_spinner=False)
def load_live_power_news_with_diagnostics() -> tuple[pd.DataFrame, list[str], list[str]]:
    return fetch_public_power_news_with_diagnostics()


def load_live_power_news() -> pd.DataFrame:
    """Backward-compatible live-news loader."""
    return load_live_power_news_with_diagnostics()[0]


def get_power_news(use_live: bool = False) -> tuple[pd.DataFrame, list[str], str]:
    if not use_live:
        try:
            published = load_published_csv(
                PUBLISHED_ARTIFACTS["news"],
                parse_dates=("published_at",),
            )
            return normalize_news_events(published), [], "Scheduled public news snapshot"
        except Exception:
            return load_power_news(), [], "Bundled sample news"
    try:
        news, warnings, sources = load_live_power_news_with_diagnostics()
        if news.empty:
            warnings.append("Public news refresh returned no matching Japan power items; using bundled sample news.")
            return load_power_news(), warnings, "Bundled sample news"
        source_label = f"Live public news ({', '.join(sources)})" if sources else "Live public news"
        return news, warnings, source_label
    except Exception as exc:
        return load_power_news(), [f"Public news refresh failed, using bundled sample news: {exc}"], "Bundled sample news"


def load_uploaded_power_news(uploaded_file) -> pd.DataFrame:
    return normalize_news_events(pd.read_csv(uploaded_file))


@st.cache_data(show_spinner=False)
def load_jepx_offer_stack(path: str | Path = JEPX_OFFER_STACK_LATEST_MONTH_PATH) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["delivery_date", "downloaded_at"])


@st.cache_data(ttl=900, show_spinner=False)
def load_jepx_offer_stack_depth(
    path: str | Path = JEPX_OFFER_STACK_DEPTH_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=JEPX_OFFER_STACK_DEPTH_PATH,
        artifact=PUBLISHED_ARTIFACTS["jepx_offer_stack_depth"],
        parse_dates=("delivery_date",),
        use_published=use_published,
    )


@st.cache_data(ttl=900, show_spinner=False)
def load_jepx_offer_stack_compact_curves(
    path: str | Path = JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=JEPX_OFFER_STACK_CURVES_COMPACT_PATH,
        artifact=PUBLISHED_ARTIFACTS["jepx_offer_stack_curves"],
        parse_dates=("delivery_date",),
        use_published=use_published,
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_live_jepx_offer_stack_latest_month(days: int = 31) -> pd.DataFrame:
    return fetch_latest_month_jepx_offer_stack(days=days)


def get_jepx_offer_stack(use_live: bool = False, days: int = 31) -> tuple[pd.DataFrame, list[str], str]:
    if not use_live:
        data = load_jepx_offer_stack()
        label = "Local JEPX offer-stack CSV" if not data.empty else "No local JEPX offer-stack CSV"
        return data, [], label
    try:
        data = load_live_jepx_offer_stack_latest_month(days=days)
        if data.empty:
            return (
                load_jepx_offer_stack(),
                ["JEPX offer-stack refresh returned no rows; using local CSV if available."],
                "Local JEPX offer-stack CSV",
            )
        return data, [], "JEPX public bidding-curve endpoint"
    except Exception as exc:
        return (
            load_jepx_offer_stack(),
            [f"JEPX offer-stack refresh failed, using local CSV if available: {exc}"],
            "Local JEPX offer-stack CSV",
        )


def load_uploaded_jepx_offer_stack(uploaded_file) -> pd.DataFrame:
    return normalize_jepx_offer_stack_upload(pd.read_csv(uploaded_file))


@st.cache_data(ttl=900, show_spinner=False)
def load_jepx_intraday(
    path: str | Path = JEPX_INTRADAY_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=JEPX_INTRADAY_PATH,
        artifact=PUBLISHED_ARTIFACTS["jepx_intraday"],
        parse_dates=("delivery_date",),
        use_published=use_published,
    )


def load_uploaded_jepx_intraday(uploaded_file) -> pd.DataFrame:
    return normalize_jepx_intraday(pd.read_csv(uploaded_file))


@st.cache_data(ttl=900, show_spinner=False)
def load_jepx_baseload(
    path: str | Path = JEPX_BASELOAD_PATH,
    use_published: bool | None = None,
) -> pd.DataFrame:
    return _published_or_local_csv(
        path=path,
        default_path=JEPX_BASELOAD_PATH,
        artifact=PUBLISHED_ARTIFACTS["jepx_baseload"],
        parse_dates=("trade_date",),
        use_published=use_published,
    )


def load_uploaded_jepx_baseload(uploaded_file) -> pd.DataFrame:
    return normalize_jepx_baseload(pd.read_csv(uploaded_file))


def _missing_columns(df: pd.DataFrame, required: set[str]) -> list[str]:
    return sorted(required.difference(df.columns))


def validate_forward_curve(df: pd.DataFrame) -> DatasetDiagnostics:
    errors: list[str] = []
    warnings: list[str] = []
    missing = _missing_columns(df, FORWARD_CURVE_REQUIRED)
    if missing:
        errors.append(f"Missing required curve columns: {', '.join(missing)}")
        return DatasetDiagnostics(tuple(errors), tuple(warnings))
    if df.empty:
        errors.append("Forward curve upload is empty.")
        return DatasetDiagnostics(tuple(errors), tuple(warnings))
    if df["market"].astype(str).str.strip().eq("").any():
        errors.append("Forward curve upload contains blank market codes.")
    if df["price"].isna().any():
        errors.append("Forward curve upload contains non-numeric or blank prices.")
    if (df["price"] <= 0).any():
        warnings.append("Forward curve upload contains non-positive prices; check units and signs.")
    if df["curve_date"].isna().any() or df["contract_month"].isna().any():
        errors.append("Forward curve upload contains invalid curve_date or contract_month values.")
    if not df[["curve_date", "contract_month", "market"]].drop_duplicates().shape[0] == len(df):
        warnings.append("Duplicate curve points detected; averages will be used in charts and analytics.")
    if df["contract_month"].lt(df["curve_date"].dt.to_period("M").dt.start_time).any():
        warnings.append("Some contract months are earlier than curve date; verify tenor labels.")
    return DatasetDiagnostics(tuple(errors), tuple(warnings))


def normalize_forward_curve_upload(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    for col in ["curve_date", "contract_month"]:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.tz_localize(None)
    if "price" in out.columns:
        out["price"] = pd.to_numeric(out["price"], errors="coerce")
    if "market" in out.columns:
        out["market"] = out["market"].astype(str).str.strip().str.upper()
    for col in ["region", "currency", "unit"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str).str.strip()
    optional_defaults = {
        "contract_type": "uploaded_curve",
        "source_note": "User-uploaded forward curve; verify source, settlement basis, and unit before trading use.",
    }
    for col, default in optional_defaults.items():
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default).astype(str)
    sort_cols = [col for col in ["market", "curve_date", "contract_month"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols)
    return out.reset_index(drop=True)


def load_uploaded_curve(uploaded_file) -> pd.DataFrame:
    raw = pd.read_csv(uploaded_file)
    df = normalize_forward_curve_upload(raw)
    diagnostics = validate_forward_curve(df)
    if not diagnostics.ok:
        raise ValueError("; ".join(diagnostics.errors))
    df.attrs["diagnostics"] = diagnostics
    return df


@lru_cache(maxsize=2)
def duckdb_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=":memory:")
