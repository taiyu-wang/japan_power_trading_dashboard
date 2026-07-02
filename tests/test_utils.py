import pandas as pd

from src.utils import format_dates_for_display, freshness_bar_html


def test_format_dates_for_display_removes_midnight_time():
    df = pd.DataFrame(
        {
            "curve_date": [pd.Timestamp("2026-05-30 00:00:00")],
            "contract_month": [pd.Timestamp("2027-07-01 00:00:00")],
            "price": [12.5],
        }
    )

    out = format_dates_for_display(df)

    assert out.loc[0, "curve_date"] == "2026-05-30"
    assert out.loc[0, "contract_month"] == "2027-07-01"
    assert out.loc[0, "price"] == 12.5


def test_freshness_bar_html_shows_group_dates_and_status_classes():
    manifest = {
        "overall_status": "stale",
        "generated_at": "2026-07-01T00:00:00+00:00",
        "warnings": [],
        "datasets": [
            {
                "dataset_id": "historical_prices",
                "label": "Historical prices",
                "observation_end": "2026-06-08",
                "status": "stale",
            },
            {
                "dataset_id": "weather",
                "label": "Weather",
                "observation_end": "2026-06-30",
                "status": "current",
            },
            {
                "dataset_id": "jepx_intraday",
                "label": "JEPX intraday",
                "observation_end": "2026-06-30",
                "status": "current",
            },
            {
                "dataset_id": "supply_mix_daily_shape",
                "label": "Supply mix daily shape",
                "observation_end": "2026-07-01",
                "status": "current",
            },
        ],
    }

    html = freshness_bar_html(manifest, source="scheduled public manifest")

    assert "Data status" in html
    assert "Historical: 2026-06-08" in html
    assert "JEPX: 2026-06-30" in html
    assert "Supply: 2026-07-01" in html
    assert "Weather: 2026-06-30" in html
    assert "freshness-stale" in html
    assert "scheduled public manifest" in html
