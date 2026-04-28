from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StrategyConfig:
    benchmark_code: str = "000300.SH"
    rebalance_freq: str = "M"  # W / M / Q
    top_n: int = 20
    weight_mode: str = "equal"  # equal / risk_parity
    factor_direction: str = "top"  # top / bottom
    commission: float = 0.001
    slippage: float = 0.0005
    signal_lag: int = 1
    exec_price: str = "close"
    initial_cash: float = 1_000_000.0
    limit_eps: float = 0.0005

