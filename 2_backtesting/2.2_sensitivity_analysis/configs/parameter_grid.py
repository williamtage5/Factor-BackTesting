from __future__ import annotations


def get_parameter_grid() -> list[dict]:
    grid = []
    for freq in ["W", "M", "Q"]:
        for top_n in [10, 20, 30]:
            grid.append(
                {
                    "rebalance_freq": freq,
                    "top_n": top_n,
                    "weight_mode": "equal",
                    "factor_direction": "top",
                    "signal_lag": 1,
                    "commission": 0.001,
                    "slippage": 0.0005,
                    "exec_price": "close",
                }
            )
    return grid


def combo_id(p: dict) -> str:
    return (
        f"freq-{p['rebalance_freq']}_"
        f"top-{p['top_n']}_"
        f"wm-{p['weight_mode']}_"
        f"dir-{p['factor_direction']}"
    )

