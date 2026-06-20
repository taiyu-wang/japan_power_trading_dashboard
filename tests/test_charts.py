import pandas as pd

from src.charts import (
    baseload_price_volume_chart,
    generation_share_area_chart,
    intraday_convergence_chart,
    offer_stack_curve_chart,
    offer_stack_depth_heatmap,
    offer_stack_daily_price_sensitivity_chart,
    offer_stack_period_shift_chart,
    offer_stack_price_sensitivity_heatmap,
    offer_stack_price_attribution_chart,
    offer_stack_tightness_spread_chart,
    offer_stack_shift_chart,
)


def test_generation_share_chart_uses_area_subtitles_and_month_axis():
    df = pd.DataFrame(
        {
            "month": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-01", "2026-01-01"]),
            "area": ["Tokyo", "Tokyo", "Kansai", "Kansai"],
            "generation_type": ["Gas", "Solar", "Gas", "Nuclear"],
            "share_pct": [80, 20, 55, 45],
            "generation_gwh": [800, 200, 550, 450],
        }
    )

    fig = generation_share_area_chart(df)

    subtitles = {annotation.text for annotation in fig.layout.annotations}
    assert {"Tokyo Area", "Kansai Area"}.issubset(subtitles)
    assert fig.layout.xaxis.tickformat == "%b %Y"
    assert fig.layout.xaxis.hoverformat == "%b %Y"
    assert "Generation:" in fig.data[0].hovertemplate
    assert "Area:" in fig.data[0].hovertemplate
    assert "generation_type" not in fig.data[0].hovertemplate


def test_offer_stack_curve_chart_uses_readable_hover_labels():
    df = pd.DataFrame(
        {
            "bid_price_jpy_kwh": [0, 5, 10],
            "sell_cumulative_mw": [100, 200, 300],
            "buy_cumulative_mw": [300, 200, 100],
            "net_supply_mw": [-200, 0, 200],
        }
    )
    df.attrs["clearing_price_estimate"] = 5

    fig = offer_stack_curve_chart(df, "System Price Stack")

    assert "Sell curve" in {trace.name for trace in fig.data}
    assert "Buy curve" in {trace.name for trace in fig.data}
    assert "JPY/kWh" in fig.data[0].hovertemplate
    assert "sell_cumulative_mw" not in fig.data[0].hovertemplate


def test_offer_stack_depth_heatmap_labels_time_and_depth():
    df = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-05-31", "2026-05-31"]),
            "time_code": [1, 2],
            "area_group": ["System Price", "System Price"],
            "tightest_depth_mw": [1000, 2000],
        }
    )

    fig = offer_stack_depth_heatmap(df)

    assert fig.layout.xaxis.title.text == "Delivery date"
    assert fig.layout.yaxis.title.text == "Time code"
    assert fig.layout.coloraxis.colorbar.title.text == "Tightest depth (MW)"


def test_offer_stack_price_sensitivity_heatmap_uses_readable_hover_labels():
    df = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-06-02", "2026-06-02"]),
            "time_code": [37, 38],
            "area_group": ["System Price", "System Price"],
            "shock_mw": [500, 500],
            "price_impact_jpy_kwh": [4.0, 6.0],
        }
    )

    fig = offer_stack_price_sensitivity_heatmap(df, shock_mw=500)

    assert fig.layout.xaxis.title.text == "Delivery date"
    assert fig.layout.yaxis.title.text == "Time code"
    assert fig.layout.coloraxis.colorbar.title.text == "Price impact (JPY/kWh)"


def test_offer_stack_daily_price_sensitivity_chart_uses_block_and_impact_axes():
    df = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-06-02", "2026-06-02"]),
            "time_code": [37, 38],
            "area_group": ["System Price", "System Price"],
            "shock_mw": [500, 500],
            "scenario_price_jpy_kwh": [22.0, 24.0],
            "price_impact_jpy_kwh": [4.0, 6.0],
        }
    )

    fig = offer_stack_daily_price_sensitivity_chart(df, shock_mw=500)

    assert fig.layout.xaxis.title.text == "Half-hour delivery block"
    assert fig.layout.yaxis.title.text == "Price impact (JPY/kWh)"
    assert fig.data[0].name == "+500 MW net demand"
    assert "Delivery block:" in fig.data[0].hovertemplate


