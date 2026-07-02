import streamlit as st
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.data_loader import (
    get_forward_curves,
    get_power_news,
    get_weather_temperatures,
    load_historical_prices,
    load_jepx_offer_stack_compact_curves,
    load_jepx_offer_stack_depth,
    load_uploaded_power_news,
)
from src.preprocessing import prepare_historical
from src.offer_stack import build_offer_stack_signal_payload
from src.signals import generate_trading_signals, signal_methodology
from src.utils import configure_page, dataframe_with_dates, download_button, page_header, sample_data_notice


configure_page("Trading Signals")

df = prepare_historical(load_historical_prices())
with st.sidebar:
    st.header("Signal Console")
    use_live_curves = st.toggle("Refresh live public curves", value=False, help="Uses bundled curves by default for deployment stability.")
    use_live_news = st.toggle(
        "Refresh live public news",
        value=False,
        help="Refreshes official JEPX/OCCTO notices and public news feeds. Bundled news remains the fallback.",
    )
    uploaded_news = st.file_uploader("Upload power news CSV", type=["csv"])

curves, curve_warnings, curve_source_label = get_forward_curves(use_live_curves)
weather, weather_warnings, weather_source_label = get_weather_temperatures(False)
signals = generate_trading_signals(df, curves, weather)
offer_stack_curves = load_jepx_offer_stack_compact_curves()
offer_stack_depth = load_jepx_offer_stack_depth()
if not offer_stack_depth.empty:
    latest_offer_stack_date = pd.to_datetime(offer_stack_depth["delivery_date"], errors="coerce").max()
    latest_offer_stack_curves = offer_stack_curves[
        pd.to_datetime(offer_stack_curves["delivery_date"], errors="coerce").eq(latest_offer_stack_date)
    ].copy()
    latest_offer_stack_depth = offer_stack_depth[
        pd.to_datetime(offer_stack_depth["delivery_date"], errors="coerce").eq(latest_offer_stack_date)
    ].copy()
    stack_signal_payload = build_offer_stack_signal_payload(latest_offer_stack_curves, depth=latest_offer_stack_depth)
else:
    stack_signal_payload = pd.DataFrame()
news, news_warnings, news_source_label = get_power_news(use_live_news)
if uploaded_news is not None:
    try:
        news = load_uploaded_power_news(uploaded_news)
        news_source_label = "Uploaded news CSV"
        news_warnings = []
        st.sidebar.success("Uploaded news loaded.")
    except ValueError as exc:
        st.sidebar.error(str(exc))

page_header(
    "Trading Signals",
    f"Rule-based desk prompts for dislocations, repricing lag, curve structure, and weather-sensitive setups. Curve source: {curve_source_label}. Weather source: {weather_source_label}. News source: {news_source_label}.",
    {
        "Historical signal inputs": "Bundled synthetic historical prices",
        "Forward curves": curve_source_label,
        "Weather": weather_source_label,
        "News": news_source_label,
        "Offer-stack signals": "Processed compact JEPX offer-stack analytics" if not offer_stack_depth.empty else "No local JEPX offer-stack CSV",
    },
)
sample_data_notice()
for warning in curve_warnings + weather_warnings:
    st.warning(warning)

if signals.empty:
    st.info("No active desk signals for the current data window. Market relationships are inside configured monitoring bands.")
else:
    cols = st.columns(4)
    cols[0].metric("Active signals", len(signals))
    cols[1].metric("Top confidence", f"{signals['confidence_score'].max():.0f}/100")
    cols[2].metric("Curve calls", int(signals["signal_name"].str.contains("Curve", case=False).sum()))
    cols[3].metric("Spread/fuel calls", int(signals["signal_name"].str.contains("LNG|Coal|Power|Tokyo|Spot", case=False).sum()))

