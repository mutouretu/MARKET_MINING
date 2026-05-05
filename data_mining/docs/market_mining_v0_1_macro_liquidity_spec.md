# market_mining v0.1：宏观流动性优先规格文档

> 版本：v0.1 macro-liquidity-first
>
> 目标：建立一个以宏观流动性为主线的市场状态挖掘系统，用于指导 crypto 长周期仓位判断。
>
> 非目标：不自动交易，不下单，不接私有交易所 API key，不做高频策略。

---

## 1. v0.1 总目标

v0.1 需要完成：

```text
1. 建立 macro-first 项目骨架
2. 支持 FRED 数据拉取
3. 支持 Treasury FiscalData / Daily Treasury Statement 数据拉取或导入
4. 支持 stablecoin supply 数据导入/拉取
5. 支持 BTC ETF flow 数据导入
6. 支持最小 crypto confirmation 数据导入
7. 计算宏观流动性特征
8. 计算核心评分
9. 输出市场状态 regime
10. 输出仓位建议 positioning_suggestion
11. 建立最小回测框架
12. 建立第一版 Python 项目结构
```

---

## 2. v0.1 数据源

### 2.1 FRED 数据

FRED 通过 `fred/series/observations` API 获取历史观察值。所有 FRED 数据需要统一成：

```text
date
series_id
value
source
updated_at
```

v0.1 需要支持以下 series：

```yaml
fred_series:
  policy:
    DFF: Effective Federal Funds Rate
    DFEDTARU: Federal Funds Target Range - Upper Limit
    DFEDTARL: Federal Funds Target Range - Lower Limit
    SOFR: Secured Overnight Financing Rate
    IORB: Interest Rate on Reserve Balances

  liquidity:
    WALCL: Fed Total Assets
    RRPONTSYD: Overnight Reverse Repo
    WRESBAL: Reserve Balances with Federal Reserve Banks
    M2SL: M2 Money Stock

  rates_risk:
    DGS2: 2-Year Treasury Constant Maturity Rate
    DGS10: 10-Year Treasury Constant Maturity Rate
    DFII10: 10-Year Real Treasury Rate
    T10Y2Y: 10-Year Treasury Minus 2-Year Treasury
    BAMLH0A0HYM2: ICE BofA US High Yield OAS
    VIXCLS: CBOE Volatility Index

  optional_v0_2:
    CPIAUCSL: CPI
    CPILFESL: Core CPI
    PCEPI: PCE Price Index
    PCEPILFE: Core PCE
    UNRATE: Unemployment Rate
    PAYEMS: Nonfarm Payrolls
```

### 2.2 Treasury FiscalData

v0.1 需要获取或导入 Daily Treasury Statement 中的 Operating Cash Balance。

目标字段：

```text
date
tga_operating_cash_balance
tga_deposits
tga_withdrawals
```

如果 API parsing 复杂，v0.1 允许先实现 CSV importer：

```bash
market-mining import-treasury-dts --input data/manual/dts.csv
```

但 schema 必须按照后续 API 自动化设计。

### 2.3 Stablecoin Supply

v0.1 需要支持：

```text
date
usdt_supply
usdc_supply
total_stablecoin_supply
usdt_share
usdc_share
source
```

实现方式：

```text
优先：DeFiLlama API connector
备选：手动 CSV importer
```

### 2.4 BTC ETF Flow

v0.1 需要支持：

```text
date
ibit_flow
fbtc_flow
arkb_flow
bitb_flow
gbtc_flow
other_flow
btc_etf_total_flow
btc_etf_cumulative_flow
source
```

实现方式：

```text
优先：CSV importer
可选：HTML parser / external connector
```

### 2.5 Crypto Confirmation

v0.1 仅保留最小确认数据：

```text
date
btc_close
btc_ma_200
btc_return_30d
btc_drawdown_from_ath
funding_rate
open_interest
```

不要求 v0.1 完成完整 Binance connector，可以允许 CSV importer。

---

## 3. 数据表结构

### 3.1 `raw_fred_observations`

```sql
CREATE TABLE raw_fred_observations (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL,
    series_id TEXT NOT NULL,
    value REAL,
    realtime_start DATE,
    realtime_end DATE,
    source TEXT DEFAULT 'fred',
    created_at TIMESTAMP,
    UNIQUE(date, series_id)
);
```

### 3.2 `raw_treasury_dts`