def test_offer_stack_tightness_spread_chart_names_tokyo_kansai_spread():
    df = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-06-02"]),
            "time_code": [37],
            "tightness_spread_mw": [-1200],
            "tokyo_tightest_depth_mw": [800],
            "kansai_tightest_depth_mw": [2000],
            "tighter_area": ["Tokyo"],
        }
    )

    fig = offer_stack_tightness_spread_chart(df)

    assert fig.data[0].name == "Tokyo minus Kansai tightness"
    assert "Tighter area:" in fig.data[0].hovertemplate
    assert "tightness_spread_mw" not in fig.data[0].hovertemplate


def test_offer_stack_shift_chart_uses_readable_hover_labels():
    df = pd.DataFrame(
        {
            "bid_price_jpy_kwh": [10, 20, 30, 1000],
            "sell_shift_mw": [-200, -300, -100, 900],
            "buy_shift_mw": [400, 300, 100, -800],
        }
    )
    df.attrs["summary"] = {"current_clearing_price_estimate": 20}

    fig = offer_stack_shift_chart(df)

    assert {"Sell depth shift", "Buy depth shift"}.issubset({trace.name for trace in fig.data})
    assert "Shift:" in fig.data[0].hovertemplate
    assert "sell_shift_mw" not in fig.data[0].hovertemplate
    assert fig.layout.xaxis.title.text == "Bid price around clearing (JPY/kWh)"
    assert fig.layout.yaxis.title.text == "Cumulative depth shift (MW)"
    assert max(fig.data[0].x) < 1000


def test_offer_stack_period_shift_charts_use_trader_labels():
    df = pd.DataFrame(
        {
            "delivery_period": ["Evening peak"],
            "supply_tightening_mw": [500],
            "demand_strength_mw": [300],
            "net_tightening_pressure_mw": [800],
            "supply_price_contribution_jpy_kwh": [2.0],
            "demand_price_contribution_jpy_kwh": [1.0],
            "interaction_jpy_kwh": [0.5],
            "price_change_jpy_kwh": [3.5],
        }
    )

    shift_fig = offer_stack_period_shift_chart(df)
    price_fig = offer_stack_price_attribution_chart(df)

    assert {"Supply-side tightening", "Buy-side strength", "Net tightening pressure"}.issubset({trace.name for trace in shift_fig.data})
    assert {"Supply curve", "Demand curve", "Actual price change"}.issubset({trace.name for trace in price_fig.data})
    assert "supply_tightening_mw" not in shift_fig.data[0].hovertemplate
    assert "JPY/kWh" in price_fig.layout.yaxis.title.text


def test_intraday_convergence_chart_uses_readable_trace_names():
    df = pd.DataFrame(
        {
            "delivery_date": pd.to_datetime(["2026-06-02"]),
            "spot_price": [20.0],
            "intraday_average_price": [18.0],
            "spot_intraday_spread": [2.0],
        }
    )

    fig = intraday_convergence_chart(df)

    assert {"JEPX day-ahead system", "Intraday average", "Spot minus intraday"}.issubset({trace.name for trace in fig.data})
    assert "JPY/kWh" in fig.data[0].hovertemplate


def test_baseload_price_volume_chart_uses_contract_hover_labels():
    df = pd.DataFrame(
        {
            "fiscal_year": [2026],
            "product_name": ["BY2601B3"],
            "area": ["Tokyo"],
            "trade_date": pd.to_datetime(["2025-08-29"]),
            "clearing_price_jpy_kwh": [15.5],
            "volume_mw": [20.0],
        }
    )

    fig = baseload_price_volume_chart(df)

    assert "Product" not in fig.data[0].hovertemplate
    assert "Area:" in fig.data[0].hovertemplate
    assert "Price:" in fig.data[0].hovertemplate
