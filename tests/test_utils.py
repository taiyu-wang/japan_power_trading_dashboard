import pandas as pd

from src.utils import format_dates_for_display


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
