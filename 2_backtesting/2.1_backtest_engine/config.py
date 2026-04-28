from __future__ import annotations

# =========================
# Backtest Runtime Config
# =========================

# Data locations (relative to project root)
FACTOR_DIR = "data/2023example/synthesized_factors"
OHLC_DIR = "1_data_request/1.1_OHLC/output/ohlc_daily_2023example"
TRADE_CONDITION_DIR = "1_data_request/1.3_trade_condition/output/trade_condition_daily_2023example"
BENCHMARK_PATH = "1_data_request/1.2_SH.300/output/hs300_2023example/hs300_daily.csv"

# Strategy params
BENCHMARK_CODE = "000300.SH"
REBALANCE_FREQ = "M"  # W / M / Q
TOP_N = 20
WEIGHT_MODE = "equal"  # equal / risk_parity (placeholder)
FACTOR_DIRECTION = "top"  # top / bottom
COMMISSION = 0.001  # one-way
SLIPPAGE = 0.0005
SIGNAL_LAG = 1  # T signal -> T+1 execution
EXEC_PRICE = "close"
INITIAL_CASH = 1_000_000.0
LIMIT_EPS = 0.0005

# Output
OUTPUT_DIR = "2_backtesting/2.1_backtest_engine/output/restructured_run"
