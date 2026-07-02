import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from .config import MARKET_COLORS


PLOT_TEMPLATE = "plotly_white"
PAPER_BG = "#FFFFFF"
PLOT_BG = "#FFFFFF"
GRID_COLOR = "rgba(31, 41, 51, 0.08)"
REFERENCE_LINE = "rgba(31, 41, 51, 0.32)"
TEXT_COLOR = "#1F2933"
MUTED_COLOR = "#667085"
NAVY = "#2F3A4A"
RED = "#D64545"
BLUE = "#2563EB"
LIGHT_BLUE = "#4F86F7"
AMBER = "#D39B36"
GREEN = "#008A66"
TEAL = "#00A6A6"
COAL = "#2F3136"
DISPLAY_LABELS = {
    "area": "Area",
    "asset_class": "Asset class",
    "contract": "Contract",
    "contract_month": "Contract month",
    "contract_month_label": "Contract month",
    "contract_type": "Contract type",
    "currency": "Currency",
    "curve_date": "Curve date",
    "date": "Date",
    "generation_gwh": "Generation (GWh)",
    "generation_type": "Generation type",
    "market": "Market",
    "month": "Month",
    "price": "Price",
    "product": "Product",
    "settlement_price": "Settlement price",
    "peak_premium": "Peak premium",
    "rank_pct": "Share of observations exceeded (%)",
    "region": "Region",
    "return_pct": "Return (%)",
    "share_pct": "Share of generation (%)",
    "source_note": "Source note",
    "unit": "Unit",
    "value": "Value",
    "volatility": "Volatility",
    "window": "Window",
}


def apply_terminal_layout(fig: go.Figure, height: int = 430) -> go.Figure:
    fig.update_layout(
        template=PLOT_TEMPLATE,
        height=height,
        margin=dict(l=42, r=24, t=78, b=40),
        title=dict(font=dict(size=15, color=NAVY), x=0.01, xanchor="left", y=0.98, yanchor="top"),
        font=dict(size=12, color=TEXT_COLOR),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        colorway=[GREEN, BLUE, RED, TEAL, AMBER, "#7B61FF", "#C05A8A", COAL],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="left",
            x=0,
            bgcolor="rgba(255,255,255,0)",
            font=dict(size=11, color=TEXT_COLOR),
            itemwidth=30,
        ),
        hoverlabel=dict(font_size=12, align="left", bgcolor="#FFFFFF", bordercolor="#E3E8EF", font_color=TEXT_COLOR),
        modebar=dict(orientation="h"),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False, ticks="outside", ticklen=4, linecolor="#E3E8EF")
    fig.update_xaxes(hoverformat="%Y-%m-%d")
    fig.update_yaxes(showgrid=True, gridcolor=GRID_COLOR, zerolinecolor=REFERENCE_LINE, ticks="outside", ticklen=4, linecolor="#E3E8EF")
    return fig


def _hover_data(df: pd.DataFrame) -> list[str]:
    return [col for col in ["market", "region", "currency", "unit", "contract", "contract_type"] if col in df.columns]


def _labels(extra: dict[str, str] | None = None) -> dict[str, str]:
    labels = DISPLAY_LABELS.copy()
    if extra:
        labels.update(extra)
    return labels


def _apply_area_subtitles(fig: go.Figure) -> None:
    for annotation in fig.layout.annotations:
        text = str(annotation.text).replace("area=", "").replace("Area=", "")
        annotation.update(
            text=f"{text} Area",
            x=0.01,
            xanchor="left",
            textangle=0,
            font=dict(size=14),
        )


def _unit_title(df: pd.DataFrame, fallback: str = "Price / index level") -> str:
    if {"currency", "unit"}.issubset(df.columns) and not df.empty:
        pairs = df[["currency", "unit"]].dropna().drop_duplicates()
        pairs = pairs[(pairs["currency"].astype(str) != "") | (pairs["unit"].astype(str) != "")]
        if len(pairs) == 1:
            row = pairs.iloc[0]
            return f"{row['currency']}/{row['unit']}".strip("/")
    return fallback


def line_chart(df: pd.DataFrame, x: str, y: str, color: str, title: str, y_title: str | None = None) -> go.Figure:
    fig = px.line(df, x=x, y=y, color=color, title=title, color_discrete_map=MARKET_COLORS, template=PLOT_TEMPLATE, hover_data=_hover_data(df), labels=_labels())
    fig.update_layout(hovermode="x unified", legend_title_text="", yaxis_title=y_title or y, xaxis_title="")
    return apply_terminal_layout(fig)


