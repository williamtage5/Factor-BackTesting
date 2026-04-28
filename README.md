# Factor BackTesting

现在我已经得到了使用IC加权的一段时间的SH300的股票的因子值，现在我想要去做相关的回测内容。

现在已有的内容：
* 日频因子

还需要的内容：
* A股个股日线行情（为了能够回测）
    键：TRADE_DT, S_INFO_WINDCODE
    字段：OPEN/HIGH/LOW/CLOSE
    同时拉：ADJFACTOR（或直接前复权价）、VOLUME, AMOUNT
    用途：计算策略收益、换仓成交价、波动率/Calmar
* 沪深300指数日线（为了能够对比）
    代码：000300.SH
    字段：TRADE_DT, CLOSE
    用途：基准净值曲线与对比指标
* 交易状态约束（约束）
    停牌标记
    ST/退市风险标记
    涨跌停状态
    用途：避免回测“买得到/卖得出”的假设过于乐观



# 1 Data request

## 1.1 A股个股日线行情

时间区间和股票池固定为data\2023example\synthesized_factors中的每个交易日和每天的股票池。这个部分的数据请求严格与给出的因子的交易日和每天的因子池严格对齐。

每个日文件存在：1_data_request\1.1_OHLC\output\ohlc_daily_2023example。

下面的详细解释：
| 名称 | 含义 | 来源（Wind 表） |
|---|---|---|
| `trade_date` | 交易日（YYYYMMDD） | `ASHAREEODPRICES.TRADE_DT`（并与因子壳子日期对齐） |
| `stock_code` | 股票代码（WindCode，如 `000001.SZ`） | `ASHAREEODPRICES.S_INFO_WINDCODE`（并与因子壳子股票池对齐） |
| `open` | 当日开盘价（未复权） | `ASHAREEODPRICES.S_DQ_OPEN` |
| `high` | 当日最高价（未复权） | `ASHAREEODPRICES.S_DQ_HIGH` |
| `low` | 当日最低价（未复权） | `ASHAREEODPRICES.S_DQ_LOW` |
| `close` | 当日收盘价（未复权） | `ASHAREEODPRICES.S_DQ_CLOSE` |
| `volume` | 当日成交量 | `ASHAREEODPRICES.S_DQ_VOLUME` |
| `amount` | 当日成交额 | `ASHAREEODPRICES.S_DQ_AMOUNT` |
| `adjfactor` | 复权因子 | `ASHAREEODPRICES.S_DQ_ADJFACTOR` |
| `adj_open` | 当日开盘价（复权） | `ASHAREEODPRICES.S_DQ_ADJOPEN` |
| `adj_high` | 当日最高价（复权） | `ASHAREEODPRICES.S_DQ_ADJHIGH` |
| `adj_low` | 当日最低价（复权） | `ASHAREEODPRICES.S_DQ_ADJLOW` |
| `adj_close` | 当日收盘价（复权） | `ASHAREEODPRICES.S_DQ_ADJCLOSE` |
| `trade_status` | 交易状态（如“交易”） | `ASHAREEODPRICES.S_DQ_TRADESTATUS` |
| `trade_status_code` | 交易状态代码 | `ASHAREEODPRICES.S_DQ_TRADESTATUSCODE` |
| `limit_flag` | 涨跌停相关标记值 | `ASHAREEODPRICES.S_DQ_LIMIT` |
| `stopping_flag` | 停牌相关标记值 | `ASHAREEODPRICES.S_DQ_STOPPING` |
| `missing_any_before_impute` | 填充前关键字段是否有缺失 | 非 Wind 原始字段（脚本生成） |
| `is_imputed` | 该行是否发生过缺失填充 | 非 Wind 原始字段（脚本生成） |
| `impute_reason` | 填充原因说明（如 `volume_zero`） | 非 Wind 原始字段（脚本生成） |

补充：最终 CSV 的主键是 `trade_date + stock_code`，是“先按因子壳子建键，再从 `ASHAREEODPRICES` 回填”。


# 1.2 沪深300指数日线

依据因子值的日期序列获取SH.300的收盘价。交易日必须与 data\2023example\synthesized_factors 的日期集合严格对齐，避免基准和策略错位。

最后每天的沪深300指数日线存在：1_data_request\1.2_SH.300\output\hs300_2023example\hs300_daily.csv。

具体细节如下：
| 名称 | 含义 | 来源（Wind 表） |
|---|---|---|
| `trade_date` | 交易日（YYYYMMDD） | 主体来自 `AINDEXEODPRICES.TRADE_DT`，并与因子交易日壳子对齐 |
| `index_code` | 指数代码（固定 `000300.SH`） | `AINDEXEODPRICES.S_INFO_WINDCODE`（缺失时脚本回填 `000300.SH`） |
| `close` | 沪深300当日收盘价 | `AINDEXEODPRICES.S_DQ_CLOSE` |
| `missing_before_impute` | 填充前 `close` 是否缺失 | 非 Wind 原始字段（脚本生成） |
| `is_imputed` | 该行是否发生缺失填充 | 非 Wind 原始字段（脚本生成） |
| `impute_reason` | 填充原因（`none`/`close_ffill`/`close_bfill`/`unresolved`） | 非 Wind 原始字段（脚本生成） |