```sql
CREATE TABLE raw_treasury_dts (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    tga_operating_cash_balance REAL,
    tga_deposits REAL,
    tga_withdrawals REAL,
    source TEXT DEFAULT 'treasury_fiscaldata',
    created_at TIMESTAMP
);
```

### 3.3 `raw_stablecoin_supply`

```sql
CREATE TABLE raw_stablecoin_supply (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    usdt_supply REAL,
    usdc_supply REAL,
    total_stablecoin_supply REAL,
    usdt_share REAL,
    usdc_share REAL,
    source TEXT,
    created_at TIMESTAMP
);
```

### 3.4 `raw_btc_etf_flow`

```sql
CREATE TABLE raw_btc_etf_flow (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    ibit_flow REAL,
    fbtc_flow REAL,
    arkb_flow REAL,
    bitb_flow REAL,
    gbtc_flow REAL,
    other_flow REAL,
    btc_etf_total_flow REAL,
    btc_etf_cumulative_flow REAL,
    source TEXT,
    created_at TIMESTAMP
);
```

### 3.5 `raw_crypto_confirmation`

```sql
CREATE TABLE raw_crypto_confirmation (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    btc_close REAL,
    funding_rate REAL,
    open_interest REAL,
    source TEXT,
    created_at TIMESTAMP
);
```

### 3.6 `feature_daily`

```sql
CREATE TABLE feature_daily (
    date DATE PRIMARY KEY,

    -- Fed policy
    dff REAL,
    fed_target_upper REAL,
    fed_target_lower REAL,
    sofr REAL,
    iorb REAL,
    policy_rate_change_30d REAL,
    real_yield_10y REAL,

    -- USD liquidity
    walcl REAL,
    tga REAL,
    rrp REAL,
    reserve_balances REAL,
    m2 REAL,
    net_liquidity REAL,
    net_liquidity_30d_change REAL,
    net_liquidity_90d_change REAL,
    reserve_balance_30d_change REAL,
    m2_yoy REAL,

    -- Stablecoin
    usdt_supply REAL,
    usdc_supply REAL,
    total_stablecoin_supply REAL,
    usdt_supply_30d_change REAL,
    stablecoin_supply_30d_change REAL,

    -- ETF
    btc_etf_flow_1d REAL,
    btc_etf_flow_5d REAL,
    btc_etf_flow_20d REAL,
    btc_etf_cumulative_flow REAL,

    -- Risk appetite
    us2y REAL,
    us10y REAL,
    us10y_real REAL,
    hy_oas REAL,
    vix REAL,
    yield_curve_10y2y REAL,

    -- Crypto confirmation
    btc_close REAL,
    btc_ma_200 REAL,
    btc_return_30d REAL,
    btc_drawdown_from_ath REAL,
    funding_rate REAL,
    open_interest REAL,
    open_interest_30d_change REAL
);
```

### 3.7 `score_daily`

```sql
CREATE TABLE score_daily (
    date DATE PRIMARY KEY,
    fed_policy_score REAL,
    usd_liquidity_score REAL,
    stablecoin_liquidity_score REAL,
    institutional_flow_score REAL,
    risk_appetite_score REAL,
    crypto_confirmation_score REAL,
    leverage_heat_score REAL,
    macro_liquidity_score REAL,
    crypto_risk_score REAL,
    accumulation_readiness_score REAL
);
```

### 3.8 `market_state_daily`

```sql
CREATE TABLE market_state_daily (
    date DATE PRIMARY KEY,
    regime TEXT,
    allowed_actions TEXT,
    forbidden_actions TEXT,
    spot_dca_intensity REAL,
    hedge_intensity REAL,
    long_enhancement_intensity REAL,
    grid_permission BOOLEAN,
    risk_level TEXT,
    output_json TEXT
);
```

---

## 4. 指标公式

### 4.1 基础函数

```python
pct_change(x, n) = x / x.shift(n) - 1
diff(x, n) = x - x.shift(n)
rolling_mean(x, n) = mean(x[t-n+1:t])
rolling_std(x, n) = std(x[t-n+1:t])
zscore(x, n) = (x - rolling_mean(x, n)) / rolling_std(x, n)
clip01(x) = min(max(x, 0), 1)
score01(x) = 100 * clip01(x)
```

### 4.2 Net Liquidity

```text
net_liquidity = WALCL - TGA - RRP
```

