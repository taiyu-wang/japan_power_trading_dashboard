# Data Sources and Confidence Matrix

This dashboard intentionally separates sample, public, uploaded, and licensed/vendor data. A chart can be visually useful while still being unsuitable for production trading if the underlying source is synthetic, delayed, incomplete, or derived.

## Source Hierarchy

1. **Licensed/vendor or internally validated data:** best for production trading workflows.
2. **Uploaded broker/vendor/user CSVs:** usable when provenance and schema are controlled by the desk.
3. **Public exchange or official data:** useful for ex-post analysis, monitoring, and validation; latency and completeness vary.
4. **Derived public proxies:** useful for screening but not settlement-quality.
5. **Bundled synthetic sample data:** useful for demos, deployment, testing, and workflow design only.

Key pages also display compact source-quality badges generated from this hierarchy. They are a fast desk reminder, not a substitute for validating timestamps, settlement basis, units, and vendor lineage.

## Refresh Audit: 2026-07-02

The scheduled public-data workflow completed with ten current artifacts and no collector warnings.

| Dataset | Latest observation | Refresh status | Dashboard use |
|---|---:|---|---|
| JEPX day-ahead system/Tokyo/Kansai | 2026-07-03 delivery | Scheduled daily | Official daily averages of 48 half-hour prices |
| JEPX intraday | 2026-07-02 | Scheduled daily | Liquidity, convergence, and daily intraday price |
| JEPX offer stack | 2026-07-03 delivery | Scheduled daily | Seven-day compact ex-post curve/depth window |
| Tokyo/Kansai supply mix | 2026-06 closed month | Scheduled daily | Monthly generation shares and residual thermal |
| Tokyo/Kansai daily supply shape | 2026-07-01 | Scheduled daily | Complete 48-period days only |
| Tokyo/Kansai weather | 2026-06-27 | Scheduled daily | Open-Meteo archive snapshot with expected publication lag |
| Japan power news | 2026-06-25 | Scheduled daily | Public JEPX/OCCTO and related market context |
| JEPX baseload auction | 2026-01-30 | Scheduled daily check | Event-driven public auction history |
| Historical fuels and FX | 2026-06-08 | Static sample | Explicitly stale; replace with vendor/official feeds |
| JKM/coal/Japan power forward marks | 2026-06-08 fallback | Static or upload-required | Licensed/vendor settlement required |
| Brent/JCC-derived forward screen | 2026-07-02 | Optional on-demand | Public Brent plus derived JCC/JCC-linked proxy |

## Confidence Matrix

| Dataset / Page Use | Current Default Source | Type | Update Path | Trading Reliability | API Key / License Need | Production Replacement |
|---|---|---:|---|---:|---|---|
| Historical fuel/power/FX prices | Scheduled official JEPX overlay plus `data/sample_historical_prices.csv` fallback | Mixed public and synthetic | Daily workflow for JEPX; static fuel/FX fallback | High for JEPX public prices; low for sample fuel/FX | No for JEPX; licensed sources for production fuel/FX | Platts/Argus, ICE/CME, broker, customs, and FX feed |
| Forward curves | `data/sample_forward_curves.csv`; optional public Brent refresh | Synthetic plus derived public proxy | Bundled refresh or page toggle | Low to Medium for Brent screening only | No for public refresh; yes for production | ICE Brent, Platts JKM, CME/ICE coal, JPX/JSCC/vendor power marks |
| Japan power futures | `data/sample_power_futures.csv` | Synthetic fallback | Bundled refresh or upload | Low | No by default; yes for JSCC/vendor | JSCC paid settlement service, JPX/vendor settlement data, broker marks |
| JEPX intraday liquidity/convergence | Scheduled `jepx_intraday.csv` | Compact public processed data | Daily `jepx_market` lane | Medium-high for ex-post liquidity | No | Vendor history if lower latency/SLA is required |
| JEPX physical baseload auction tracker | Scheduled `jepx_baseload.csv` | Compact public processed data | Daily `jepx_market` check | Medium for ex-post auction context | No | Vendor history for production SLA |
| JEPX day-ahead offer stack / bidding curves | Scheduled compact curve/depth artifacts | Public ex-post processed data | Daily `offer_stack` lane | Medium for ex-post market structure | No | Exchange/member access, vendor order-book/participant/unit-level data |
| Raw JEPX offer-stack cache | `data/raw/jepx_offer_stack_latest_1m.csv` | Public ex-post raw local cache | `PYTHONPATH=. python -m src.offer_stack` | Medium for ex-post aggregate curve work | No | Same as above; keep full raw cache local |
| Weather | Scheduled Open-Meteo snapshot with bundled fallback | Public weather history | Daily `weather` lane or page refresh | Medium for public weather screening | No | JMA, ECMWF, DTN, Meteomatics, vendor forecasts/history |
| Tokyo/Kansai generation mix | Scheduled compact JapanesePower.org aggregates | Public processed with synthetic fallback | Daily `supply_mix` lane | Medium for screening | No | OCCTO/TSO/METI reconciled data, vendor generation by fuel/area |
| Power news | Scheduled public JEPX/OCCTO and related feeds | Public RSS/HTML with sample fallback | Daily `news` lane or page refresh | Medium for public context; low latency not guaranteed | No by default | Paid news/outage/vendor feeds, broker notes, internal event database |
| SRMC calculations | Derived from historical fuel, FX, and assumptions | Derived analytics | Changes with source data and sidebar assumptions | Depends on input source | No by default | Validated fuel prices, freight, heat rates, VOM, emissions, plant availability |
| Trading signals | Rule engine over dashboard data | Derived monitoring prompts | Automatic after data refresh | Depends on input source and calibration | No | Calibrated desk thresholds, validated source hierarchy, event/outage integration |