# 1.3 获取交易状态约束

目的不是还原所有交易细节，而是避免回测高估可成交性。

在计算可交易状态的时候分为可买和可卖。最终仍然严格遵守援引自的交易日和股票池。

主要考虑下面三种情况：

* 停牌
  * 判定条件（发生一个就记为is_suspended为1）
    * 条件 A：stopping_flag 指示停牌。
    * 条件 B：trade_status 不属于“正常交易”状态。
    * 如果都缺失，保险起见取停牌。
* 退市和风险
  * 判定条件
    * 条件 A：当日不落在 ST 生效区间。
    * 条件 B：命中退市/退市整理/已退市风险标记。
* 涨跌停
  * 判定条件：
    * 若 close 非常接近或等于 S_DQ_LIMIT，说明收盘封在涨停边上，买入通常不可达，记 is_limit_up=1。
      * 公式为：close >= S_DQ_LIMIT * (1 - eps)
    * 若 close 非常接近或等于 S_DQ_STOPPING，说明收盘封在跌停边上，卖出通常不可达，记 is_limit_down=1。
      * 公式为：close <= S_DQ_STOPPING * (1 + eps)
    * eps默认取0.0005。
* 为此可买卖的条件设置为：
  * can_buy = 0 if is_suspended=1 or is_limit_up=1 or is_st_risk=1, else 1。
  * can_sell = 0 if is_suspended=1 or is_limit_down=1 or is_st_risk=1, else 1。


详细信息如下：
| 名称 | 含义 | 来源（Wind 表） |
|---|---|---|
| `trade_date` | 交易日（YYYYMMDD） | 主键壳子来自 `data/2023example/synthesized_factors`，并与 Wind 数据对齐 |
| `stock_code` | 股票代码（WindCode） | 主键壳子来自 `data/2023example/synthesized_factors`，并与 Wind 数据对齐 |
| `close` | 当日收盘价（未复权） | `ASHAREEODPRICES.S_DQ_CLOSE` |
| `trade_status` | 交易状态（如“交易”“停牌”等） | `ASHAREEODPRICES.S_DQ_TRADESTATUS` |
| `trade_status_code` | 交易状态代码 | `ASHAREEODPRICES.S_DQ_TRADESTATUSCODE` |
| `up_limit_price` | 当日涨停价 | `ASHAREEODPRICES.S_DQ_LIMIT` |
| `down_limit_price` | 当日跌停价 | `ASHAREEODPRICES.S_DQ_STOPPING` |
| `is_st_window` | 当日是否落在 ST 生效区间 | 由 `ASHAREST.ENTRY_DT / REMOVE_DT / S_TYPE_ST` 计算得到 |
| `delist_date` | 退市日期（若有） | `ASHAREDESCRIPTION.S_INFO_DELISTDATE` |
| `is_delisted` | 是否已退市标记 | `ASHAREDESCRIPTION.IS_DELISTED` |
| `is_imputed` | 是否发生保守填充/兜底 | 非 Wind 原始字段（脚本生成） |
| `impute_reason` | 填充原因说明 | 非 Wind 原始字段（脚本生成） |
| `is_suspended` | 停牌约束标记 | 由 `trade_status`（及缺失兜底）计算得到 |
| `is_st_risk` | ST/退市风险标记 | 由 `is_st_window + delist_date + is_delisted` 计算得到 |
| `is_limit_up` | 涨停状态标记 | 由 `close` 与 `up_limit_price` 比较计算得到 |
| `is_limit_down` | 跌停状态标记 | 由 `close` 与 `down_limit_price` 比较计算得到 |
| `can_buy` | 当日是否可买（1可买/0不可买） | 规则字段：由 `is_suspended / is_limit_up / is_st_risk` 计算 |
| `can_sell` | 当日是否可卖（1可卖/0不可卖） | 规则字段：由 `is_suspended / is_limit_down / is_st_risk` 计算 |

# 2 Backtesting

## 2.1 通用回测部分构建

使用Backtrader实现策略。整体的这个部分采用可插拔式的设计，分为下面五层：

为了通用性，建议这样设计：

1. `DataAdapter` 层  
- 统一读取你现在的三个输出目录。  
- 输出标准面板：`date, code, open, high, low, close, adjfactor, volume, amount, can_buy, can_sell, factor_score`。

2. `StrategyConfig` 层  
- 参数化：
  - `rebalance_freq`（W/M/Q）：默认是 "M"（月度）
  - `top_n`：默认是20
  - `weight_mode`：默认是"equal"（等权）
  - `commission`：默认是0.001（单边 0.1%）
  - `slippage`：默认是0.0005（0.05%）
  - `signal_lag`：默认是1（T 信号，T+1 成交）
- 后面做敏感性分析时直接改配置，不改策略代码。

3. `Signal + Filter + Portfolio` 三段式  
- `Signal`：按因子值排序。  
- `Filter`：先过滤 `can_buy/can_sell`。  
- `Portfolio`：等权或风险平价分配目标权重。