def volatility_chart(df: pd.DataFrame, title: str = "Rolling Realized Volatility") -> go.Figure:
    fig = px.line(
        df,
        x="date",
        y="volatility",
        color="market",
        line_dash="window",
        title=title,
        color_discrete_map=MARKET_COLORS,
        template=PLOT_TEMPLATE,
        hover_data=["market", "window", "volatility"],
        labels=_labels(),
    )
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="", yaxis_title="% annualized")
    fig.add_hline(y=50, line_width=1, line_dash="dot", line_color=REFERENCE_LINE)
    fig.add_hline(y=100, line_width=1, line_dash="dot", line_color=AMBER)
    return apply_terminal_layout(fig)


def area_line(df: pd.DataFrame, x: str, y: str, color: str, title: str) -> go.Figure:
    fig = px.area(df, x=x, y=y, color=color, title=title, color_discrete_map=MARKET_COLORS, template=PLOT_TEMPLATE, labels=_labels())
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="")
    return apply_terminal_layout(fig)


def heatmap(matrix: pd.DataFrame, title: str) -> go.Figure:
    fig = px.imshow(matrix, text_auto=".2f", aspect="auto", color_continuous_scale="RdBu_r", zmin=-1 if title.lower().find("correlation") >= 0 else None, zmax=1 if title.lower().find("correlation") >= 0 else None, title=title, template=PLOT_TEMPLATE, labels=_labels())
    fig.update_layout(xaxis_title="", yaxis_title="")
    return apply_terminal_layout(fig)


def distribution_chart(df: pd.DataFrame, x: str, color: str, title: str) -> go.Figure:
    fig = px.histogram(df, x=x, color=color, nbins=80, marginal="box", barmode="overlay", opacity=0.58, title=title, template=PLOT_TEMPLATE, color_discrete_map=MARKET_COLORS, labels=_labels())
    fig.update_layout(legend_title_text="")
    return apply_terminal_layout(fig)


def bar_chart(df: pd.DataFrame, x: str, y: str, color: str | None, title: str) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, title=title, template=PLOT_TEMPLATE, color_discrete_map=MARKET_COLORS, labels=_labels())
    fig.update_layout(legend_title_text="", xaxis_title="", yaxis_title=y)
    return apply_terminal_layout(fig)


def generation_share_area_chart(df: pd.DataFrame, title: str = "Monthly Generation Market Share") -> go.Figure:
    generation_order = ["Gas", "Coal", "Nuclear", "Solar", "Hydro", "Wind", "Biomass", "Oil", "Other"]
    fig = px.area(
        df,
        x="month",
        y="share_pct",
        color="generation_type",
        facet_row="area",
        category_orders={"generation_type": generation_order},
        color_discrete_map=MARKET_COLORS,
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["area", "month", "generation_type", "share_pct", "generation_gwh"],
        labels=_labels(),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[2]}</b><br>"
            "Area: %{customdata[0]}<br>"
            "Month: %{customdata[1]|%b %Y}<br>"
            "Share: %{customdata[3]:.1f}%<br>"
            "Generation: %{customdata[4]:,.0f} GWh"
            "<extra></extra>"
        )
    )
    for trace in fig.data:
        if trace.name in MARKET_COLORS:
            trace.update(fillcolor=MARKET_COLORS[trace.name], line=dict(color=MARKET_COLORS[trace.name], width=1.7))
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="", yaxis_title="Share of generation (%)")
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    _apply_area_subtitles(fig)
    fig = apply_terminal_layout(fig, height=620)
    fig.update_xaxes(tickformat="%b %Y", hoverformat="%b %Y")
    return fig


def generation_volume_bar_chart(df: pd.DataFrame, title: str = "Monthly Generation by Fuel") -> go.Figure:
    generation_order = ["Gas", "Coal", "Nuclear", "Solar", "Hydro", "Wind", "Biomass", "Oil", "Other"]
    fig = px.bar(
        df,
        x="month",
        y="generation_gwh",
        color="generation_type",
        facet_row="area",
        category_orders={"generation_type": generation_order},
        color_discrete_map=MARKET_COLORS,
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["area", "month", "generation_type", "share_pct", "generation_gwh"],
        labels=_labels(),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[2]}</b><br>"
            "Area: %{customdata[0]}<br>"
            "Month: %{customdata[1]|%b %Y}<br>"
            "Share: %{customdata[3]:.1f}%<br>"
            "Generation: %{customdata[4]:,.0f} GWh"
            "<extra></extra>"
        )
    )
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="", yaxis_title="GWh")
    _apply_area_subtitles(fig)
    fig = apply_terminal_layout(fig, height=620)
    fig.update_xaxes(tickformat="%b %Y", hoverformat="%b %Y")
    return fig


