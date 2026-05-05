# market_mining Stepwise Development Plan

## 0. 项目定位

`market_mining` 是一个 **macro-liquidity-first** 的市场状态挖掘系统。

它的目标不是做一个交易机器人，也不是直接执行网格或下单，而是通过以下数据：

- 美联储政策
- 美元流动性
- 稳定币供应
- ETF / 机构资金流
- 风险偏好
- crypto 市场确认信号

生成可解释的市场状态、评分和仓位建议，供上层 `cycle_engine` 使用。

核心链路：

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

---

## 1. 总体开发原则

本项目采用 **step-by-step** 的开发方式，不采用一次性生成完整系统的 vibe coding 模式。

每一步的原则：

```text
1. 范围足够小
2. 输出可运行
3. 逻辑可审查
4. 不提前写死后续设计
5. 每一步完成后再进入下一步
```

当前阶段不做：

```text
实盘交易
自动下单
Binance API key 管理
复杂机器学习
过度抽象框架
完整回测优化
```

---

# Step 0：项目骨架初始化

## 目标

建立 `market_mining` 的最小 Python 项目结构。

本阶段只做项目骨架，不实现真实数据抓取、不实现评分系统、不实现状态机、不实现交易执行。

## 主要任务

创建基础目录结构：

```text
market_mining/
  pyproject.toml
  README.md
  configs/
    default.yaml
  docs/
    market_mining_stepwise_plan.md
  src/
    market_mining/
      __init__.py
      config.py
      logging.py
      cli.py
      data/
        __init__.py
        schemas.py
        validators.py
      features/
        __init__.py
      scores/
        __init__.py
      regimes/
        __init__.py
      positions/
        __init__.py
      utils/
        __init__.py
        math.py
  tests/
    test_import.py
    test_config.py
```

## 关键内容

- `pyproject.toml` 使用现代 Python 项目结构
- 包名：`market-mining`
- Python 版本：`>=3.10`
- 最小依赖：
  - pandas
  - numpy
  - pydantic
  - pyyaml
  - typer
  - rich
  - pytest
  - ruff

## 最小 CLI

先实现两个命令：

```bash
market-mining version
market-mining show-config --config configs/default.yaml
```

## 验收标准

```bash
python -c "import market_mining; print(market_mining.__version__)"

market-mining version

market-mining show-config --config configs/default.yaml

pytest

ruff check .
```

---

# Step 1：数据表与 Data Contract

## 目标

先定义数据结构，不急着接真实 API。

明确每类数据应该存什么、字段是什么意思、频率是什么、来源是什么。

## 核心数据表

```text
macro_policy_daily
usd_liquidity_daily
stablecoin_liquidity_daily
risk_appetite_daily
institutional_flow_daily
crypto_confirmation_daily
market_state_daily
```

## 初始 Record 类型

```text
MacroPolicyRecord
UsdLiquidityRecord
StablecoinLiquidityRecord
RiskAppetiteRecord
InstitutionalFlowRecord
CryptoConfirmationRecord
MarketStateRecord
```

## 每条记录至少包含

```text
date
source
created_at
```

后续逐步增加业务字段。

## 本阶段不做

```text
不接 FRED
不接 Treasury
不接 DeFiLlama
不接 Binance
不计算评分
不判断 regime
```

## 验收标准

- 所有 schema 可以正常 import
- 所有 Record 类型有基础校验
- validators 能检查：
  - date 是否存在
  - source 是否存在
  - 是否有重复日期
  - 时间序列是否按日期排序

---

# Step 2：接入 FRED 宏观数据

## 目标

先接入最核心的 FRED 宏观时间序列。

FRED 是 v0.1 的第一优先级数据源。

## 初始 series

建议第一批只接：

```text
DFF         # Effective Federal Funds Rate
WALCL       # Fed Balance Sheet
RRPONTSYD   # Overnight Reverse Repo
M2SL        # M2 Money Supply
DGS2        # 2-Year Treasury Yield
DGS10       # 10-Year Treasury Yield
DFII10      # 10-Year Real Yield
VIXCLS      # VIX
BAMLH0A0HYM2 # High Yield OAS
```

## 主要任务

```text
1. 新增 FRED client
2. 支持 API key 从环境变量读取
3. 支持下载单个 series
4. 支持批量下载 series
5. 保存为 CSV 或 SQLite
6. 保留原始数据，不直接覆盖
```

## 推荐目录

```text
src/market_mining/data/sources/fred.py
data/raw/fred/
```

## 本阶段不做

```text
不接 Treasury TGA
不计算 net liquidity
不做评分
不做状态机
```

