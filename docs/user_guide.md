# User Guide

## Overview
The daily desk entrypoint shows system, Tokyo and Kansai prices, a latest-quote
market board, dated current alerts and selected Japan power events. The board
shows each market's own observation date and source, independently of the chart
window. Missing alerts do not imply normal conditions: stale, sample and
insufficient-history inputs are excluded.

## Power & Liquidity
Monitor outright prices, regional basis, spot/intraday convergence, half-hour
liquidity and a checklist of large daily moves. Weather context is reached through
Fundamentals rather than duplicated here.

## Market Structure
Inspect public aggregate JEPX day-ahead supply and demand curves, depth around
estimated clearing, demand-shock scenarios and shifts by delivery period.
Supply, demand and net shifts have separate aligned panels. Seven/30-day
benchmarks require complete coverage; unavailable periods are not substituted.
These are ex-post diagnostics, not live orders or participant/plant bids.

## Fuel & Margins
Three views separate dispatch economics, input prices and relative value.
The dispatch view compares coal and JKM gas SRMC with JEPX system prices in
JPY/kWh and retains the shaded 11-13% JCC-linked band. LNG and coal indexed
comparisons use common observation dates; spreads use compatible units.
USD/JPY has its own input chart, separate from crude.

Default gas/coal efficiencies are 55%/40%; coal heat content is 6,000 kcal/kg
NAR. Newcastle is a FOB benchmark, not a delivered Japan cost. Freight, carbon,
startup costs and plant constraints are not included. These are screening
economics, not realized margins or identified marginal fuels.

Dated history uploaded here replaces the active historical dataset throughout
the session. The restore control removes the override.

## Fundamentals
Generation Mix combines share and GWh views, preserving the full generation
denominator when fuels are hidden. Supply Shape adds thermal dependence and
recent daily solar/ramp context. Weather & Seasonality combines regional
temperature, degree days and full-year seasonal comparisons.
Monthly generation uses closed months; recent daily shape and weather have
separate observation dates and coverage.

## Curves & Hedges
Compare dated fuel curves, monthly cash-settled power futures and the separate
physical JEPX baseload auction. Contract notes distinguish financial settlement,
physical products, analyst inputs and synthetic scenarios.
Quoted-tenor averages are not full delivery-weighted strips when contract
coverage is incomplete. A slope is not an executable carry return.

Synthetic forward scenarios are labelled. Reliable JKM and coal forwards require
licensed or desk-supplied marks. Uploaded fuel curves are shared with the signal
engine; unverified manual points do not generate current alerts.

## Shared Controls and Compatibility
Overview, Power & Liquidity, Fuel & Margins and weather share 7D, 30D, 90D,
February 2026 onward and custom analysis presets. The initial preset is 30D.
Monthly generation and forward curve vintages retain their own natural date
controls.

The previous /Weather_Seasonality and /Trading_Signals URLs still work.
Detailed signal rules and public news are reached through the Overview's
"All alerts and market news" link. Rule strength is qualitative, not forecast
probability. See [methodology](methodology.md) and [upgrade notes](upgrade_notes.md)
for calculation, provenance and upload conventions.