单位必须统一：

```text
WALCL: million USD
TGA: million USD
RRPONTSYD: billion USD
```

因此：

```text
rrp_million = RRPONTSYD * 1000
net_liquidity_million = WALCL - TGA - rrp_million
```

### 4.3 Net Liquidity Change

```text
net_liquidity_30d_change = pct_change(net_liquidity, 30)
net_liquidity_90d_change = pct_change(net_liquidity, 90)
```

### 4.4 M2 YoY

```text
m2_yoy = pct_change(M2SL, 365)
```

注意 M2 是月频数据，需要 forward-fill 到日频。

### 4.5 Stablecoin Supply Change

```text
usdt_supply_30d_change = pct_change(usdt_supply, 30)
stablecoin_supply_30d_change = pct_change(total_stablecoin_supply, 30)
```

### 4.6 ETF Flow Rolling Sum

```text
btc_etf_flow_5d = rolling_sum(btc_etf_total_flow, 5)
btc_etf_flow_20d = rolling_sum(btc_etf_total_flow, 20)
```

### 4.7 BTC Features

```text
btc_ma_200 = rolling_mean(btc_close, 200)
btc_return_30d = pct_change(btc_close, 30)
btc_drawdown_from_ath = btc_close / rolling_max(btc_close, all_history) - 1
open_interest_30d_change = pct_change(open_interest, 30)
```

---

## 5. 评分公式

评分公式 v0.1 采用解释性启发式，不做机器学习。

### 5.1 Fed Policy Score

压力项：

```text
rate_pressure = normalize_high_is_bad(dff, lookback=3y)
real_yield_pressure = normalize_high_is_bad(us10y_real, lookback=3y)
policy_hike_pressure = normalize_high_is_bad(policy_rate_change_30d, lookback=3y)
```

评分：

```text
fed_policy_score =
  100
- 40 * rate_pressure
- 40 * real_yield_pressure
- 20 * policy_hike_pressure
```

clip 到 `[0, 100]`。

### 5.2 USD Liquidity Score

```text
net_liq_30d_score = normalize_high_is_good(net_liquidity_30d_change, lookback=3y)
net_liq_90d_score = normalize_high_is_good(net_liquidity_90d_change, lookback=3y)
reserve_score = normalize_high_is_good(reserve_balance_30d_change, lookback=3y)
m2_score = normalize_high_is_good(m2_yoy, lookback=5y)
```

```text
usd_liquidity_score =
  35 * net_liq_30d_score
+ 35 * net_liq_90d_score
+ 15 * reserve_score
+ 15 * m2_score
```

### 5.3 Stablecoin Liquidity Score

```text
stablecoin_liquidity_score =
  45 * normalize_high_is_good(stablecoin_supply_30d_change, lookback=2y)
+ 35 * normalize_high_is_good(usdt_supply_30d_change, lookback=2y)
+ 20 * normalize_high_is_good(stablecoin_supply_90d_change, lookback=2y)
```

### 5.4 Institutional Flow Score

```text
institutional_flow_score =
  30 * normalize_high_is_good(btc_etf_flow_1d, lookback=1y)
+ 35 * normalize_high_is_good(btc_etf_flow_5d, lookback=1y)
+ 35 * normalize_high_is_good(btc_etf_flow_20d, lookback=1y)
```

### 5.5 Risk Appetite Score

```text
risk_appetite_score =
  25 * normalize_high_is_bad(-nasdaq_return_30d, lookback=3y)
+ 25 * normalize_high_is_bad(vix, lookback=3y)
+ 25 * normalize_high_is_bad(hy_oas, lookback=3y)
+ 25 * normalize_high_is_bad(us10y_real_30d_change, lookback=3y)
```

更直观地说：

```text
VIX 越低越好
HY OAS 越低越好
实际利率越不继续上行越好
纳指越稳越好
```

### 5.6 Leverage Heat Score

```text
leverage_heat_score =
  50 * normalize_high_is_bad(funding_rate, lookback=2y)
+ 50 * normalize_high_is_bad(open_interest_30d_change, lookback=2y)
```

### 5.7 Crypto Confirmation Score

```text
btc_trend_score =
  50 * indicator(btc_close > btc_ma_200)
+ 50 * normalize_high_is_good(btc_return_30d, lookback=3y)

crypto_confirmation_score =
  50 * btc_trend_score
+ 30 * (100 - leverage_heat_score)
+ 20 * normalize_high_is_good(-btc_drawdown_from_ath, lookback=3y)
```

