from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
HISTORICAL_DATA_PATH = DATA_DIR / "sample_historical_prices.csv"
FORWARD_CURVES_PATH = DATA_DIR / "sample_forward_curves.csv"
POWER_FUTURES_PATH = DATA_DIR / "sample_power_futures.csv"
MARKET_MAPPING_PATH = DATA_DIR / "market_mapping.csv"
WEATHER_DATA_PATH = DATA_DIR / "sample_weather_temperatures.csv"
SUPPLY_MIX_PATH = DATA_DIR / "sample_generation_mix.csv"
SUPPLY_MIX_MONTHLY_PATH = DATA_DIR / "processed" / "tokyo_kansai_generation_monthly.csv"
SUPPLY_MIX_DAILY_SHAPE_PATH = DATA_DIR / "processed" / "tokyo_kansai_generation_daily_shape.csv"
SUPPLY_MIX_RESIDUAL_THERMAL_PATH = DATA_DIR / "processed" / "tokyo_kansai_residual_thermal.csv"
NEWS_EVENTS_PATH = DATA_DIR / "sample_power_news.csv"
JEPX_OFFER_STACK_LATEST_MONTH_PATH = DATA_DIR / "raw" / "jepx_offer_stack_latest_1m.csv"
JEPX_OFFER_STACK_DAILY_CACHE_DIR = DATA_DIR / "raw" / "jepx_offer_stack_daily"
JEPX_OFFER_STACK_DEPTH_PATH = DATA_DIR / "processed" / "jepx_offer_stack_depth.csv"
JEPX_OFFER_STACK_CURVES_COMPACT_PATH = DATA_DIR / "processed" / "jepx_offer_stack_curves_compact.csv"
JEPX_OFFER_STACK_SENSITIVITY_PATH = DATA_DIR / "processed" / "jepx_offer_stack_price_sensitivity.csv"
JEPX_INTRADAY_PATH = DATA_DIR / "processed" / "jepx_intraday_latest.csv"
JEPX_BASELOAD_PATH = DATA_DIR / "processed" / "jepx_baseload_market.csv"

APP_TITLE = "Japan Fuel & Power Market Dashboard"

MARKET_COLORS = {
    "JKM": "#00A6A6",
    "DES_JAPAN_LNG": "#70C7B5",
    "JCC": "#A87932",
    "JCC_LINKED_LNG": "#D39B36",
    "NEWCASTLE_COAL": "#2F3136",
    "CFR_JAPAN_COAL": "#5C626B",
    "BRENT": "#D64545",
    "USDJPY": "#7B61FF",
    "JEPX_SYSTEM": "#2F3A4A",
    "JEPX_INTRADAY": "#4F86F7",
    "JEPX_TOKYO": "#D65F5F",
    "JEPX_KANSAI": "#008A66",
    "JAPAN_POWER_FUTURES": "#2563EB",
    "TOKYO_TEMP": "#E45757",
    "KANSAI_TEMP": "#0AA06E",
    "Gas": "#2F5F9E",
    "Coal": "#2D3640",
    "Nuclear": "#2F8F71",
    "Solar": "#D9A21B",
    "Hydro": "#2A9FD6",
    "Wind": "#68AFA0",
    "Biomass": "#8A5E9E",
    "Oil": "#9A6B3F",
    "Other": "#8F98A3",
}

ASSET_GROUPS = {
    "LNG": ["JKM", "DES_JAPAN_LNG", "JCC_LINKED_LNG"],
    "Coal": ["NEWCASTLE_COAL", "CFR_JAPAN_COAL"],
    "Crude": ["JCC", "BRENT"],
    "Power": ["JEPX_SYSTEM", "JEPX_INTRADAY", "JEPX_TOKYO", "JEPX_KANSAI", "JAPAN_POWER_FUTURES"],
    "FX": ["USDJPY"],
}

DEFAULT_MARKETS = ["JKM", "JCC", "NEWCASTLE_COAL", "JEPX_SYSTEM", "JEPX_TOKYO", "JEPX_KANSAI", "USDJPY"]
DEFAULT_FOCUS_START = "2026-02-01"

PAGE_ICON = "chart_with_upwards_trend"

MARKET_NOTES = {
    "JCC": "Sample JCC is a synthetic Japan customs-cleared crude proxy in USD/bbl. JCC is normally a monthly customs statistic, not an exchange-traded futures contract.",
    "BRENT": "Sample Brent is a synthetic Brent crude proxy in USD/bbl. Replace with EIA spot history or ICE Brent futures settlements for production use.",
    "JAPAN_POWER_FUTURES": "Sample Japan power futures are prompt-month, cash-settled futures proxies referencing JEPX area prices. They are financial futures, not physical power delivery.",
    "JEPX_SYSTEM": "JEPX system price is a physical day-ahead spot market price proxy, not a futures contract.",
}

WEATHER_LOCATIONS = {
    "TOKYO": {"label": "Tokyo", "latitude": 35.6762, "longitude": 139.6503, "power_market": "JEPX_TOKYO"},
    "KANSAI": {"label": "Kansai / Osaka", "latitude": 34.6937, "longitude": 135.5023, "power_market": "JEPX_KANSAI"},
}

WEATHER_SOURCE_NOTE = (
    "Weather history is bundled synthetic sample data unless live Open-Meteo refresh is enabled or licensed/user weather data is connected."
)
