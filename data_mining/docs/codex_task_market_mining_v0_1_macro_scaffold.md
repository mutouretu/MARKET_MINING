# Codex 任务：重写 market_mining v0.1 为 Macro-Liquidity-First Scaffold

> 任务目标：根据新的 macro-first 方向，生成 `market_mining` 第一版项目骨架。
>
> 重要：这是数据挖掘与市场状态分析系统，不是交易机器人。不要实现实盘下单，不要接交易所私有 API，不要保存 API secret。

---

## 1. 背景

项目名：`market_mining`

项目定位：

```text
A macro-liquidity-first market mining system for crypto positioning.
```

系统主线：

```text
Fed policy
→ USD net liquidity
→ Stablecoin liquidity
→ ETF / institutional flow
→ Risk appetite
→ Crypto confirmation
→ Market regime
→ Positioning suggestion
```

本轮实现只做工程地基：

```text
项目骨架
配置文件
数据 schema
CSV importer
FRED connector
宏观特征计算
评分模块
状态机
仓位建议
最小回测
单元测试
CLI
```

禁止实现：

```text
实盘下单
交易所私有 API key
自动交易
完整网格执行
复杂机器学习
深度学习
过度工程化调度系统
```

---

## 2. 必须创建的目录结构

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

## 3. Python 包要求

使用：

```text
python >= 3.10
pandas
numpy
pydantic
sqlalchemy
typer
pyyaml
requests
pytest
ruff
```

不要引入复杂依赖。

---

## 4. CLI

实现以下命令：

```bash
market-mining show-config --config configs/default.yaml

market-mining init-db --database-url sqlite:///market_mining.db

market-mining fetch-fred \
  --config configs/default.yaml \
  --start-date 2018-01-01 \
  --end-date 2026-05-03 \
  --output data/raw/fred_observations.csv

market-mining import-treasury-dts \
  --input examples/sample_treasury_dts.csv \
  --output data/raw/treasury_dts.csv

market-mining import-stablecoin \
  --input examples/sample_stablecoin_supply.csv \
  --output data/raw/stablecoin_supply.csv

market-mining import-etf-flow \
  --input examples/sample_btc_etf_flow.csv \
  --output data/raw/btc_etf_flow.csv

market-mining import-crypto-confirmation \
  --input examples/sample_crypto_confirmation.csv \
  --output data/raw/crypto_confirmation.csv

market-mining build-features \
  --fred data/raw/fred_observations.csv \
  --treasury data/raw/treasury_dts.csv \
  --stablecoin data/raw/stablecoin_supply.csv \
  --etf-flow data/raw/btc_etf_flow.csv \
  --crypto data/raw/crypto_confirmation.csv \
  --output data/processed/features.csv

market-mining score \
  --input data/processed/features.csv \
  --output data/processed/scores.csv

market-mining run-daily \
  --features data/processed/features.csv \
  --scores data/processed/scores.csv \
  --date 2026-05-03 \
  --output data/signals/market_state_2026-05-03.json

market-mining backtest-regimes \
  --features data/processed/features.csv \
  --scores data/processed/scores.csv \
  --output outputs/backtest/regime_forward_returns.csv
```

---

## 5. 数据模型

实现 SQLAlchemy models，但 v0.1 的 pipeline 可以先用 CSV 跑通。

需要建表：

```text
raw_fred_observations
raw_treasury_dts
raw_stablecoin_supply
raw_btc_etf_flow
raw_crypto_confirmation
feature_daily
score_daily
market_state_daily
```

字段按照 `market_mining_v0_1_macro_liquidity_spec.md` 实现。

---

## 6. FRED Connector

文件：`connectors/fred.py`

要求：

```text
输入 series_id、start_date、end_date、api_key
调用 FRED series observations API
返回 pandas DataFrame:
  date
  series_id
  value
  realtime_start
  realtime_end
```

处理：

```text
"." 或空字符串转 NaN
date 转 datetime/date
value 转 float
API error 给出清晰异常
```

---

## 7. CSV Importers

实现以下 importer：

```text
connectors/treasury.py
connectors/stablecoin.py
connectors/etf_flow.py
connectors/crypto_market.py
```

每个 importer 要：

```text
读取 CSV
标准化列名
检查 date
检查重复日期
检查数值列
输出标准化 DataFrame
```

---

## 8. 特征计算

### 8.1 `features/usd_liquidity.py`

实现：

```python
net_liquidity = WALCL - TGA - RRPONTSYD * 1000
net_liquidity_30d_change
net_liquidity_90d_change
reserve_balance_30d_change
m2_yoy
```

注意单位：

```text
WALCL: million USD
TGA: million USD
RRPONTSYD: billion USD
RRPONTSYD must be multiplied by 1000
```

### 8.2 `features/stablecoin_liquidity.py`

实现：

```python
usdt_supply_30d_change
usdt_supply_90d_change
stablecoin_supply_30d_change
stablecoin_supply_90d_change
```

### 8.3 `features/institutional_flow.py`

实现：

```python
btc_etf_flow_1d
btc_etf_flow_5d
btc_etf_flow_20d
btc_etf_cumulative_flow
```

### 8.4 `features/crypto_confirmation.py`

实现：

```python
btc_ma_200
btc_return_30d
btc_drawdown_from_ath
open_interest_30d_change
```

---

