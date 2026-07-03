# Optimization Plan: Data Pipeline & UI/UX

**Scope:** End-to-end optimization proposal covering (1) the data pipeline — ingestion,
processing, and caching — and (2) visualization / UI-UX. No behavioral change to the
analytics: every recommendation preserves the meaning of existing outputs and data
contracts.

**Status:** Proposal. Verification strategy and sequencing are included at the end.

---

## 1. Why: current bottleneck assessment

The dashboard is a multi-page Streamlit app (`app.py` + `pages/1..7`) over `src/`
modules. Streamlit re-runs the entire page script on **every** sidebar interaction
(market/date selection, SRMC sliders, live-data toggles). Three compounding cost
centers were identified by direct code inspection:

| Layer | Problem | Where |
|---|---|---|
| Ingestion | No HTTP connection reuse; serial per-day downloads; slow feeds on the interactive path | `src/offer_stack.py`, `src/news.py`, `src/live_forward_curves.py`, `src/weather.py`, `src/jepx_market_data.py` |
| Processing | O(n²)-style loops in offer-stack analytics; triple pass over half-hourly supply data; derived analytics recomputed on every rerun | `src/offer_stack.py`, `src/supply_mix_pipeline.py`, `src/indicators.py`, `src/signals.py` |
| Presentation | Every Plotly figure rebuilt per rerun; long vertical scrolls; heavy heatmap payloads | `src/charts.py`, `app.py`, `pages/*` |

Only file I/O is cached today (`@st.cache_data` in `src/data_loader.py`). The derived
analytics and all chart construction re-execute on each interaction.

A note from prior review: the suspected `@st.cache_data` "cache key collision" on
parameterized loaders is a **non-issue** — Streamlit keys the cache on function
arguments, so `load_live_weather_temperatures(start, end)` and
`load_live_jepx_offer_stack_latest_month(days)` are already correct.

---

## 2. Data pipeline optimization

### 2.1 Ingestion / network layer

**P1. Shared HTTP session with connection pooling and retries.**
All 7 outbound call sites use bare `requests.get()` (`news.py:148,183`,
`live_forward_curves.py:40`, `weather.py:81`, `jepx_market_data.py:46`,
`offer_stack.py:125,131`) — a new TCP+TLS handshake per request. Introduce one
module (e.g. `src/http_client.py`) exposing a shared `requests.Session` configured
with `HTTPAdapter(pool_connections, pool_maxsize)` and
`urllib3.util.Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])`,
and route all fetchers through it. Biggest single win for the JEPX offer-stack
refresh, which hits the same host dozens of times.

**P2. Parallelize the JEPX offer-stack month download.**
`fetch_jepx_offer_stack_range` (`offer_stack.py:890-903`) downloads up to 31 days
**serially**, and each day is 2 requests (bid curve + area mapping). At ~0.5–1 s per
request that is 30–60 s of wall time on the live toggle. Fetch days concurrently
with a bounded `ThreadPoolExecutor` (max_workers ≈ 4–6 to stay polite to JEPX),
reusing the P1 session. Keep result ordering deterministic by sorting after concat
(already done via `sort_values`).

**P3. Incremental offer-stack refresh.**
The live path re-downloads all 31 days every time the 30-min cache TTL lapses, but
JEPX history is immutable — only the newest day(s) change. Persist fetched days to
`data/raw/` (a per-day cache keyed on delivery date, which
`fetch_jepx_offer_stack_for_date` naturally supports) and only fetch dates not
already on disk. Turns a 62-request refresh into typically 2.

**P4. Keep slow feeds off the interactive path.**
`src/news.py` already parallelizes its 3 sources with `ThreadPoolExecutor` and
correctly excludes the slow METI feed (per the note at `news.py` §sources). Two
refinements: (a) reduce the per-source connect timeout budget so one hung source
cannot pin a page load near the 8 s ceiling — with P1 retries, a tighter
`timeout=(3.05, 5)` is safe; (b) fail fast in
`fetch_live_forward_curves` (`live_forward_curves.py:147-158`): return immediately
when the Brent fetch yields no rows instead of deriving JCC/JCC-linked curves from
an empty frame.

**P5. Precompute over live-compute (scheduled pipeline).**
`src/supply_mix_pipeline.py` already embodies the right pattern — fetch raw
half-hourly data offline, write processed aggregates, let the app read only
aggregates. Extend that pattern to the offer stack: run
`calculate_offer_stack_depth` / `..._price_sensitivity` in the same scheduled job
that refreshes `data/processed/jepx_offer_stack_depth.csv`, so page 7 renders from
precomputed artifacts by default and only computes live when the user explicitly
refreshes.