def power_futures_curve_chart(df: pd.DataFrame, title: str = "Monthly Power Futures Curve") -> go.Figure:
    plot_df = df.copy()
    if plot_df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title), height=520)
    plot_df["contract_month_label"] = plot_df["contract_month"].dt.strftime("%b %Y")
    plot_df["curve_date_label"] = plot_df["curve_date"].dt.strftime("%Y-%m-%d")
    order = plot_df.sort_values("contract_month")["contract_month_label"].drop_duplicates().tolist()
    fig = px.line(
        plot_df,
        x="contract_month_label",
        y="settlement_price",
        color="product",
        line_dash="curve_date_label",
        markers=True,
        category_orders={"contract_month_label": order},
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["area", "load_type", "curve_date_label", "contract_month_label", "settlement_price", "source"],
        labels=_labels({"curve_date_label": "Curve date"}),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]} %{customdata[1]}</b><br>"
            "Curve date: %{customdata[2]}<br>"
            "Contract month: %{customdata[3]}<br>"
            "Settlement: %{customdata[4]:.2f} JPY/kWh<br>"
            "Source: %{customdata[5]}"
            "<extra></extra>"
        )
    )
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="Contract month", yaxis_title="JPY/kWh")
    return apply_terminal_layout(fig, height=520)


def power_futures_peak_premium_chart(df: pd.DataFrame, title: str = "Peakload Premium to Baseload") -> go.Figure:
    fig = px.line(
        df,
        x="contract_month",
        y="peak_premium",
        color="area",
        markers=True,
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["area", "contract_month", "peak_premium"],
        labels=_labels(),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Contract month: %{customdata[1]|%b %Y}<br>"
            "Peak premium: %{customdata[2]:.2f} JPY/kWh"
            "<extra></extra>"
        )
    )
    fig.update_xaxes(tickformat="%b %Y", hoverformat="%b %Y")
    fig.update_layout(hovermode="x unified", legend_title_text="", xaxis_title="", yaxis_title="JPY/kWh")
    return apply_terminal_layout(fig)