## 9. 评分模块

### 9.1 `scoring/normalization.py`

实现：

```python
rolling_zscore(series, window)
rolling_percentile_score(series, window, high_is_good=True)
clip_score(series)
safe_pct_change(series, periods)
safe_rolling_sum(series, window)
```

要求所有 score 输出范围 `[0, 100]`。

### 9.2 `scoring/scores.py`

实现：

```python
compute_fed_policy_score(df)
compute_usd_liquidity_score(df)
compute_stablecoin_liquidity_score(df)
compute_institutional_flow_score(df)
compute_risk_appetite_score(df)
compute_leverage_heat_score(df)
compute_crypto_confirmation_score(df)
compute_macro_liquidity_score(df)
compute_crypto_risk_score(df)
compute_accumulation_readiness_score(df)
compute_all_scores(df)
```

使用 spec 中公式。

---

## 10. 状态机

文件：`regimes/state_machine.py`

实现：

```python
class Regime(str, Enum):
    RISK_OFF_DELEVERAGING = "risk_off_deleveraging"
    MACRO_TIGHTENING = "macro_tightening"
    LIQUIDITY_DRAIN = "liquidity_drain"
    ACCUMULATION_WINDOW = "accumulation_window"
    LIQUIDITY_RECOVERY = "liquidity_recovery"
    RISK_ON_EXPANSION = "risk_on_expansion"
    MACRO_STABILIZATION = "macro_stabilization"
    NEUTRAL = "neutral"
```

实现：

```python
class RegimeOutput(BaseModel):
    date: date
    regime: Regime
    allowed_actions: list[str]
    forbidden_actions: list[str]
    risk_level: str
```

判断优先级按照 spec：

```text
risk_off_deleveraging
macro_tightening
liquidity_drain
accumulation_window
liquidity_recovery
risk_on_expansion
macro_stabilization
neutral
```

---

## 11. 仓位建议

文件：`positioning/suggestions.py`

实现：

```python
def sigmoid(x: float) -> float

def compute_spot_dca_intensity(row) -> float
def compute_hedge_intensity(row) -> float
def compute_long_enhancement_intensity(row) -> float
def compute_grid_permission(row, regime) -> bool
def build_positioning_suggestion(row, regime) -> dict
```

约束：

```text
所有 intensity 输出范围 [0, 1]
risk_on_expansion 之外 long_enhancement_intensity = 0
risk_on_expansion 之外 grid_permission = false
```

---

## 12. 回测

文件：`backtest/regime_backtest.py`

实现最小版本：

```python
def attach_forward_returns(features, horizons=(30, 90)):
    ...
```

输出：

```text
date
regime
macro_liquidity_score
crypto_risk_score
btc_return_fwd_30d
btc_return_fwd_90d
```

再按 regime 聚合：

```text
regime
count
avg_forward_return_30d
avg_forward_return_90d
median_forward_return_30d
median_forward_return_90d
```

不要做策略收益优化。

---

## 13. 示例数据

生成足够跑通 CLI 的 sample CSV：

```text
examples/sample_fred_observations.csv
examples/sample_treasury_dts.csv
examples/sample_stablecoin_supply.csv
examples/sample_btc_etf_flow.csv
examples/sample_crypto_confirmation.csv
```

至少覆盖 300 个日历日，方便计算 200 日均线、90 日变化等。

可以用合成数据，但字段必须真实。

---

## 14. 测试要求

必须通过：

```bash
pytest
ruff check .
```

至少实现：

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

## 15. 验收标准

以下命令必须能跑通：

```bash
python -c "import market_mining; print(market_mining.__version__)"

market-mining show-config --config configs/default.yaml

market-mining init-db --database-url sqlite:///market_mining.db

market-mining import-treasury-dts \
  --input examples/sample_treasury_dts.csv \
  --output data/raw/treasury_dts.csv

market-mining import-stablecoin \
  --input examples/sample_stablecoin_supply.csv \
  --output data/raw/stablecoin_supply.csv

market-mining import-etf-flow \
  --input examples/sample_btc_etf_flow.csv \
  --output data/raw/btc_etf_flow.csv

market-mining import-crypto-confirmation \
  --input examples/sample_crypto_confirmation.csv \
  --output data/raw/crypto_confirmation.csv

market-mining build-features \
  --fred examples/sample_fred_observations.csv \
  --treasury data/raw/treasury_dts.csv \
  --stablecoin data/raw/stablecoin_supply.csv \
  --etf-flow data/raw/btc_etf_flow.csv \
  --crypto data/raw/crypto_confirmation.csv \
  --output data/processed/features.csv

market-mining score \
  --input data/processed/features.csv \
  --output data/processed/scores.csv

market-mining run-daily \
  --features data/processed/features.csv \
  --scores data/processed/scores.csv \
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

## 16. 实现注意事项

1. 不要把 `market_mining` 写成交易 bot。
2. 不要实现真实下单。
3. 不要要求 Binance API key。
4. 所有评分必须可解释。
5. 所有阈值放入 config。
6. 所有输出必须可以被 `cycle_engine` 读取。
7. 所有数据处理必须避免未来函数。
8. 月频和周频数据可以 forward-fill，但要在代码注释中说明 limitation。
9. 真实 release lag 放到 v0.2。
10. 数据缺失时要 warning，不要静默吞掉。