### 2.2 Processing layer

**P6. Fix the offer-stack hot loops (largest CPU win).**
- `calculate_offer_stack_scenarios` (`offer_stack.py:307-335`) calls
  `prepare_offer_stack_curve(work, ...)` with the **full** DataFrame inside a
  per-row loop over depth results — re-filtering the whole frame once per
  (date, time_code, area) row. Restructure to group once and pass each group,
  exactly as `calculate_offer_stack_depth` (line 279) already does.
- `calculate_offer_stack_depth` (lines 284-288) and
  `calculate_offer_stack_price_sensitivity` (lines 364-399) perform repeated
  `(curve["bid_price_jpy_kwh"] - x).abs().idxmin()` scans — 3+ full passes per
  group. The curve is monotone in price after preparation, so replace these with a
  single `np.searchsorted` on the price array (the interpolation-based
  `sample_offer_stack_curves` at line 827 already uses the vectorized
  `np.interp` idiom to copy).

**P7. Single-pass supply-mix aggregation.**
`build_processed_supply_mix_artifacts` (`supply_mix_pipeline.py:206-210`) runs three
aggregations (`aggregate_monthly_generation_mix`, `aggregate_daily_supply_shape`,
`aggregate_residual_thermal`), each starting with `df.copy()` and re-deriving
`month`, `_positive_gwh`, and thermal/clean column sums over the same half-hourly
rows. Compute the shared derived columns (**month, thermal_mw, clean_supply_mw,
per-fuel positive GWh**) once on the raw frame, then run the three groupbys off
that single enriched frame. This is a batch job, so the win is pipeline runtime
and memory, not page latency — but it also removes 2 of the 3 full-frame copies.

**P8. Cache derived analytics, not just file loads.**
Wrap the deterministic DataFrame-in/DataFrame-out computations in `@st.cache_data`
(thin wrappers in `data_loader.py`, keeping the underlying functions pure):
- `calculate_srmc_comparison` (`src/indicators.py`; re-run on every SRMC slider move
  in `app.py:75` and the Fuel page)
- `generate_market_commentary` and signal rollups (`src/signals.py`)
- `calculate_offer_stack_depth` / `..._scenarios` / `..._price_sensitivity`
- `rolling_volatility` (`src/transformations.py`)
Hashing the small bundled frames is negligible next to recompute cost.

**P9. Faster, leaner loads.**
- Add `dtype` hints and `usecols` to the `pd.read_csv` calls in `data_loader.py`
  (e.g. categorical `market`, `region`, `asset_class` on
  `load_historical_prices`, line 54) — cuts parse time and memory.
- Write the scheduled-pipeline artifacts (`data/processed/*.csv`) as **Parquet**
  alongside CSV (pyarrow is already a dependency): typed, compressed, ~5-10×
  faster to load; keep CSV for human inspection/diffs.
- Rationalize cache TTLs in `data_loader.py` behind named constants
  (`LIVE_MARKET_TTL = 1800`, `NEWS_TTL = 900`) with a one-line rationale each, so
  the 900/1800 split is a documented decision instead of scattered literals.

**P10. Trim defensive `.copy()` on hot paths** *(low priority, after P6-P8).*
Chart builders and transforms copy defensively (`charts.py`, `preprocessing.py`,
`indicators.py`). With P8 caching in place most rebuilds disappear; then drop
copies where functions only derive new columns into fresh frames.

---

## 3. UI/UX optimization

**U1. Centralized chart rendering.**
Add `render_chart(fig, **opts)` in `src/utils.py` and route all
`st.plotly_chart(...)` calls through it, passing a lean
`config={"displayModeBar": "hover", "displaylogo": False, "responsive": True}` and
the shared `width="stretch"`. One place to control mode-bar, height rhythm, and
responsiveness — removes boilerplate repeated across `app.py` and all 7 pages, and
trims per-chart JS overhead.

**U2. Tabbed layouts on dense pages.**
`pages/1_Power_Market.py`, `pages/2_Fuel_Dispatch.py`, and
`pages/7_Market_Structure.py` stack 4-6 full-height charts in one scroll. Group
related views under `st.tabs(...)` (e.g. Prices / Spreads / Intraday / Weather).
Pairs with P8: Streamlit still executes all tab code, so caching carries the
compute, while tabs cut the simultaneous DOM/WebGL load and give a cleaner desk
layout.

**U3. Lighter heatmap payloads.**
- `heatmap()` (`charts.py:147`) renders `text_auto=".2f"` in every cell; gate the
  annotation on matrix size (annotate only when `rows × cols` is small, e.g. ≤ 200).