4. `ExecutionPolicy`（关键）  
- 先卖后买。  
- 卖出：仅对 `can_sell=1` 的目标剔除仓位下单；`can_sell=0` 的仓位保留。  
- 买入：仅从 `can_buy=1` 的候选中买；不足 `top_n` 的部分留现金。  
- 这样才能把“可买卖标签”真正纳入回测，而不是只做统计。

5. `Metrics` 层  
- 输出策略与基准净值、年化收益、波动率、Calmar。  
- 另加执行质量指标：不可卖持仓占比、不可买导致现金占比、实际持仓数。

值得注意的是，T日的因子能够得到交易，但是交易要放在T+1收盘成交。交易的限制是T+1日的限制。这个主要考虑的是实操层面的。

以下是每个结果文件的分析：

* `nav_timeseries.csv`（净值曲线原始数据）
    列：
    - `date`
    - `strategy_nav`
    - `benchmark_nav`
    - `excess_nav`

    计算：
    1. 每日策略总资产  
    \[
    V_t = \text{cash}_t + \sum_i(\text{shares}_{i,t}\times \text{price}_{i,t})
    \]
    2. 策略净值归一化  
    \[
    strategy\_nav_t = V_t / V_0
    \]
    3. 基准净值归一化（沪深300收盘价）  
    \[
    benchmark\_nav_t = close^{bench}_t / close^{bench}_0
    \]
    4. 超额净值  
    \[
    excess\_nav_t = strategy\_nav_t / benchmark\_nav_t
    \]

    解释：
    - `strategy_nav=1.05` 表示策略累计 +5%
    - `benchmark_nav=0.90` 表示基准累计 -10%
    - `excess_nav=1.10` 表示策略相对基准多赚约 10%（比值口径）

---
* `nav_curve.png`（净值曲线图）
    三条线分别对应上面三列：
    - 蓝：`strategy_nav`
    - 橙：`benchmark_nav`
    - 绿：`excess_nav`

    图的纵轴 `NAV` 含义：
    - 是“归一化净值”，不是价格
    - 起点都在 `1.0`
    - 大于 1 是相对起点盈利，小于 1 是亏损

    ---

* `metrics_strategy.csv`（策略绩效指标）
字段与计算：

  * `ann_return`（年化收益）
  - 先取日收益：
  \[
  r_t = \frac{NAV_t}{NAV_{t-1}} - 1
  \]
  - 若共有 \(N\) 个日收益（交易日），则：
  \[
  ann\_return = \left(\frac{NAV_{end}}{NAV_{start}}\right)^{252/N} - 1
  \]

     `ann_vol`（年化波动率）
  \[
  ann\_vol = std(r_t)\times \sqrt{252}
  \]
  （代码里用总体标准差 `ddof=0`）

  * `max_drawdown`（最大回撤）
  - 先算历史高点：
  \[
  peak_t = \max(NAV_1,\dots,NAV_t)
  \]
  - 回撤序列：
  \[
  dd_t = NAV_t/peak_t - 1
  \]
  - 最大回撤：
  \[
  max\_drawdown = \min(dd_t)
  \]

  * `calmar`（Calmar 比率）
  \[
  calmar = \frac{ann\_return}{|max\_drawdown|}
  \]
  （若无回撤则记 0）

  ---

*  `metrics_benchmark.csv`（基准绩效指标）
    与 `metrics_strategy.csv` **同一公式**，只是把 `strategy_nav` 换成 `benchmark_nav`。

---

* `summary.csv`（最终净值摘要）
  - `final_strategy_nav`：最后一天策略净值
  - `final_benchmark_nav`：最后一天基准净值
  - `final_excess_nav`：最后一天超额净值（前两者比值）


---

* `execution_log.csv`（每次调仓执行明细）
    每一行是一次调仓执行（T+1收盘）：
    - `planned_top_n`：目标持仓数
    - `actual_hold_n`：实际持仓数（受约束后）
    - `blocked_buy_n`：因 `can_buy=0` 未能买入的目标数
    - `blocked_sell_n`：因 `can_sell=0` 未能卖出的目标剔除数
    - `cash_after_rebalance`：调仓后现金

---

* `metrics_execution.csv`（执行质量汇总）
    从 `execution_log.csv` 聚合而来：
    - `rebalance_count`：调仓次数
    - `avg_actual_hold_n`：平均实际持仓数
    - `blocked_buy_ratio`：买入受阻比例（总 blocked_buy / 理论买入机会）
    - `blocked_sell_ratio`：卖出受阻比例（总 blocked_sell / 理论卖出机会）

---

## 2.2 参数敏感性分析

对于参数敏感性分析，目前的参数组合设置为：
  * rebalance_freq ∈ {W, M, Q}
  * top_n ∈ {10, 20, 30}
调用2.1的代码，每次参数组合保存一个结果，结果文件存储在2_backtesting\2.2_sensitivity_analysis\output。然后汇总成不同指标和热力图进行分析，结果存储在2_backtesting\2.2_sensitivity_analysis\reports。