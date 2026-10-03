# Desk Workflow Upgrade

## Navigation

Six primary workflows replace overlapping standalone pages:

| Workflow | Primary question |
| --- | --- |
| Overview | Where are power prices, which feeds are current, and what needs attention? |
| Power & Liquidity | How are regional prices, intraday trading and physical liquidity evolving? |
| Market Structure | What changed in aggregate offered supply and bid demand? |
| Fuel & Margins | How do common-unit fuel costs compare with power? |
| Fundamentals | How do generation, solar shape and weather explain the regional balance? |
| Curves & Hedges | What is actually quoted, and is the contract physical or financial? |

Existing URLs are retained. Weather & Seasonality is also accessible through
Fundamentals; Trading Signals is accessible from the Overview watchlist.
Page scripts reside in `views/`, with no legacy `pages/` directory, so cold
deep links use the explicit six-workflow navigation without a startup warning.

## Analytical Safeguards

- Default preprocessing preserves raw prices, missing observations and genuine
  power spikes. Cleaning remains available through explicit opt-in functions.
- Fuel and FX marks may carry forward for four calendar days; JCC permits a
  45-day publication interval. There is no backward filling. Missing power prices
  are not synthesized. The JCC interval is a screening convention, not evidence
  that a monthly assessment is current.
- Current alerts require public, uploaded or vendor-labelled inputs no older than
  four days. Sample and unlabelled observations are excluded. These labels express
  provenance, not an independent audit of source accuracy.
- Tomorrow's JEPX delivery observations are permitted; future fuel marks are not.
- Relative performance uses common observation dates and a calendar 30-day
  baseline, with at most seven days of baseline publication slack.
- Confidence numbers remain in the engine/export for compatibility. The interface
  presents qualitative rule strength, not calibrated probability of a price move.
- Calendar season by itself does not generate an alert.
- SRMC margins are indicative screening spreads, not realized plant profitability
  or identification of the price-setting fuel.
- Relative-value subtraction is restricted to matching units. Gas versus coal is
  compared in JPY/kWh after conversion; raw USD/MMBtu minus USD/tonne is not used.

## Data Overrides

Historical uploads require `date, market, price, currency, unit`. Region,
frequency, contract and asset class have defaults. Dates normalize to dates;
prices must be finite. Duplicate date/market observations and incompatible
currency/unit combinations are rejected. Known examples:

| Market | Currency | Unit |
| --- | --- | --- |
| JKM / DES_JAPAN_LNG / JCC_LINKED_LNG | USD | MMBtu |
| JCC / BRENT | USD | bbl |
| NEWCASTLE_COAL / CFR_JAPAN_COAL | USD | tonne |
| JEPX_SYSTEM / JEPX_TOKYO / JEPX_KANSAI / JEPX_INTRADAY | JPY | kWh |
| USDJPY | JPY | JPY/USD |

Full units such as USD/MMBtu and JPY/kWh are also accepted. Historical uploads
replace the active historical dataset across pages for that browser session.
Restore public/sample history resets the override. Uploads are not persisted or
published by this application.

Forward uploads override the fuel curve dataset across pages. Manual points
remain explicitly unverified and are excluded from alerts. Synthetic, uploaded,
public and vendor data are not interchangeable.

## Offer-Curve Benchmarks

Prior-week means the actual date seven days earlier; it never silently becomes
the previous day. Benchmarks use the full available history, independently of the
display date filter. Current-day curves are excluded from their own benchmark.

Seven/30-day labels require all seven/30 delivery dates for the chosen block.
Incomplete rolling benchmarks are omitted. Selected-window benchmarks show
their observed day count. Daily curves are interpolated onto a common price grid
within their overlapping range and weighted equally by day. Compact curve
interpolation remains approximate, not a reimplementation of JEPX clearing.

Scheduled publishing accumulates up to 31 calendar days of compact offer curves
and depth, replacing revised delivery dates. New deployments may need time to
build a full 30-day benchmark. Large raw downloads remain outside GitHub.

## Deployment and Verification

Streamlit 1.57 is required for hidden legacy navigation and segmented views.
Keep the tested 1.57 patch series. A Python 3.12 CI workflow checks imports,
calculations and offline Streamlit routes; local verification also runs on 3.14.

```bash
pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

Community Cloud: repository `taiyu-wang/japan_power_trading_dashboard`, branch
`main`, entrypoint `app.py`, Python 3.12. After pulling this upgrade, reboot the
app if dependency changes have not triggered a clean rebuild. Do not regenerate
sample prices to imitate a live refresh. Check GitHub Actions and the separate
`data` branch for actual public feed updates.

Existing 15-minute public-data caches remain; sample files are cached separately.
Generation/weather views render conditionally. Shared history and curve overrides
are session-local. Published feed status is in the sidebar; actual input dates and
source classifications remain next to the relevant quotes.

## Remaining Priorities

1. Licensed dated JKM, Japan coal and oil-linked procurement inputs.
2. Plant availability and weather confirmation before stronger dispatch claims.
3. True delivery-weighted strips with explicit monthly/quarterly contract coverage.
4. Immutable artifact snapshot IDs for atomic multi-feed publication.
5. Persistent authenticated vendor uploads with appropriate licensing controls.
