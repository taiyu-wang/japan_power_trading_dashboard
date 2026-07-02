# Data Freshness and Public Pipeline Design

## Objective

Make deployed data freshness explicit and update public JEPX, weather, and news datasets independently from Streamlit application deployments.

## Architecture

The `main` branch remains the application release branch. A dedicated orphan `data` branch stores only compact published CSV artifacts and `data/published/manifest.json`. GitHub Actions checks out both branches, runs existing public-source adapters, validates outputs, and commits refreshed artifacts to `data`.

The Streamlit application reads published artifacts from:

`https://raw.githubusercontent.com/taiyu-wang/japan_power_trading_dashboard/data/data/published`

The base URL is configurable through `JAPAN_POWER_PUBLIC_DATA_URL`. Remote reads use short timeouts and TTL caching. Any unavailable, empty, or invalid remote artifact falls back to the existing bundled CSV without blocking a page.

## Published Datasets

- `weather_temperatures.csv`: Tokyo and Kansai Open-Meteo daily temperatures.
- `power_news.csv`: filtered JEPX, OCCTO, METI, and public Japan-power news.
- `jepx_intraday.csv`: current-year JEPX intraday transactions.
- `jepx_baseload.csv`: current and prior-year JEPX baseload transactions.
- `jepx_offer_stack_depth.csv`: compact depth analytics for the latest seven available days.
- `jepx_offer_stack_curves.csv`: sampled compact curves for the same period.
- `manifest.json`: publication time, source, observation coverage, row count, freshness threshold, status, and pipeline warnings.

Historical fuel and power prices and forward curves remain bundled snapshots until a reliable licensed or official feed is connected. The freshness interface must label these as stale rather than implying they are live.

## Freshness Interface

Every page renders a compact strip immediately below Streamlit configuration:

- Overall status: Current, Delayed, Stale, Partial, or Unavailable.
- Historical market data observation date.
- JEPX public pipeline observation date.
- Weather observation date.
- News observation date.

Status is evaluated from dataset-specific thresholds. The strip uses green for current, amber for delayed/partial, and red for stale/unavailable. Full source-quality panels remain page-specific.

## Refresh and Failure Behavior

Collectors are independent. Successful datasets are written atomically. If one collector fails, its previous artifact and manifest record remain in place while the new manifest records the warning. The workflow fails only if no requested collector publishes any usable artifact.

The Streamlit runtime never writes durable datasets. User uploads remain session-scoped. Scheduled refresh and publication occur only in GitHub Actions.

## Schedule

The public pipeline runs daily at 22:30 UTC, equivalent to 07:30 JST, and supports manual `workflow_dispatch`. This first release refreshes all public datasets daily; higher-frequency news refresh can be split later without changing the artifact contract.

## Validation

Each artifact must:

- Be non-empty.
- Contain its required observation-date column.
- Have at least one parseable observation date.
- Preserve required schema through the existing normalizers.
- Publish row count, coverage dates, and source metadata.

Unit tests cover freshness boundaries, manifest aggregation, atomic publication, collector failure preservation, and remote-loader fallback behavior. Existing dashboard tests must continue to pass.
