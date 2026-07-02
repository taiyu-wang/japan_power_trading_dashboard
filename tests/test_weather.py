import pandas as pd
import pytest
import plotly.graph_objects as go

from src.charts import weather_scatter
from src.sample_data import generate_weather_data
from src.weather import (
    calculate_degree_days,
    fetch_open_meteo_daily_temperatures,
    normalize_weather_data,
    weather_power_join,
    weather_spread,
)


def test_calculate_degree_days_uses_expected_bases():
    out = calculate_degree_days(pd.Series([16.0, 18.0, 22.0, 27.0]))

    assert out["heating_degree_day"].tolist() == [2.0, 0.0, 0.0, 0.0]
    assert out["cooling_degree_day"].tolist() == [0.0, 0.0, 0.0, 5.0]


def test_normalize_weather_data_rejects_bad_temperature():
    df = pd.DataFrame({"date": ["2026-01-01"], "region": ["Tokyo"], "temperature_mean_c": ["bad"]})

    with pytest.raises(ValueError, match="temperatures"):
        normalize_weather_data(df)


def test_weather_power_join_uses_region_specific_power_market():
    dates = pd.date_range("2026-01-01", periods=2)
    weather = normalize_weather_data(
        pd.DataFrame(
            {
                "date": list(dates) * 2,
                "region": ["Tokyo", "Tokyo", "Kansai", "Kansai"],
                "temperature_mean_c": [10, 11, 12, 13],
            }
        )
    )
    power = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "market": ["JEPX_TOKYO", "JEPX_TOKYO", "JEPX_KANSAI", "JEPX_KANSAI"],
            "price": [20, 21, 18, 19],
        }
    )

    out = weather_power_join(weather, power)

    assert len(out) == 4
    assert set(out["power_market"]) == {"JEPX_TOKYO", "JEPX_KANSAI"}


def test_generate_weather_data_returns_two_regions_per_date():
    dates = pd.date_range("2026-01-01", periods=5)
    out = generate_weather_data(dates=dates)

    assert len(out) == 10
    assert set(out["region"]) == {"Tokyo", "Kansai"}
    assert (out[["cooling_degree_day", "heating_degree_day"]] >= 0).all().all()


def test_weather_spread_returns_tokyo_minus_kansai():
    weather = normalize_weather_data(
        pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-01"],
                "region": ["Tokyo", "Kansai"],
                "temperature_mean_c": [25, 23],
            }
        )
    )

    out = weather_spread(weather)

    assert out.iloc[0]["value"] == 2


def test_weather_scatter_does_not_require_external_trendline_engine():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4).tolist() * 2,
            "region": ["Tokyo"] * 4 + ["Kansai"] * 4,
            "cooling_degree_day": [0, 1, 2, 3, 0, 2, 4, 6],
            "price": [10, 11, 12, 13, 9, 11, 13, 15],
        }
    )

    fig = weather_scatter(df, "cooling_degree_day", "price", "region", "Weather beta", "CDD", "JPY/kWh")

    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 4


def test_open_meteo_fetch_drops_incomplete_api_rows(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "daily": {
                    "time": ["2026-06-29", "2026-06-30"],
                    "temperature_2m_mean": [25.0, None],
                    "temperature_2m_max": [29.0, None],
                    "temperature_2m_min": [21.0, None],
                }
            }

    monkeypatch.setattr("src.weather.requests.get", lambda *args, **kwargs: Response())

    out = fetch_open_meteo_daily_temperatures("2026-06-29", "2026-06-30")

    assert len(out) == 2
    assert out["date"].eq(pd.Timestamp("2026-06-29")).all()
    assert set(out["region"]) == {"Tokyo", "Kansai"}
