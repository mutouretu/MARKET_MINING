# market_mining Architecture Boundaries

`market_mining` is one repository with phase-oriented root-level layers:

```text
data_foundation -> feature_foundation -> monitoring -> statistical_analysis -> decision_layer
```

Dependencies should follow that direction only.

## Phase 1: data_foundation/

`data_foundation/` owns data production.

Installable package: `market_mining_data_mining`

- external data source clients
- raw data downloads
- raw and processed data contracts
- field normalization
- data validation
- ingestion pipelines

`data_foundation/` must not calculate market scores, detect regimes, produce positioning suggestions, or render dashboards.

## Phase 2: feature_foundation/

`feature_foundation/` owns feature production and explanatory market state calculations.

Installable package: `market_mining_analysis`

- feature engineering
- macro liquidity scores
- risk and confirmation scores
- stablecoin and BTC transmission features
- rule-based scores
- rule-based regimes

`feature_foundation/` consumes `data_foundation/` outputs. It should not call external data APIs directly and should not render UI.

## Phase 3: monitoring/

`monitoring/` owns presentation and daily monitoring surfaces.

Installable package: `market_mining_visualization`

- static HTML reports
- dashboards
- chart layouts
- TradingView embeds
- visual summaries of feature and monitoring outputs

`monitoring/` consumes `feature_foundation/` outputs. It should not fetch raw external data, recalculate core scores, or decide regimes.

## Phase 4: statistical_analysis/

`statistical_analysis/` is reserved for single-feature tests, quantiles, lag studies, event studies, and integration models.

## Phase 5: decision_layer/

`decision_layer/` is reserved for overbought/oversold scores, monthly accumulation zones, and long/short accumulation bias.

## Compatibility Shell

`data_foundation/market_mining/` is the shared compatibility shell:

- CLI entrypoint
- shared configuration
- shared utilities
- narrow compatibility imports for older `market_mining.data.*` and `market_mining.reports.*` paths

New feature work should go into the appropriate phase layer unless it is truly shared infrastructure.

## Non-Goals

This repository does not execute trades, place orders, manage private exchange keys, or implement exchange execution logic.