def offer_stack_curve_chart(df: pd.DataFrame, title: str = "JEPX Bidding Curve") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=520)
    fig.add_trace(
        go.Scatter(
            x=df["sell_cumulative_mw"],
            y=df["bid_price_jpy_kwh"],
            mode="lines",
            name="Sell curve",
            line=dict(color=RED, width=2.3),
            hovertemplate="Sell depth: %{x:,.0f} MW<br>Price: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["buy_cumulative_mw"],
            y=df["bid_price_jpy_kwh"],
            mode="lines",
            name="Buy curve",
            line=dict(color=BLUE, width=2.3),
            hovertemplate="Buy depth: %{x:,.0f} MW<br>Price: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    clearing = df.attrs.get("clearing_price_estimate")
    if clearing is not None and not pd.isna(clearing):
        fig.add_hline(
            y=float(clearing),
            line_color=AMBER,
            line_dash="dot",
            annotation_text=f"Estimated clearing {float(clearing):.2f}",
            annotation_position="top right",
        )
    fig.update_layout(
        title=title,
        hovermode="closest",
        legend_title_text="",
        xaxis_title="Cumulative depth (MW)",
        yaxis_title="Bid price (JPY/kWh)",
    )
    return apply_terminal_layout(fig, height=520)


def offer_stack_depth_heatmap(df: pd.DataFrame, title: str = "Stack Tightness Heatmap") -> go.Figure:
    if df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title), height=470)
    plot_df = df.copy()
    plot_df["delivery_date"] = pd.to_datetime(plot_df["delivery_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pivot = plot_df.pivot_table(index="time_code", columns="delivery_date", values="tightest_depth_mw", aggfunc="mean")
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="RdYlGn",
        title=title,
        template=PLOT_TEMPLATE,
        labels=dict(x="Delivery date", y="Time code", color="Tightest depth (MW)"),
    )
    fig.update_layout(xaxis_title="Delivery date", yaxis_title="Time code")
    fig.update_coloraxes(colorbar_title="Tightest depth (MW)")
    return apply_terminal_layout(fig, height=470)


def offer_stack_price_sensitivity_heatmap(
    df: pd.DataFrame,
    shock_mw: int = 500,
    title: str = "Price Sensitivity to Demand Shock",
) -> go.Figure:
    if df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title), height=470)
    plot_df = df.copy()
    shock_mask = pd.to_numeric(plot_df.get("shock_mw"), errors="coerce").eq(int(shock_mw))
    if shock_mask.any():
        plot_df = plot_df[shock_mask]
    plot_df["delivery_date"] = pd.to_datetime(plot_df["delivery_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pivot = plot_df.pivot_table(index="time_code", columns="delivery_date", values="price_impact_jpy_kwh", aggfunc="mean")
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="RdBu_r",
        title=title,
        template=PLOT_TEMPLATE,
        labels=dict(x="Delivery date", y="Time code", color="Price impact (JPY/kWh)"),
    )
    fig.update_layout(xaxis_title="Delivery date", yaxis_title="Time code")
    fig.update_coloraxes(colorbar_title="Price impact (JPY/kWh)")
    return apply_terminal_layout(fig, height=470)


def offer_stack_daily_price_sensitivity_chart(
    df: pd.DataFrame,
    shock_mw: int = 500,
    title: str = "Daily Price Sensitivity by Delivery Block",
) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=430)
    plot_df = df.copy()
    shock_mask = pd.to_numeric(plot_df.get("shock_mw"), errors="coerce").eq(int(shock_mw))
    if shock_mask.any():
        plot_df = plot_df[shock_mask]
    plot_df["time_code"] = pd.to_numeric(plot_df["time_code"], errors="coerce")
    plot_df = plot_df.dropna(subset=["time_code", "price_impact_jpy_kwh"]).sort_values("time_code")
    if plot_df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=430)
    plot_df["delivery_date"] = pd.to_datetime(plot_df["delivery_date"], errors="coerce")
    fig.add_trace(
        go.Bar(
            x=plot_df["time_code"],
            y=plot_df["price_impact_jpy_kwh"],
            name=f"+{int(shock_mw):,} MW net demand",
            marker_color=np.where(plot_df["price_impact_jpy_kwh"] >= 0, RED, BLUE),
            customdata=plot_df[["delivery_date", "time_code", "scenario_price_jpy_kwh"]],
            hovertemplate=(
                "Delivery date: %{customdata[0]|%Y-%m-%d}<br>"
                "Delivery block: %{customdata[1]:.0f}<br>"
                "Scenario price: %{customdata[2]:.2f} JPY/kWh<br>"
                "Price impact: %{y:+.2f} JPY/kWh"
                "<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    fig.update_layout(
        title=title,
        xaxis_title="Half-hour delivery block",
        yaxis_title="Price impact (JPY/kWh)",
        showlegend=True,
    )
    fig.update_xaxes(dtick=4)
    return apply_terminal_layout(fig, height=430)


def offer_stack_tightness_spread_chart(df: pd.DataFrame, title: str = "Tokyo/Kansai Stack Tightness Spread") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=390)
    plot_df = df.copy()
    plot_df["delivery_date"] = pd.to_datetime(plot_df["delivery_date"], errors="coerce")
    custom_cols = ["delivery_date", "time_code", "tokyo_tightest_depth_mw", "kansai_tightest_depth_mw", "tighter_area"]
    fig.add_trace(
        go.Bar(
            x=plot_df["time_code"].astype(str),
            y=plot_df["tightness_spread_mw"],
            name="Tokyo minus Kansai tightness",
            marker_color=np.where(plot_df["tightness_spread_mw"] < 0, RED, BLUE),
            customdata=plot_df[custom_cols],
            hovertemplate=(
                "Date: %{customdata[0]|%Y-%m-%d}<br>"
                "Time code: %{customdata[1]}<br>"
                "Tokyo depth: %{customdata[2]:,.0f} MW<br>"
                "Kansai depth: %{customdata[3]:,.0f} MW<br>"
                "Spread: %{y:+,.0f} MW<br>"
                "Tighter area: %{customdata[4]}"
                "<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    fig.update_layout(
        title=title,
        xaxis_title="Half-hour product",
        yaxis_title="Tokyo minus Kansai tightest depth (MW)",
        showlegend=False,
    )
    return apply_terminal_layout(fig, height=390)


def offer_stack_scenario_bar(df: pd.DataFrame, title: str = "Price Impact by MW Shift") -> go.Figure:
    if df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title))
    plot_df = df.copy()
    plot_df["shift_label"] = plot_df["demand_shift_mw"].map(lambda value: f"{value:+,.0f} MW")
    fig = px.bar(
        plot_df,
        x="shift_label",
        y="price_impact_jpy_kwh",
        color="price_impact_jpy_kwh",
        color_continuous_scale="RdBu_r",
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["demand_shift_mw", "scenario_price_jpy_kwh", "price_impact_jpy_kwh"],
        labels=_labels({"shift_label": "Demand shift", "price_impact_jpy_kwh": "Price impact"}),
    )
    fig.update_traces(
        hovertemplate=(
            "Demand shift: %{customdata[0]:+,.0f} MW<br>"
            "Scenario price: %{customdata[1]:.2f} JPY/kWh<br>"
            "Price impact: %{customdata[2]:+.2f} JPY/kWh"
            "<extra></extra>"
        )
    )
    fig.update_layout(xaxis_title="", yaxis_title="JPY/kWh", showlegend=False)
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    return apply_terminal_layout(fig, height=390)


def offer_stack_shift_chart(df: pd.DataFrame, title: str = "Bidding Curve Shift") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=430)
    plot_df = df.copy()
    for col in ["bid_price_jpy_kwh", "sell_shift_mw", "buy_shift_mw"]:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
    plot_df = plot_df.dropna(subset=["bid_price_jpy_kwh", "sell_shift_mw", "buy_shift_mw"]).sort_values("bid_price_jpy_kwh")
    clearing = df.attrs.get("summary", {}).get("current_clearing_price_estimate") if isinstance(df.attrs.get("summary"), dict) else None
    if clearing is not None and pd.notna(clearing):
        lower = max(0, float(clearing) - 25)
        upper = max(float(clearing) + 35, 60)
        window = plot_df[plot_df["bid_price_jpy_kwh"].between(lower, upper)].copy()
        if len(window) >= 3:
            plot_df = window
    elif plot_df["bid_price_jpy_kwh"].max() > 120:
        window = plot_df[plot_df["bid_price_jpy_kwh"].le(120)].copy()
        if len(window) >= 3:
            plot_df = window
    plot_df["net_depth_shift_mw"] = plot_df["sell_shift_mw"] - plot_df["buy_shift_mw"]
    fig.add_trace(
        go.Scatter(
            x=plot_df["bid_price_jpy_kwh"],
            y=plot_df["sell_shift_mw"],
            mode="lines+markers",
            name="Sell depth shift",
            line=dict(color=RED, width=2.2),
            customdata=plot_df[["bid_price_jpy_kwh", "sell_shift_mw"]],
            hovertemplate="Price: %{customdata[0]:.2f} JPY/kWh<br>Shift: %{customdata[1]:+,.0f} MW<br>Curve: Sell depth<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=plot_df["bid_price_jpy_kwh"],
            y=plot_df["buy_shift_mw"],
            mode="lines+markers",
            name="Buy depth shift",
            line=dict(color=BLUE, width=2.2),
            customdata=plot_df[["bid_price_jpy_kwh", "buy_shift_mw"]],
            hovertemplate="Price: %{customdata[0]:.2f} JPY/kWh<br>Shift: %{customdata[1]:+,.0f} MW<br>Curve: Buy depth<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=plot_df["bid_price_jpy_kwh"],
            y=plot_df["net_depth_shift_mw"],
            name="Net depth shift",
            marker_color="rgba(127, 127, 127, 0.34)",
            customdata=plot_df[["bid_price_jpy_kwh", "net_depth_shift_mw"]],
            hovertemplate="Price: %{customdata[0]:.2f} JPY/kWh<br>Net depth shift: %{customdata[1]:+,.0f} MW<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    if clearing is not None and pd.notna(clearing):
        fig.add_vline(
            x=float(clearing),
            line_color=AMBER,
            line_dash="dot",
            line_width=1,
            annotation_text=f"Clearing {float(clearing):.2f}",
            annotation_position="top right",
        )
        summary = df.attrs.get("summary", {}) if isinstance(df.attrs.get("summary"), dict) else {}
        if summary:
            fig.add_annotation(
                x=float(clearing),
                y=0,
                text=(
                    f"Sell {summary.get('sell_shift_at_clearing_mw', 0):+,.0f} MW<br>"
                    f"Buy {summary.get('buy_shift_at_clearing_mw', 0):+,.0f} MW<br>"
                    f"Net {summary.get('net_depth_shift_at_clearing_mw', 0):+,.0f} MW"
                ),
                showarrow=True,
                arrowhead=2,
                ax=60,
                ay=-70,
                bgcolor="rgba(127, 127, 127, 0.16)",
                bordercolor=REFERENCE_LINE,
                borderwidth=1,
                font=dict(size=11),
            )
    fig.update_layout(
        title=title,
        hovermode="x unified",
        barmode="relative",
        legend_title_text="",
        xaxis_title="Bid price around clearing (JPY/kWh)",
        yaxis_title="Cumulative depth shift (MW)",
    )
    return apply_terminal_layout(fig, height=430)


def offer_stack_period_shift_chart(df: pd.DataFrame, title: str = "Offer-Stack Shift by Time Period") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=390)
    plot_df = df.copy()
    period = (
        plot_df.groupby("delivery_period", as_index=False)[["supply_tightening_mw", "demand_strength_mw", "net_tightening_pressure_mw"]]
        .mean()
        .sort_values("delivery_period")
    )
    period_order = ["Overnight", "Solar belly", "Afternoon ramp", "Evening peak", "Late peak"]
    period["delivery_period"] = pd.Categorical(period["delivery_period"], categories=period_order, ordered=True)
    period = period.sort_values("delivery_period")
    fig.add_trace(
        go.Bar(
            x=period["delivery_period"].astype(str),
            y=period["supply_tightening_mw"],
            name="Supply-side tightening",
            marker_color=RED,
            customdata=period[["delivery_period", "supply_tightening_mw"]],
            hovertemplate="Period: %{customdata[0]}<br>Supply-side tightening: %{customdata[1]:+,.0f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=period["delivery_period"].astype(str),
            y=period["demand_strength_mw"],
            name="Buy-side strength",
            marker_color=BLUE,
            customdata=period[["delivery_period", "demand_strength_mw"]],
            hovertemplate="Period: %{customdata[0]}<br>Buy-side strength: %{customdata[1]:+,.0f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=period["delivery_period"].astype(str),
            y=period["net_tightening_pressure_mw"],
            name="Net tightening pressure",
            mode="lines+markers",
            line=dict(color=AMBER, width=2.2),
            customdata=period[["delivery_period", "net_tightening_pressure_mw"]],
            hovertemplate="Period: %{customdata[0]}<br>Net tightening pressure: %{customdata[1]:+,.0f} MW<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    fig.update_layout(
        title=title,
        barmode="relative",
        legend_title_text="",
        xaxis_title="Delivery period",
        yaxis_title="Average shift at clearing (MW)",
    )
    return apply_terminal_layout(fig, height=390)


def offer_stack_price_attribution_chart(df: pd.DataFrame, title: str = "Price Move Attribution by Time Period") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title), height=390)
    plot_df = df.copy()
    period = (
        plot_df.groupby("delivery_period", as_index=False)[
            [
                "supply_price_contribution_jpy_kwh",
                "demand_price_contribution_jpy_kwh",
                "interaction_jpy_kwh",
                "price_change_jpy_kwh",
            ]
        ]
        .mean()
        .sort_values("delivery_period")
    )
    period_order = ["Overnight", "Solar belly", "Afternoon ramp", "Evening peak", "Late peak"]
    period["delivery_period"] = pd.Categorical(period["delivery_period"], categories=period_order, ordered=True)
    period = period.sort_values("delivery_period")
    traces = [
        ("Supply curve", "supply_price_contribution_jpy_kwh", RED),
        ("Demand curve", "demand_price_contribution_jpy_kwh", BLUE),
        ("Interaction", "interaction_jpy_kwh", "#8B95A1"),
    ]
    for name, col, color in traces:
        fig.add_trace(
            go.Bar(
                x=period["delivery_period"].astype(str),
                y=period[col],
                name=name,
                marker_color=color,
                customdata=period[["delivery_period", col]],
                hovertemplate=f"Period: %{{customdata[0]}}<br>{name} contribution: %{{customdata[1]:+.2f}} JPY/kWh<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=period["delivery_period"].astype(str),
            y=period["price_change_jpy_kwh"],
            name="Actual price change",
            mode="lines+markers",
            line=dict(color=AMBER, width=2.2),
            customdata=period[["delivery_period", "price_change_jpy_kwh"]],
            hovertemplate="Period: %{customdata[0]}<br>Actual price change: %{customdata[1]:+.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color=REFERENCE_LINE, line_width=1)
    fig.update_layout(
        title=title,
        barmode="relative",
        legend_title_text="",
        xaxis_title="Delivery period",
        yaxis_title="Average price move (JPY/kWh)",
    )
    return apply_terminal_layout(fig, height=390)


def intraday_convergence_chart(df: pd.DataFrame, title: str = "Day-Ahead vs Intraday Convergence") -> go.Figure:
    fig = go.Figure()
    if df.empty:
        return apply_terminal_layout(fig.update_layout(title=title))
    fig.add_trace(
        go.Scatter(
            x=df["delivery_date"],
            y=df["spot_price"],
            name="JEPX day-ahead system",
            mode="lines",
            line=dict(color=BLUE, width=2.2),
            hovertemplate="Day-ahead: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["delivery_date"],
            y=df["intraday_average_price"],
            name="Intraday average",
            mode="lines",
            line=dict(color=AMBER, width=2.2),
            hovertemplate="Intraday average: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=df["delivery_date"],
            y=df["spot_intraday_spread"],
            name="Spot minus intraday",
            marker_color=REFERENCE_LINE,
            opacity=0.42,
            yaxis="y2",
            hovertemplate="Spread: %{y:+.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        hovermode="x unified",
        xaxis_title="",
        yaxis=dict(title="JPY/kWh"),
        yaxis2=dict(title="Spread", overlaying="y", side="right", showgrid=False),
        legend_title_text="",
    )
    return apply_terminal_layout(fig, height=430)


def intraday_liquidity_heatmap(df: pd.DataFrame, value: str = "total_volume_kwh", title: str = "Intraday Liquidity by Product") -> go.Figure:
    if df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title))
    plot_df = df.copy()
    plot_df["delivery_date"] = pd.to_datetime(plot_df["delivery_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    pivot = plot_df.pivot_table(index="time_code", columns="delivery_date", values=value, aggfunc="mean")
    color_title = "Volume (kWh)" if value == "total_volume_kwh" else "Contracts"
    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="Viridis",
        title=title,
        template=PLOT_TEMPLATE,
        labels=dict(x="Delivery date", y="Time code", color=color_title),
    )
    fig.update_layout(xaxis_title="Delivery date", yaxis_title="Time code")
    fig.update_coloraxes(colorbar_title=color_title)
    return apply_terminal_layout(fig, height=430)


def baseload_price_volume_chart(df: pd.DataFrame, title: str = "JEPX Baseload Market Tracker") -> go.Figure:
    if df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title))
    plot_df = df.dropna(subset=["clearing_price_jpy_kwh"]).copy()
    fig = px.scatter(
        plot_df,
        x="trade_date",
        y="clearing_price_jpy_kwh",
        size="volume_mw",
        color="area",
        title=title,
        template=PLOT_TEMPLATE,
        custom_data=["product_name", "area", "trade_date", "clearing_price_jpy_kwh", "volume_mw", "fiscal_year"],
        labels=_labels({"clearing_price_jpy_kwh": "Clearing price", "volume_mw": "Volume (MW)"}),
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Area: %{customdata[1]}<br>"
            "Trade date: %{customdata[2]|%Y-%m-%d}<br>"
            "Price: %{customdata[3]:.2f} JPY/kWh<br>"
            "Volume: %{customdata[4]:,.1f} MW<br>"
            "Fiscal year: %{customdata[5]}"
            "<extra></extra>"
        )
    )
    fig.update_layout(xaxis_title="", yaxis_title="JPY/kWh", legend_title_text="")
    return apply_terminal_layout(fig, height=430)