### 5.8 Macro Liquidity Score

```text
macro_liquidity_score =
  0.30 * usd_liquidity_score
+ 0.25 * fed_policy_score
+ 0.20 * stablecoin_liquidity_score
+ 0.15 * institutional_flow_score
+ 0.10 * risk_appetite_score
```

### 5.9 Crypto Risk Score

```text
downside_momentum_score = normalize_high_is_bad(-btc_return_30d, lookback=3y)
stablecoin_drain_score = 100 - stablecoin_liquidity_score
etf_outflow_score = 100 - institutional_flow_score

crypto_risk_score =
  0.35 * leverage_heat_score
+ 0.25 * downside_momentum_score
+ 0.20 * stablecoin_drain_score
+ 0.20 * etf_outflow_score
```

### 5.10 Accumulation Readiness Score

```text
cycle_cheapness_score = normalize_high_is_good(-btc_drawdown_from_ath, lookback=3y)
macro_stabilization_score = 100 - abs(macro_liquidity_score - 55)
stablecoin_recovery_score = stablecoin_liquidity_score
leverage_clearing_score = 100 - leverage_heat_score
institutional_flow_stabilization_score = institutional_flow_score

accumulation_readiness_score =
  0.30 * cycle_cheapness_score
+ 0.25 * macro_stabilization_score
+ 0.20 * stablecoin_recovery_score
+ 0.15 * leverage_clearing_score
+ 0.10 * institutional_flow_stabilization_score
```

---

## 6. 状态机

按优先级判断。越靠前优先级越高。

### 6.1 `risk_off_deleveraging`

```python
if crypto_risk_score > 70 and crypto_confirmation_score < 45:
    regime = "risk_off_deleveraging"
```

### 6.2 `macro_tightening`

```python
elif fed_policy_score < 40 and risk_appetite_score < 45 and macro_liquidity_score < 50:
    regime = "macro_tightening"
```

### 6.3 `liquidity_drain`

```python
elif usd_liquidity_score < 40 and net_liquidity_30d_change < 0 and stablecoin_liquidity_score < 50:
    regime = "liquidity_drain"
```

### 6.4 `accumulation_window`

```python
elif accumulation_readiness_score > 60 and crypto_risk_score < 60:
    regime = "accumulation_window"
```

### 6.5 `liquidity_recovery`

```python
elif macro_liquidity_score > 60 and stablecoin_liquidity_score > 55 and institutional_flow_score > 50:
    regime = "liquidity_recovery"
```

### 6.6 `risk_on_expansion`

```python
elif macro_liquidity_score > 65 and crypto_confirmation_score > 60 and crypto_risk_score < 65:
    regime = "risk_on_expansion"
```

### 6.7 `macro_stabilization`

```python
elif fed_policy_score >= 45 and usd_liquidity_score >= 45 and stablecoin_liquidity_score >= 45 and risk_appetite_score >= 40:
    regime = "macro_stabilization"
```

### 6.8 `neutral`

```python
else:
    regime = "neutral"
```

---

## 7. 仓位建议函数

### 7.1 Sigmoid

```python
def sigmoid(x):
    return 1 / (1 + exp(-x))
```

### 7.2 Spot DCA Intensity

```text
spot_dca_intensity = sigmoid((accumulation_readiness_score - 60) / 10)
```

约束：

```text
if regime not in ["accumulation_window", "liquidity_recovery", "risk_on_expansion"]:
    spot_dca_intensity *= 0.5
```

### 7.3 Hedge Intensity

```text
hedge_intensity =
  sigmoid((crypto_risk_score - 60) / 10)
* (1 - macro_liquidity_score / 100)
```

约束：

```text
if regime in ["risk_on_expansion", "liquidity_recovery"]:
    hedge_intensity *= 0.3
```

### 7.4 Long Enhancement Intensity

```text
long_enhancement_intensity =
  sigmoid((macro_liquidity_score - 65) / 10)
* sigmoid((crypto_confirmation_score - 60) / 10)
* (1 - crypto_risk_score / 100)
```

约束：

```text
if regime != "risk_on_expansion":
    long_enhancement_intensity = 0
```

### 7.5 Grid Permission

