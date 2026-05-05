# market_mining Macro-First Overall Plan

`market_mining` is a macro-liquidity-first market state mining system for crypto long-cycle positioning.

The system direction is:

```text
Fed policy
-> USD net liquidity
-> Stablecoin liquidity
-> ETF / institutional flow
-> Risk appetite
-> Crypto confirmation
-> Market regime
-> Positioning suggestion
```

## v0.1 Scope

The first version establishes the Python project scaffold and data contracts needed for later steps.

Step 0 only includes:

- package structure
- configuration loading
- minimal CLI
- placeholder data schemas
- utility math helpers
- smoke tests

Step 0 does not include:

- real API connectors
- scoring logic
- market regime state machine
- backtesting
- trading execution
- exchange private API integration
- machine learning modules