## 验收标准

```bash
market-mining fetch-fred --series DFF --start 2020-01-01 --output data/raw/fred/DFF.csv

market-mining fetch-fred-batch --config configs/default.yaml
```

并确认 CSV 至少包含：

```text
date
value
series_id
source
```

---

# Step 3：接入 Treasury TGA 数据

## 目标

接入美国财政部 Daily Treasury Statement，提取 Treasury General Account / Operating Cash Balance。

TGA 是计算美元净流动性的关键变量。

## 主要任务

```text
1. 新增 Treasury FiscalData client
2. 获取 Daily Treasury Statement
3. 提取 Operating Cash Balance
4. 标准化为日频时间序列
5. 保存到 data/raw/treasury/
```

## 核心字段

```text
date
operating_cash_balance
source
created_at
```

## 初步合成指标

本阶段可以开始合成：

```text
net_liquidity = WALCL - TGA - RRP
```

注意单位必须统一。

## 本阶段不做

```text
不接稳定币
不接 ETF flow
不做完整 macro score
```

## 验收标准

```bash
market-mining fetch-treasury-tga --start 2020-01-01 --output data/raw/treasury/tga.csv

market-mining build-usd-liquidity   --fred-dir data/raw/fred   --tga data/raw/treasury/tga.csv   --output data/processed/usd_liquidity_daily.csv
```

输出至少包含：

```text
date
walcl
tga
rrp
net_liquidity
net_liquidity_30d_change
net_liquidity_90d_change
```

---

# Step 4：接入稳定币供应量

## 目标

接入 stablecoin liquidity 数据，重点观察 USDT、USDC 和总稳定币供应变化。

稳定币供应是 crypto 场内美元流动性的核心代理变量。

## 初始数据

```text
USDT supply
USDC supply
total stablecoin supply
stablecoin supply by chain
```

## 推荐来源

```text
DeFiLlama stablecoin API
```

## 主要任务

```text
1. 新增 DeFiLlama stablecoin client
2. 拉取总稳定币供应
3. 拉取 USDT / USDC 供应
4. 计算 30d / 90d change
5. 保存到 stablecoin_liquidity_daily
```

## 输出字段

```text
date
usdt_supply
usdc_supply
total_stablecoin_supply
usdt_supply_30d_change
usdt_supply_90d_change
stablecoin_supply_30d_change
stablecoin_supply_90d_change
stablecoin_liquidity_score
```

本阶段可以先不计算 `stablecoin_liquidity_score`，只保留字段占位。

## 本阶段不做

```text
不分析山寨币
不接 DEX volume
不接 DeFi TVL
不做链上地址级分析
```

## 验收标准

```bash
market-mining fetch-stablecoins --output data/raw/defillama/stablecoins.csv

market-mining build-stablecoin-liquidity   --input data/raw/defillama/stablecoins.csv   --output data/processed/stablecoin_liquidity_daily.csv
```

---

# Step 5：宏观指标计算

## 目标

把原始宏观数据转成可用于评分的指标。

本阶段只做指标，不做最终 regime。

## 核心指标

## Fed policy

```text
dff
fed_target_upper
fed_target_lower
policy_rate_change_30d
policy_rate_change_90d
```

## USD liquidity

```text
walcl
tga
rrp
net_liquidity
net_liquidity_30d_change
net_liquidity_90d_change
net_liquidity_zscore
m2_yoy
m2_3m_change
```

## Risk appetite

```text
us2y
us10y
us10y_real
yield_curve_10y_2y
hy_oas
vix
vix_30d_change
```

## Stablecoin liquidity

```text
usdt_supply_30d_change
usdt_supply_90d_change
stablecoin_supply_30d_change
stablecoin_supply_90d_change
```

## 工具函数

需要实现：

```text
pct_change
rolling_change
rolling_mean
rolling_std
zscore
minmax_score
clip
safe_divide
```

## 验收标准

```bash
market-mining build-macro-features   --usd-liquidity data/processed/usd_liquidity_daily.csv   --stablecoins data/processed/stablecoin_liquidity_daily.csv   --output data/processed/macro_features_daily.csv
```

输出应包含：

```text
date
net_liquidity_30d_change
net_liquidity_90d_change
m2_yoy
us10y_real
hy_oas
vix
stablecoin_supply_30d_change
```

---

# Step 6：评分系统

## 目标

把宏观指标压缩成几个 0~100 的可解释评分。

评分系统是 `market_mining` 的核心。

## 核心评分

```text
fed_policy_score
usd_liquidity_score
stablecoin_liquidity_score
risk_appetite_score
institutional_flow_score
crypto_confirmation_score
macro_liquidity_score
```