methodology = signal_methodology()
with st.expander("How signals are generated", expanded=False):
    st.caption("Signals are deterministic rule-based desk prompts. They are not predictive model outputs or buy/sell recommendations.")
    if signals.empty:
        dataframe_with_dates(methodology, width="stretch", hide_index=True)
    else:
        active_names = set(signals["signal_name"].dropna().astype(str))
        active_methodology = methodology[methodology["signal_name"].isin(active_names)].copy()
        st.markdown("#### Active signal rulebook")
        dataframe_with_dates(active_methodology, width="stretch", hide_index=True)
        st.markdown("#### Full monitored rulebook")
        dataframe_with_dates(methodology, width="stretch", hide_index=True)
    st.caption(
        "Market-structure cards are generated separately from processed JEPX aggregate bidding-curve analytics: latest delivery date, thinnest depth blocks, and available upside shock estimates."
    )

for _, signal in signals.iterrows():
    st.markdown(
        f"""
        <div class="signal-card">
            <h4>{signal['signal_name']} | {signal['direction']}</h4>
            <div class="small-muted">Signal time: {signal['signal_time_sgt']} | Market data through: {signal['market_data_as_of']} | Confidence score: {signal['confidence_score']:.0f}/100</div>
            <p><strong>Rationale:</strong> {signal['rationale']}</p>
            <p><strong>Trader takeaway:</strong> {signal['trader_interpretation']}</p>
            <p><strong>Market implication:</strong> {signal['possible_market_implication']}</p>
            <div class="small-muted"><strong>Invalidation:</strong> {signal['invalidation']}</div>
            <div class="small-muted"><strong>Metrics:</strong> {signal['supporting_metrics']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

download_button(signals, "trading_signals.csv", "Export signals as CSV")

st.markdown("### Market-Structure Signals")
st.caption("Stack-derived prompts from public JEPX aggregate bidding curves. These are ex-post market-depth diagnostics, not participant-level offer signals.")
if stack_signal_payload.empty:
    st.info("No market-structure signal payload is available. Refresh or rebuild the JEPX offer-stack processed files.")
else:
    latest_stack_date = stack_signal_payload["delivery_date"].max()
    stack_view = stack_signal_payload[stack_signal_payload["delivery_date"].eq(latest_stack_date)].sort_values("stack_tightest_depth_mw").head(4)
    cols = st.columns(4)
    for idx, (_, item) in enumerate(stack_view.iterrows()):
        up_cols = [col for col in item.index if col.startswith("stack_price_impact_up_")]
        up_impact = item[up_cols].dropna().max() if up_cols else pd.NA
        up_text = f"{up_impact:+.2f} JPY/kWh" if pd.notna(up_impact) else "n/a"
        cols[idx].markdown(
            f"""
            <div class="signal-card">
                <h4>{item['area_group']} | Block {int(item['time_code'])}</h4>
                <div class="small-muted">Delivery: {pd.Timestamp(item['delivery_date']).date()} | {item['stack_regime']}</div>
                <p><strong>Trader takeaway:</strong> Thin depth near clearing can amplify weather, outage, and renewable forecast shocks.</p>
                <div class="small-muted"><strong>Depth:</strong> {item['stack_tightest_depth_mw']:,.0f} MW | <strong>Upside shock:</strong> {up_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("### Japan Power News Monitor")
st.caption("Official JEPX/OCCTO notices lead the public refresh; broader public feeds add market context. Upload a licensed vendor/internal CSV for production latency.")
if news_warnings:
    with st.expander("News refresh diagnostics", expanded=news_source_label == "Bundled sample news"):
        for warning in news_warnings:
            st.warning(warning)
if news.empty:
    st.info("No news items are available. Upload a CSV or enable public refresh.")
else:
    for _, item in news.head(10).iterrows():
        published = item["published_at"].strftime("%Y-%m-%d") if hasattr(item["published_at"], "strftime") else str(item["published_at"])
        url = item["url"]
        title = item["title"]
        link = f"[{title}]({url})" if url else title
        st.markdown(
            f"""
            <div class="signal-card">
                <h4>{link}</h4>
                <div class="small-muted">{published} | {item['source']} | {item['category']} | {item['market_tag']}</div>
                <p>{item['summary']}</p>
                <div class="small-muted"><strong>Desk relevance:</strong> {item['impact_hint']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    dataframe_with_dates(news, width="stretch", hide_index=True)
    download_button(news, "japan_power_news.csv", "Export news CSV")
