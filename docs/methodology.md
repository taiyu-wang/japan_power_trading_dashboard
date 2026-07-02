# Methodology

This document summarizes the dashboard's analytical methods. The app favors trader-readable market interpretation over black-box forecasting.

## Preprocessing

- Historical prices are standardized into a long-form table by `date`, `market`, `region`, `asset_class`, `frequency`, `contract`, `price`, `currency`, and `unit`.
- Missing values are forward/back-filled by market where appropriate.
- Outliers are winsorized by market.
- Frequency conversion supports daily, weekly, monthly, and quarterly views.
- Cross-asset comparison uses normalization to `Index = 100` at the start of the selected window.

## Forward Curves

Forward curves are evaluated through:

- front-month premium
- quarterly strips
- calendar averages
- curve steepness
- rolling carry
- contango/backwardation classification
- monthly-to-quarterly tenor policy for longer-dated views

Bundled curves are synthetic fallback curves. Reliable production curves require licensed/vendor or uploaded marks.

## SRMC

Fuel short-run marginal cost is shown in `JPY/kWh`.

Gas SRMC uses:

- LNG price
- USDJPY
- plant efficiency
- variable O&M

Coal SRMC uses:

- CFR Japan delivered coal when available
- Newcastle coal as fallback/benchmark context
- default coal heat content of 6,000 kcal/kg NAR, approximately 6.978 MWh thermal per tonne before plant efficiency
- plant efficiency
- variable O&M

The dashboard includes an 11-13% JCC-linked gas SRMC band to visualize oil-linked LNG slope sensitivity.

## Spread and Relative Value

Spread analytics include:

- LNG minus coal
- LNG minus JCC-linked LNG
- Tokyo minus Kansai power
- spot minus intraday
- power minus fuel basket

Z-scores and rolling statistics are used to identify stretched relationships, but dashboard wording avoids retail-style buy/sell recommendations.

## Weather and Seasonality

Weather analytics include:

- Tokyo/Kansai daily temperature
- cooling degree days
- heating degree days
- regional temperature spread
- monthly and weekly seasonal profiles
- summer/winter regime comparison

Weather data is bundled synthetic sample data unless Open-Meteo or vendor/JMA data is connected.

## JEPX Offer-Stack Analytics

The Market Structure page uses public ex-post JEPX day-ahead aggregate bidding curves.

Core calculations:

- estimated clearing price from the closest point where sell cumulative MW and buy cumulative MW cross
- upside/downside depth around clearing within selected `JPY/kWh` bands
- tightest depth and stack regime classification
- price impact from net demand shocks such as `+500 MW` and `+1,000 MW`
- sell/buy curve shift versus a prior day or benchmark average
- time-of-day attribution across overnight, solar belly, afternoon ramp, evening peak, and late peak

Important interpretation:

- Positive sell shift means more offered depth at that price.
- Positive buy shift means stronger bid depth at that price.
- Net depth shift is `sell shift - buy shift`.
- Supply-side tightening is the inverse of sell shift: less sell depth means tighter supply.
- Buy-side strength is the buy shift.
- Net tightening pressure is `buy shift - sell shift`.

Offer-stack outputs are aggregate market-structure diagnostics. They are not participant-level bidding behavior.

## Trading Signals

Signals are rule-based monitoring prompts. Each signal includes:

- signal name
- direction
- confidence score
- rationale
- trader interpretation
- possible market implication
- invalidation condition
- supporting metrics

The signal engine is intended to explain market conditions and relationships. It does not make predictive claims and should not be treated as an automated trading recommendation.