## v0.1 可先实现 4 个

```text
fed_policy_score
usd_liquidity_score
stablecoin_liquidity_score
risk_appetite_score
```

然后合成：

```text
macro_liquidity_score =
  0.35 * usd_liquidity_score
+ 0.25 * fed_policy_score
+ 0.20 * stablecoin_liquidity_score
+ 0.20 * risk_appetite_score
```

ETF 和 crypto confirmation 可以先占位。

## 评分原则

```text
0   = 极度不利于风险资产
50  = 中性
100 = 极度有利于风险资产
```

## 本阶段不做

```text
不做仓位函数
不做交易信号
不做自动下单
```

## 验收标准

```bash
market-mining score-macro   --features data/processed/macro_features_daily.csv   --output data/processed/macro_scores_daily.csv
```

输出至少包含：

```text
date
fed_policy_score
usd_liquidity_score
stablecoin_liquidity_score
risk_appetite_score
macro_liquidity_score
```

---

# Step 7：宏观状态机

## 目标

根据评分判断市场处于哪个宏观 regime。

状态机服务于上层 `cycle_engine`，不直接下单。

## 初始 regime

```text
macro_tightening
liquidity_drain
risk_off_deleveraging
macro_stabilization
accumulation_window
liquidity_recovery
risk_on_expansion
neutral
```

## 初始规则示例

```text
if fed_policy_score < 35 and usd_liquidity_score < 40:
    regime = "macro_tightening"

elif usd_liquidity_score < 35 and risk_appetite_score < 40:
    regime = "liquidity_drain"

elif macro_liquidity_score > 60 and stablecoin_liquidity_score > 55:
    regime = "liquidity_recovery"

elif macro_liquidity_score > 70 and risk_appetite_score > 60:
    regime = "risk_on_expansion"

elif macro_liquidity_score between 45 and 60:
    regime = "macro_stabilization"

else:
    regime = "neutral"
```

## 输出字段

```text
date
regime
macro_liquidity_score
allowed_actions
forbidden_actions
risk_level
reason
```

## 本阶段不做

```text
不做实际买卖
不接交易所账户
不输出具体订单
```

## 验收标准

```bash
market-mining detect-regime   --scores data/processed/macro_scores_daily.csv   --output data/processed/market_state_daily.csv
```

---

# Step 8：回测与可视化

## 目标

验证 `macro_liquidity_score` 和 `regime` 是否能解释 BTC 大周期。

本阶段重点不是优化收益，而是验证宏观状态是否有解释力。

## 需要叠加的数据

```text
BTC price
macro_liquidity_score
usd_liquidity_score
stablecoin_liquidity_score
regime
```

## 初始分析

```text
1. BTC price vs macro_liquidity_score
2. BTC drawdown vs usd_liquidity_score
3. stablecoin supply growth vs BTC trend
4. regime 区间背景着色
5. 不同 regime 下 BTC 未来 30/90/180 天收益分布
```

## 初始输出

```text
reports/
  macro_liquidity_vs_btc.html
  regime_forward_returns.csv
  regime_summary.md
```

## 本阶段不做

```text
不做复杂机器学习
不做自动参数优化
不做高频回测
不做网格执行回测
```

## 验收标准

```bash
market-mining analyze-btc-cycle   --market-state data/processed/market_state_daily.csv   --btc-price data/raw/crypto/btc_daily.csv   --output reports/
```

---

# 2. 推荐开发节奏

建议每一步完成后都做一次人工检查。

```text
Step 0：项目能跑
Step 1：数据结构清楚
Step 2：FRED 数据能拉
Step 3：TGA 与 net liquidity 能算
Step 4：稳定币供应能拉
Step 5：宏观指标能算
Step 6：评分逻辑可解释
Step 7：状态机输出合理
Step 8：和 BTC 周期做历史验证
```

---

# 3. 与其他项目的关系

```text
market_mining
  ↓ 输出 macro regime / liquidity score

cycle_engine
  ↓ 根据 regime 决定周期仓位

grid_trading
  ↓ 在被允许的 regime 下执行触发式网格
```

`market_mining` 不应该直接做交易。

它的边界是：

```text
输入：宏观、稳定币、ETF、crypto confirmation 数据
输出：市场状态、评分、仓位建议
```

---

# 4. 下一步

当前应从 Step 0 开始。

第一轮 Codex 任务应该只做：

```text
项目骨架
配置文件
CLI
基础 schema 占位
基础数学工具
最小测试
```

不要让 Codex 一次性实现所有模块。