```python
grid_permission = (
    regime == "risk_on_expansion"
    and long_enhancement_intensity > 0.25
    and crypto_risk_score < 60
)
```

---

## 8. 每日输出 Contract

```json
{
  "date": "2026-05-03",
  "regime": "macro_stabilization",
  "scores": {
    "fed_policy_score": 48.0,
    "usd_liquidity_score": 52.0,
    "stablecoin_liquidity_score": 55.0,
    "risk_appetite_score": 46.0,
    "institutional_flow_score": 51.0,
    "crypto_confirmation_score": 43.0,
    "leverage_heat_score": 58.0,
    "macro_liquidity_score": 51.7,
    "crypto_risk_score": 58.0,
    "accumulation_readiness_score": 54.0
  },
  "features": {
    "net_liquidity": 0.0,
    "net_liquidity_30d_change": 0.0,
    "stablecoin_supply_30d_change": 0.0,
    "btc_etf_flow_20d": 0.0
  },
  "allowed_actions": [
    "observe",
    "prepare_dca"
  ],
  "forbidden_actions": [
    "high_leverage_long",
    "grid_aggressive"
  ],
  "positioning_suggestion": {
    "spot_dca_intensity": 0.35,
    "hedge_intensity": 0.20,
    "long_enhancement_intensity": 0.0,
    "grid_permission": false
  }
}
```

---

## 9. 回测框架

### 9.1 回测目标

v0.1 回测不是为了优化交易收益，而是验证：

```text
宏观状态切换是否合理
macro_liquidity_score 是否领先或同步 BTC 大周期
accumulation_window 是否避开明显流动性收缩
risk_on_expansion 是否能覆盖主要上涨阶段
risk_off_deleveraging 是否能规避主要下跌阶段
```

### 9.2 数据对齐原则

```text
所有数据以 date 为主键
月频/周频数据 forward-fill 到日频
禁止使用未来数据
发布滞后数据需要在 v0.2 加 release lag
v0.1 可先按 observation date 处理，但必须标记为 limitation
```

### 9.3 回测输出

```text
date
regime
macro_liquidity_score
crypto_risk_score
spot_dca_intensity
hedge_intensity
long_enhancement_intensity
btc_return_next_30d
btc_return_next_90d
```

### 9.4 回测指标

```text
regime duration
regime transition count
average forward return by regime
max drawdown by regime
hit rate of risk_off before drawdowns
accumulation zone forward return
risk_on expansion forward return
```

---

## 10. Python 项目结构

```text
market_mining/
  README.md
  pyproject.toml

  configs/
    default.yaml
    sources.yaml

  docs/
    market_mining_macro_first_overall_plan.md
    market_mining_v0_1_macro_liquidity_spec.md

  src/
    market_mining/
      __init__.py
      cli.py
      config.py

      connectors/
        __init__.py
        fred.py
        treasury.py
        stablecoin.py
        etf_flow.py
        crypto_market.py

      schemas/
        __init__.py
        models.py
        database.py

      features/
        __init__.py
        macro_policy.py
        usd_liquidity.py
        stablecoin_liquidity.py
        institutional_flow.py
        risk_appetite.py
        crypto_confirmation.py
        build_daily.py

      scoring/
        __init__.py
        normalization.py
        scores.py

      regimes/
        __init__.py
        state_machine.py

      positioning/
        __init__.py
        suggestions.py

      backtest/
        __init__.py
        regime_backtest.py

      pipelines/
        __init__.py
        run_daily.py
        build_features.py

      utils/
        __init__.py
        dates.py
        math.py
        io.py

  examples/
    sample_fred_observations.csv
    sample_treasury_dts.csv
    sample_stablecoin_supply.csv
    sample_btc_etf_flow.csv
    sample_crypto_confirmation.csv

  tests/
    test_normalization.py
    test_usd_liquidity.py
    test_scores.py
    test_state_machine.py
    test_positioning.py
```

---

## 11. CLI 设计

