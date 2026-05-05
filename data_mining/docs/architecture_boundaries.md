# market_mining Architecture Boundaries

`market_mining` is one repository with three physically separated root-level subprojects:

```text
data_mining -> analysis -> visualization
```

Dependencies should follow that direction only.

## data_mining/

`data_mining/` owns data production.

Installable package: `market_mining_data_mining`

- external data source clients
- raw data downloads
- raw and processed data contracts
- field normalization
- data validation
- ingestion pipelines

`data_mining/` must not calculate market scores, detect regimes, produce positioning suggestions, or render dashboards.

## analysis/

`analysis/` owns market interpretation.

Installable package: `market_mining_analysis`

- feature engineering
- macro liquidity scores
- risk and confirmation scores
- regime detection
- positioning suggestions
- backtest statistics

`analysis/` consumes `data_mining/` outputs. It should not call external data APIs directly and should not render UI.

## visualization/

`visualization/` owns presentation.

Installable package: `market_mining_visualization`

- static HTML reports
- dashboards
- chart layouts
- TradingView embeds
- visual summaries of mining and analysis outputs

`visualization/` consumes `data_mining/` and `analysis/` outputs. It should not fetch raw external data, recalculate core scores, or decide regimes.

## Compatibility Shell

`data_mining/market_mining/` is the shared compatibility shell:

- CLI entrypoint
- shared configuration
- shared utilities
- narrow compatibility imports for older `market_mining.data.*` and `market_mining.reports.*` paths

New feature work should go into one of the three root-level subprojects unless it is truly shared infrastructure.

## Non-Goals

This repository does not execute trades, place orders, manage private exchange keys, or implement exchange execution logic.