def forward_curve_chart(df: pd.DataFrame, title: str = "Forward Curve") -> go.Figure:
    plot_df = df.copy()
    if plot_df.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title))
    plot_df["curve_date"] = plot_df["curve_date"].dt.strftime("%Y-%m-%d")
    if "tenor_label" in plot_df.columns:
        plot_df["contract_month_label"] = plot_df["tenor_label"]
    else:
        plot_df["contract_month_label"] = plot_df["contract_month"].dt.strftime("%b-%y")
    category_order = plot_df.sort_values("contract_month")["contract_month_label"].drop_duplicates().tolist()
    fig = px.line(
        plot_df,
        x="contract_month_label",
        y="price",
        color="curve_date",
        markers=True,
        category_orders={"contract_month_label": category_order},
        title=title,
        template=PLOT_TEMPLATE,
        hover_data=[col for col in ["market", "currency", "unit", "contract_type", "source_note"] if col in plot_df.columns],
        labels=_labels(),
    )
    latest_curve = plot_df.sort_values("curve_date").tail(len(category_order))
    if not latest_curve.empty:
        front = latest_curve.sort_values("contract_month").head(1)
        fig.add_scatter(
            x=front["contract_month_label"],
            y=front["price"],
            mode="markers",
            marker=dict(size=12, color=AMBER, symbol="diamond"),
            name="Front",
            hovertemplate="Front: %{y:.2f}<extra></extra>",
        )
    fig.update_layout(hovermode="x unified", xaxis_title="Delivery", yaxis_title=_unit_title(plot_df), legend_title_text="")
    return apply_terminal_layout(fig, height=460)