```bash
market-mining show-config --config configs/default.yaml

market-mining init-db --database-url sqlite:///market_mining.db

market-mining fetch-fred \
  --config configs/default.yaml \
  --start-date 2018-01-01 \
  --end-date 2026-05-03

market-mining import-treasury-dts \
  --input examples/sample_treasury_dts.csv

market-mining import-stablecoin \
  --input examples/sample_stablecoin_supply.csv

market-mining import-etf-flow \
  --input examples/sample_btc_etf_flow.csv

market-mining import-crypto-confirmation \
  --input examples/sample_crypto_confirmation.csv

market-mining build-features \
  --output data/processed/features.csv

market-mining score \
  --input data/processed/features.csv \
  --output data/processed/scores.csv

market-mining run-daily \
  --date 2026-05-03 \
  --output data/signals/market_state_2026-05-03.json

market-mining backtest-regimes \
  --features data/processed/features.csv \
  --scores data/processed/scores.csv \
  --output outputs/backtest/regime_forward_returns.csv
```

---

## 12. 配置文件示例

```yaml
project:
  name: market_mining
  version: "0.1.0"

database:
  url: "sqlite:///market_mining.db"

sources:
  fred:
    enabled: true
    api_key_env: "FRED_API_KEY"
    series:
      - DFF
      - DFEDTARU
      - DFEDTARL
      - SOFR
      - IORB
      - WALCL
      - RRPONTSYD
      - WRESBAL
      - M2SL
      - DGS2
      - DGS10
      - DFII10
      - T10Y2Y
      - BAMLH0A0HYM2
      - VIXCLS

  treasury:
    enabled: true
    mode: "csv_first"

  stablecoin:
    enabled: true
    mode: "csv_first"

  etf_flow:
    enabled: true
    mode: "csv_first"

  crypto_confirmation:
    enabled: true
    mode: "csv_first"

scoring:
  lookbacks:
    macro_years: 3
    liquidity_years: 3
    stablecoin_years: 2
    etf_years: 1

regime_thresholds:
  macro_tightening:
    fed_policy_score_max: 40
    risk_appetite_score_max: 45
    macro_liquidity_score_max: 50

  liquidity_drain:
    usd_liquidity_score_max: 40
    stablecoin_liquidity_score_max: 50

  accumulation_window:
    accumulation_readiness_score_min: 60
    crypto_risk_score_max: 60

  liquidity_recovery:
    macro_liquidity_score_min: 60
    stablecoin_liquidity_score_min: 55
    institutional_flow_score_min: 50

  risk_on_expansion:
    macro_liquidity_score_min: 65
    crypto_confirmation_score_min: 60
    crypto_risk_score_max: 65
```

---

## 13. 数据质量检查

v0.1 必须实现：

```text
date 唯一性检查
数值列空值检查
时间序列是否单调递增
单位换算检查
WALCL / RRP / TGA 单位统一检查
ETF flow 是否能累加
稳定币供应是否非负
BTC price 是否非负
```

如果出现数据异常：

```text
不要 silently pass
必须 warning 或 raise
```

---

## 14. 单元测试要求

至少覆盖：

```text
test_net_liquidity_unit_conversion
test_pct_change
test_rolling_sum
test_score_clipping
test_macro_liquidity_score_range
test_state_machine_priority
test_positioning_intensity_range
test_grid_permission_false_outside_risk_on
```

---

## 15. v0.1 验收标准

以下命令必须通过：

```bash
python -c "import market_mining; print(market_mining.__version__)"

market-mining show-config --config configs/default.yaml

market-mining init-db --database-url sqlite:///market_mining.db

market-mining import-treasury-dts --input examples/sample_treasury_dts.csv

market-mining import-stablecoin --input examples/sample_stablecoin_supply.csv

market-mining import-etf-flow --input examples/sample_btc_etf_flow.csv

market-mining import-crypto-confirmation --input examples/sample_crypto_confirmation.csv

market-mining build-features --output data/processed/features.csv

market-mining score \
  --input data/processed/features.csv \
  --output data/processed/scores.csv

market-mining run-daily \
  --date 2026-05-03 \
  --output data/signals/market_state_2026-05-03.json

market-mining backtest-regimes \
  --features data/processed/features.csv \
  --scores data/processed/scores.csv \
  --output outputs/backtest/regime_forward_returns.csv

pytest
ruff check .
```

---

## 16. v0.2 路线

v0.2 可扩展：

```text
CME FedWatch
FOMC statement / minutes NLP
CPI/PCE/payroll surprise
real-time DeFiLlama connector
ETF flow parser automation
Glassnode / CryptoQuant stablecoin exchange reserve
Coinbase premium
BTC dominance / ETHBTC / TOTAL2
release-lag aware backtest
parameter sensitivity analysis
```
