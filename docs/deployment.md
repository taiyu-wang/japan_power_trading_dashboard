# Operations and Deployment Runbook

## Local Run

```bash
cd japan_fuel_power_dashboard
pip install -r requirements.txt
streamlit run app.py
```

If the local port is stale:

```bash
pkill -f "streamlit run app.py"
streamlit run app.py
```

## Streamlit Cloud

Use:

```text
Repository: taiyu-wang/japan_power_trading_dashboard
Branch: main
Main file path: app.py
```

No secrets are required for default sample-data mode.

## Refresh Bundled Sample Data

```bash
PYTHONPATH=. python -m src.sample_data
```

This refreshes synthetic fallback files:

- `data/sample_historical_prices.csv`
- `data/sample_forward_curves.csv`
- `data/sample_power_futures.csv`
- `data/sample_weather_temperatures.csv`
- `data/sample_generation_mix.csv`
- `data/sample_power_news.csv`
- `data/market_mapping.csv`

Run tests before committing refreshed sample files.

## Refresh JEPX Offer Stack

```bash
PYTHONPATH=. python -m src.offer_stack
```

This downloads the latest available public JEPX day-ahead bidding-curve month into:

```text
data/raw/jepx_offer_stack_latest_1m.csv
```

The raw file is intentionally gitignored because it is large.

The command also rebuilds deployable compact files:

```text
data/processed/jepx_offer_stack_depth.csv
data/processed/jepx_offer_stack_curves_compact.csv
```

Only compact processed files should be committed unless there is a deliberate reason to change repository storage policy.

## Test Before Push

```bash
python -m compileall app.py src pages tests
PYTHONPATH=. pytest
```

## Common Deployment Failures

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | Missing dependency | Add package to `requirements.txt` |
| `File not found` | Bad relative path or missing CSV | Confirm file exists under `data/` or `data/processed/` |
| Live curve timeout | Public source unavailable or slow | Disable live refresh; use bundled/uploaded curve |
| News refresh empty | Public source changed or no matching items | Use bundled sample, uploaded vendor CSV, or inspect `src/news.py` |
| Market Structure empty | Missing processed JEPX files or stale date selection | Rebuild offer-stack processed files or adjust date range |
| Streamlit Cloud cannot access repo | Private repo auth issue | Re-authorize GitHub or make repo public |

## GitHub Safety

Do not commit:

- `.streamlit/secrets.toml`
- API keys
- vendor credentials
- paid settlement files unless licensing allows it
- large raw caches under `data/raw/`

The `.gitignore` already excludes Streamlit secrets and raw local JEPX offer-stack cache.