def curve_heatmap(df: pd.DataFrame, title: str) -> go.Figure:
    temp = df.copy()
    if temp.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=title))
    temp["curve_date"] = temp["curve_date"].dt.strftime("%Y-%m-%d")
    temp["contract_month"] = temp["contract_month"].dt.strftime("%Y-%m")
    pivot = temp.pivot_table(index="curve_date", columns="contract_month", values="price", aggfunc="mean")
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Viridis", title=title, template=PLOT_TEMPLATE, labels=_labels())
    fig.update_layout(xaxis_title="Contract Month", yaxis_title="Curve Date")
    fig.update_coloraxes(colorbar_title=_unit_title(df))
    return apply_terminal_layout(fig, height=400)


def duration_curve(df: pd.DataFrame, market: str) -> go.Figure:
    subset = df[df["market"] == market].copy().sort_values("price", ascending=False)
    if subset.empty:
        return apply_terminal_layout(go.Figure().update_layout(title=f"{market} Price Duration Curve"))
    subset["rank_pct"] = range(1, len(subset) + 1)
    subset["rank_pct"] = subset["rank_pct"] / len(subset) * 100
    fig = px.line(subset, x="rank_pct", y="price", title=f"{market} Price Duration Curve", template=PLOT_TEMPLATE, hover_data=["date", "price"], labels=_labels())
    for pct, label in [(10, "P10"), (50, "P50"), (90, "P90")]:
        value = subset["price"].quantile(1 - pct / 100)
        fig.add_hline(y=value, line_dash="dot", line_color=REFERENCE_LINE, annotation_text=label, annotation_position="right")
    fig.update_layout(xaxis_title="Share of observations exceeded (%)", yaxis_title=_unit_title(subset, "Price"))
    return apply_terminal_layout(fig)


