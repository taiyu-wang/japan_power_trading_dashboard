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

If the repository owner, repository name, branch, or `app.py` path changes, delete the existing Streamlit app and redeploy it with the new coordinates. Community Cloud does not automatically move an existing deployment to new GitHub coordinates.

## Scheduled Public Data Branch

The scheduled workflow `.github/workflows/refresh_public_data.yml` runs daily at 22:30 UTC (07:30 JST) and can be started manually from GitHub Actions.

It checks out:

- `main` into `app/` for pipeline code.
- `data` into `published/` for durable compact artifacts.

The workflow runs:

```bash
PYTHONPATH=. python -m src.public_data_pipeline \
  --output-dir ../published/data/published \
  --datasets all
```

Only `data/published` is committed to the `data` branch. The Streamlit runtime reads those artifacts with 15-minute caching and falls back to bundled files when remote data is unavailable.

To refresh selected lanes manually:

```bash
PYTHONPATH=. python -m src.public_data_pipeline \
  --output-dir /tmp/japan-power-published \
  --datasets weather,news
```

Supported lanes are `weather`, `news`, `jepx_market`, `offer_stack`, and `supply_mix`.

The top-of-page freshness strip combines the scheduled public manifest with `data/data_manifest.json`, which describes bundled historical, forward, power-futures, and supply-mix snapshots.

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
| Code changes do not appear | Deployment still points to old GitHub coordinates | Delete and redeploy from `taiyu-wang/japan_power_trading_dashboard`, branch `main`, file `app.py` |
| Data dates do not advance | `data` workflow failed or remote manifest is unavailable | Run the workflow manually, inspect Actions logs, then reboot/clear cache |
| Public artifact fetch fails | Raw GitHub unavailable or repository is private | Use bundled fallback or configure `JAPAN_POWER_PUBLIC_DATA_URL` to an accessible artifact host |

## GitHub Safety

Do not commit:

- `.streamlit/secrets.toml`
- API keys
- vendor credentials
- paid settlement files unless licensing allows it
- large raw caches under `data/raw/`

The `.gitignore` already excludes Streamlit secrets and raw local JEPX offer-stack cache.
