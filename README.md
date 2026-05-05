# market_mining

`market_mining` is a macro-liquidity-first market state mining system.

It is designed to combine signals from Federal Reserve policy, USD liquidity, stablecoin supply, ETF flows, institutional flows, and risk appetite data to produce interpretable market states for crypto long-cycle positioning.

This project is not a trading bot. It does not place orders, execute trades, manage exchange API keys, or run Binance execution logic.

The intended output is limited to:

- market states
- scores
- positioning suggestions

Current version: `v0.1 scaffold`.

## Physical Subprojects

The repository keeps one root project name, `market_mining`, while physically separating
responsibilities into three root-level subprojects:

```text
data_mining -> analysis -> visualization
```

- `data_mining/`: data ingestion, raw data contracts, source clients, validation
- `analysis/`: features, scores, regimes, positioning, backtest statistics
- `visualization/`: static reports, dashboards, chart presentation

The installable package names are:

- `market_mining` (CLI/config compatibility shell, physically located under `data_mining/`)
- `market_mining_data_mining`
- `market_mining_analysis`
- `market_mining_visualization`

The `market_mining` package keeps shared CLI/configuration and temporary compatibility imports,
but it is physically located inside `data_mining/` so the repository root stays clean.

See `data_mining/docs/architecture_boundaries.md` for the dependency rules and non-goals.