def spread_chart(df: pd.DataFrame, title: str = "Spread Monitor", y_title: str = "Spread") -> go.Figure:
    fig = line_chart(df, "date", "price", "market", title, y_title)
    fig.add_hline(y=0, line_width=1.4, line_color=REFERENCE_LINE)
    return fig


def percentile_chart(df: pd.DataFrame, title: str = "Percentile Monitor") -> go.Figure:
    fig = line_chart(df, "date", "percentile_rank", "market", title, "Percentile")
    for level in [10, 25, 50, 75, 90]:
        fig.add_hline(y=level, line_dash="dot", line_color=REFERENCE_LINE, opacity=0.7)
    fig.update_yaxes(range=[0, 100])
    return fig


def temperature_power_chart(df: pd.DataFrame, region: str, title: str | None = None) -> go.Figure:
    subset = df[df["region"] == region].sort_values("date")
    fig = go.Figure()
    if subset.empty:
        return apply_terminal_layout(fig.update_layout(title=title or f"{region} Temperature vs Power"))
    fig.add_trace(
        go.Scatter(
            x=subset["date"],
            y=subset["temperature_mean_c"],
            name=f"{region} mean temp",
            mode="lines",
            line=dict(color=RED, width=2.2),
            yaxis="y",
            hovertemplate="Temp: %{y:.1f} deg C<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=subset["date"],
            y=subset["price"],
            name=f"{region} power",
            mode="lines",
            line=dict(color=BLUE, width=2.0),
            yaxis="y2",
            hovertemplate="Power: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    fig.update_layout(
        title=title or f"{region} Temperature vs Area Power",
        hovermode="x unified",
        yaxis=dict(title="deg C"),
        yaxis2=dict(title="JPY/kWh", overlaying="y", side="right", showgrid=False),
        xaxis_title="",
        legend_title_text="",
    )
    return apply_terminal_layout(fig, height=430)


def weather_scatter(df: pd.DataFrame, x: str, y: str, color: str, title: str, x_title: str, y_title: str) -> go.Figure:
    fig = px.scatter(df, x=x, y=y, color=color, title=title, template=PLOT_TEMPLATE, hover_data=["date", "region"], color_discrete_map=MARKET_COLORS, labels=_labels({x: x_title, y: y_title}))
    for region, group in df.dropna(subset=[x, y]).groupby(color):
        if len(group) < 3 or group[x].nunique() < 2:
            continue
        slope, intercept = np.polyfit(group[x], group[y], 1)
        x_line = pd.Series([group[x].min(), group[x].max()])
        fig.add_trace(
            go.Scatter(
                x=x_line,
                y=slope * x_line + intercept,
                mode="lines",
                name=f"{region} beta",
                line=dict(width=1.6, dash="dot"),
                hovertemplate=f"{region} fit<extra></extra>",
            )
        )
    fig.update_layout(xaxis_title=x_title, yaxis_title=y_title, legend_title_text="")
    return apply_terminal_layout(fig)


def srmc_comparison_chart(df: pd.DataFrame, title: str = "Fuel SRMC vs JEPX System Price") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["jcc_13_srmc"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
            name="JCC-linked gas SRMC 13%",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["jcc_11_srmc"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(255, 171, 0, 0.22)",
            name="JCC-linked gas SRMC 11-13% band",
            hovertemplate="JCC 11% SRMC: %{y:.2f} JPY/kWh<extra></extra>",
        )
    )
    traces = [
        ("coal_srmc", "Coal SRMC", COAL, "solid"),
        ("jkm_gas_srmc", "JKM gas SRMC", TEAL, "solid"),
        ("jepx_system", "JEPX system price", BLUE, "dash"),
    ]
    for column, name, color, dash in traces:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df[column],
                mode="lines",
                name=name,
                line=dict(color=color, width=2.4, dash=dash),
                hovertemplate=f"{name}: %{{y:.2f}} JPY/kWh<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        template=PLOT_TEMPLATE,
        hovermode="x unified",
        legend_title_text="",
        xaxis_title="",
        yaxis_title="JPY/kWh",
    )
    return apply_terminal_layout(fig, height=460)
