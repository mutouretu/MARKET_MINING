# market_mining

`market_mining` is a macro-liquidity-first market state mining system.

It is designed to combine signals from Federal Reserve policy, USD liquidity, stablecoin supply, ETF flows, institutional flows, and risk appetite data to produce interpretable market states for crypto long-cycle positioning.

This project is not a trading bot. It does not place orders, execute trades, manage exchange API keys, or run Binance execution logic.

The intended output is limited to:

- market states
- scores
- positioning suggestions

Current version: `v0.1 scaffold`.

## Physical Layers

The repository keeps one root project name, `market_mining`, while physically separating
responsibilities into phase-oriented root-level layers:

```text
Phase 1: data_foundation
Phase 2: feature_foundation
Phase 3: monitoring
Phase 4: statistical_analysis
Phase 5: decision_layer
```

- `data_foundation/`: data ingestion, cleaning, standardization, source clients
- `feature_foundation/`: macro, liquidity, stablecoin, BTC transmission features
- `monitoring/`: dashboard, score, regime, compact view
- `statistical_analysis/`: single-feature tests, quantiles, lag, event studies, integration models
- `decision_layer/`: overbought/oversold score, accumulation zones, directional bias

The installable package names are:

- `market_mining` (CLI/config compatibility shell, physically located under `data_foundation/`)
- `market_mining_data_mining`
- `market_mining_analysis`
- `market_mining_visualization`

The `market_mining` package keeps shared CLI/configuration and temporary compatibility imports,
but it is physically located inside `data_foundation/` so the repository root stays clean.

See `data_foundation/docs/architecture_boundaries.md` for dependency rules and non-goals.