## Data Categories

### Bundled Sample Data

Bundled sample files are deterministic fallback datasets for demos, deployment, and development. They are market-shaped but synthetic. They should not be used as verified market data.

Files:

- `data/sample_historical_prices.csv`
- `data/sample_forward_curves.csv`
- `data/sample_power_futures.csv`
- `data/sample_weather_temperatures.csv`
- `data/sample_generation_mix.csv`
- `data/sample_power_news.csv`
- `data/market_mapping.csv`

### Uploaded Data

Several pages accept uploaded CSVs to override bundled data:

- Forward curves require `curve_date`, `contract_month`, `market`, and `price`.
- Power futures require `curve_date`, `contract_month`, `area`, `load_type`, and `settlement_price`.
- Supply mix requires `month`, `area`, `generation_type`, and `generation_gwh`.
- Power news accepts headline fields such as `published_at`, `source`, `category`, `title`, `summary`, `url`, `market_tag`, and `impact_hint`.

Uploaded files should be treated as desk-controlled data. The app validates schema but cannot verify commercial provenance.

### Live Public Data

Live public refresh is intentionally best-effort. Public sites can change markup, rate-limit requests, publish delayed data, or disappear behind access controls.

Current public/live lanes:

- Brent-derived forward curve screening where public data is available.
- Scheduled Open-Meteo weather refresh.
- Scheduled public power news from JEPX/OCCTO/public RSS sources.
- Scheduled JEPX day-ahead, intraday, baseload, and bidding-curve data.
- Scheduled Tokyo/Kansai compact supply-mix aggregates.

### Licensed Vendor Data

Production-grade use needs licensed or internally validated sources for:

- JKM and DES Japan LNG assessments and forwards
- Newcastle and CFR Japan coal curves
- ICE Brent settlements
- JCC official customs data and oil-linked LNG contract assumptions
- JSCC/JPX Japan power futures settlements
- JEPX historical spot/intraday/auction data at production cadence
- Outage, nuclear, generation, and weather forecasts
- Paid power/LNG/utility news

## Key Source Caveats

- **JCC:** Japan Customs-cleared Crude is a monthly customs-cleared import statistic, not an exchange-traded futures contract.
- **JCC-linked LNG:** The dashboard uses proxy slope/constant logic until contract-specific formulas are supplied.
- **Japan power futures:** Daily settlement history from April 2025 onward requires JSCC paid service or vendor access. Bundled futures are synthetic fallback unless uploaded.
- **JEPX offer stack:** Public bidding curves are ex-post aggregate curves, not a live order book, participant-level offer file, or plant-level merit-order dataset.
- **Supply mix:** The default processed view is public and scheduled. It includes only complete 48-period days and closed months, but should still be reconciled against official TSO/OCCTO/METI or vendor data for production use.
- **Signals:** Signals are monitoring prompts, not trade recommendations.

## Recommended Production Source Plan

1. Replace historical prices with licensed/vendor or official history.
2. Add JSCC/JPX/vendor Japan power futures settlement workflow.
3. Add validated JKM, DES Japan LNG, Newcastle, CFR Japan coal, Brent, JCC, and USDJPY sources.
4. Add monitoring/alerting for the scheduled JEPX, weather, news, and supply-mix workflow.
5. Reconcile scheduled public supply mix against OCCTO/TSO/METI/vendor area/fuel data.
6. Add paid news/outage/nuclear/generation feed if the Trading Signals page becomes a live desk monitor.
