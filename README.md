# Japan Fuel & Power Market Dashboard

A professional Streamlit dashboard for Japan fuel and power market intelligence. The app is designed around LNG, power, utility, and commodity trading desk workflows: historical behavior, forward expectations, relative value, volatility regimes, regional power spreads, weather sensitivity, offer-stack structure, and trader-style signal monitoring.

This is not a calculator. It is a visualization and analytics terminal for market interpretation.

## Quick Start

```bash
cd japan_fuel_power_dashboard
pip install -r requirements.txt
streamlit run app.py
```

The app opens on the **Overview** page and loads bundled sample/processed CSVs by default. This keeps local and Streamlit Cloud startup stable without API keys or licensed feeds.

Key pages show compact source-quality badges so analysts can quickly distinguish sample, uploaded, public, processed, derived, and unavailable datasets.

## Streamlit Deployment

Deploy from Streamlit Community Cloud with:

```text
Repository: taiyu-wang/japan_power_trading_dashboard
Branch: main
Main file path: app.py
```

The repository is designed to be deployment-safe without committed secrets. Licensed data should be supplied through uploads, Streamlit secrets, or future vendor connectors rather than committed files.

### Scheduled Public Data

The application release stays on `main`. Compact public JEPX, Tokyo/Kansai weather and supply-mix, and Japan-power news artifacts are published to the separate `data` branch by `.github/workflows/refresh_public_data.yml`. Streamlit reads:

```text
https://raw.githubusercontent.com/taiyu-wang/japan_power_trading_dashboard/data/data/published
```

Remote artifacts use short TTL caches and fall back to bundled CSVs when unavailable. The freshness strip at the top of every page reports observation dates and clearly marks stale bundled historical/forward datasets.

Run the public pipeline manually:

```bash
PYTHONPATH=. python -m src.public_data_pipeline --output-dir /tmp/japan-power-published --datasets all
```

If deployment fails:

- `ModuleNotFoundError`: add the missing package to `requirements.txt`.
- `File not found`: confirm paths are relative to the repo root, such as `data/sample_historical_prices.csv`.
- Live curve timeout: leave live refresh disabled and use bundled or uploaded curves.
- Private repo unavailable: re-authorize GitHub access in Streamlit Cloud or make the repo public.
- Old repository changes do not appear: delete and redeploy the Streamlit app using the repository coordinates above.
- Freshness strip remains stale after a data-branch update: clear Streamlit cache or reboot the app.

## Documentation

- [Data Sources and Confidence Matrix](docs/data_sources.md)
- [Methodology](docs/methodology.md)
- [User Guide](docs/user_guide.md)
- [Operations and Deployment Runbook](docs/deployment.md)

## Folder Structure

```text
japan_fuel_power_dashboard/
├── app.py
├── requirements.txt
├── README.md
├── docs/
│   ├── data_sources.md
│   ├── deployment.md
│   ├── methodology.md
│   └── user_guide.md
├── data/
│   ├── raw/
│   ├── processed/
│   ├── sample_historical_prices.csv
│   ├── sample_forward_curves.csv
│   ├── sample_power_futures.csv
│   ├── sample_weather_temperatures.csv
│   ├── sample_generation_mix.csv
│   ├── sample_power_news.csv
│   └── market_mapping.csv
├── src/
├── pages/
├── notebooks/
└── tests/
```

## Dashboard Pages

- **Overview:** Daily desk read for fuels, power, FX, SRMC, forward context, and commentary.
- **Power Market:** JEPX system, Tokyo, Kansai, intraday, futures proxy, spreads, liquidity, and weather-price overlays.
- **Fuel & Dispatch:** LNG, coal, crude, FX, SRMC, fuel competitiveness, and dispatch economics.
- **Forward Curves:** Curve comparison, tenor metrics, monthly power futures, JEPX baseload auction tracker, upload workflows, and source notes.
- **Weather & Seasonality:** Tokyo/Kansai temperature, degree days, seasonal price patterns, and summer/winter comparisons.
- **Trading Signals:** Rule-based monitoring prompts with rationale, confidence, invalidation, market implication, and news context.
- **Supply Mix:** Tokyo/Kansai monthly generation share, volume, thermal dependence, upload support, and source notes.
- **Market Structure:** JEPX public ex-post bidding curves, stack tightness, price sensitivity, curve shifts, time-of-day attribution, and area-spread review.

## Data Model

Core datasets are long-form CSVs under `data/`:

- Historical prices: `date, market, region, asset_class, frequency, contract, price, currency, unit`
- Forward curves: `curve_date, contract_month, market, region, price, currency, unit`
- Power futures: `curve_date, contract_month, area, load_type, settlement_price, currency, unit, contract_type, source, source_note`
- Weather: `date, market, region, station, temperature_mean_c, temperature_max_c, temperature_min_c, cooling_degree_day, heating_degree_day, source, source_note`
- Generation mix: `month, area, generation_type, generation_gwh, source, source_note`
- Power news: `published_at, source, category, title, summary, url, market_tag, impact_hint`
- JEPX intraday: `delivery_date, time_code, opening_price_jpy_kwh, highest_price_jpy_kwh, lowest_price_jpy_kwh, last_price_jpy_kwh, average_price_jpy_kwh, total_volume_kwh, number_of_contracts, source`
- JEPX baseload: `fiscal_year, product_name, area, trade_date, clearing_price_jpy_kwh, volume_mw, source`
- JEPX offer stack: `delivery_date, time_code, area_group_code, area_group, bid_price_jpy_kwh, sell_cumulative_mw, buy_cumulative_mw, source, source_url, downloaded_at`

See [Data Sources and Confidence Matrix](docs/data_sources.md) for source reliability, refresh cadence, and production replacement paths.

## Refresh Commands

Refresh bundled synthetic sample data:

```bash
PYTHONPATH=. python -m src.sample_data
```

Refresh latest public JEPX offer-stack cache and rebuild compact deployable analytics:

```bash
PYTHONPATH=. python -m src.offer_stack
```

## Testing

```bash
python -m compileall app.py src pages tests
PYTHONPATH=. pytest
```

The test suite covers core transformations, indicators, chart labels, data upload validation, signal schema behavior, JEPX offer-stack analytics, and source-specific loaders.

## Important Caveat

Bundled sample data is synthetic or compact processed fallback data unless otherwise noted. It is useful for dashboard functionality, workflow design, and deployment stability. Production trading use requires licensed/vendor, exchange, broker, or internally validated datasets.