- Pivot heatmaps (`offer_stack_depth_heatmap:340`,
  `intraday_liquidity_heatmap:744`, `curve_heatmap:832`) have no column cap; when
  many delivery dates exist the figure gets wide and heavy. Cap or aggregate the
  date axis to the selected window before `pivot_table`.

**U4. KPI strip polish (`app.py:57-64`).**
The 7-column `st.metric` row wraps awkwardly at narrow widths. Move to bordered
metric cards (`st.container(border=True)`) in a 4+3 or two-row arrangement with
consistent delta semantics (the current `"{x}% 30d"` string reads as a plain
delta), optionally with an inline sparkline per market.

**U5. Loading and empty states.**
- Live-data toggles fetch synchronously with no feedback; wrap live loads in
  `st.spinner("Refreshing JEPX offer stack…")` so pages don't appear frozen
  (especially page 7 before P2/P3 land).
- Empty-figure branches already return a titled empty figure; add a short
  `st.info` next to them explaining *why* and the remedy ("Enable live JEPX
  refresh or upload data").

**U6. Color & accessibility pass.**
Audit the diverging scales used for tightness/sensitivity heatmaps
(`RdYlGn` at `charts.py:344` is not colorblind-safe; prefer `RdBu`/viridis-family
or another CVD-safe diverging scale). Keep and document the existing semantic
convention (red = tightening / price-up, blue = easing) via the shared color
constants in `charts.py`.

**U7. Consistent number/unit formatting.**
Units (JPY/kWh, MW, GWh, %) and precision are set per-chart in hovertemplates.
Lift a small formatting helper set into `src/utils.py` and apply uniformly to
hovertemplates and axis titles.

---

## 4. Sequencing & expected impact

| Phase | Items | Expected impact |
|---|---|---|
| 1 | **P6 + P8** (offer-stack loops, analytics caching) | Largest interactive-latency win; page 7 and SRMC sliders become near-instant on repeat interaction |
| 2 | **P1 + P2 + P4** (session, parallel month fetch, fail-fast) | Live offer-stack refresh from ~30-60 s to a few seconds; news/curves toggles stop stalling pages |
| 3 | **U1 + U2** (render helper, tabs) | Cleaner layout, lighter DOM; unlocks U3/U6 cleanly |
| 4 | **P3 + P5 + P9** (incremental fetch, precomputed artifacts, Parquet/dtypes) | Pipeline robustness + cold-start load time |
| 5 | **U3-U7, P7** (visual polish, single-pass supply mix) | Polish + batch-job runtime |
| 6 | **P10** (copy cleanup) | Lowest risk/reward, last |

---

## 5. Verification

- **Tests:** `PYTHONPATH=. pytest` — the existing suite covers indicators,
  offer_stack, charts, signals, news. The P6 refactor must keep
  `tests/test_offer_stack*.py` green; add a regression asserting the
  `searchsorted`-based depth equals the prior `idxmin` result on a fixture curve.
- **Behavioral parity:** snapshot outputs of `calculate_offer_stack_depth`,
  `calculate_offer_stack_price_sensitivity`, `calculate_srmc_comparison`, and the
  three supply-mix aggregates before/after; assert frame equality (analytics
  meaning must not change).
- **Network changes:** unit-test the shared session/retry config with mocked
  responses; verify the parallel month fetch returns the identical concatenated
  frame as the serial version for a fixed set of mocked days.
- **Manual run:** `streamlit run app.py`; exercise market/date/SRMC controls on
  Overview, Fuel & Dispatch, and Market Structure. Confirm cache hits on second
  interaction, tab rendering, spinner on live refresh, heatmap annotation gating,
  and no color/unit regressions.
- **Profiling:** time the offer-stack calls and the live month fetch before/after
  (simple `time.perf_counter` bracket) to quantify P2/P6.

## Critical files

- `src/offer_stack.py` — P2, P3, P6 (hot loops, fetch parallelism)
- `src/http_client.py` *(new)* + `src/news.py`, `src/live_forward_curves.py`, `src/weather.py`, `src/jepx_market_data.py` — P1, P4
- `src/supply_mix_pipeline.py` — P5, P7
- `src/data_loader.py` — P8 wrappers, P9 dtypes/TTL constants
- `src/indicators.py`, `src/signals.py`, `src/transformations.py` — P8 targets
- `src/charts.py` — U3, U6
- `src/utils.py` — U1, U7
- `app.py`, `pages/1_Power_Market.py`, `pages/2_Fuel_Dispatch.py`, `pages/7_Market_Structure.py` — U2, U4, U5
