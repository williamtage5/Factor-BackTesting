from __future__ import annotations

import numpy as np
import pandas as pd


def calc_perf_metrics(nav: pd.Series) -> dict[str, float]:
    nav = nav.dropna()
    if len(nav) < 2:
        return {"ann_return": 0.0, "ann_vol": 0.0, "max_drawdown": 0.0, "calmar": 0.0}

    ret = nav.pct_change().dropna()
    n = len(ret)
    ann_return = float((nav.iloc[-1] / nav.iloc[0]) ** (252.0 / n) - 1.0)
    ann_vol = float(ret.std(ddof=0) * np.sqrt(252.0))
    drawdown = nav / nav.cummax() - 1.0
    max_dd = float(drawdown.min())
    calmar = float(ann_return / abs(max_dd)) if max_dd < 0 else 0.0
    return {
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "max_drawdown": max_dd,
        "calmar": calmar,
    }


def build_benchmark_nav(benchmark_df: pd.DataFrame) -> pd.DataFrame:
    out = benchmark_df[["date", "benchmark_close"]].copy().sort_values("date").reset_index(drop=True)
    out["benchmark_nav"] = out["benchmark_close"] / out["benchmark_close"].iloc[0]
    return out[["date", "benchmark_nav"]]


def summarize_execution(exec_df: pd.DataFrame) -> dict[str, float]:
    if exec_df.empty:
        return {
            "rebalance_count": 0,
            "avg_actual_hold_n": 0.0,
            "blocked_buy_ratio": 0.0,
            "blocked_sell_ratio": 0.0,
        }
    planned = float(exec_df["planned_top_n"].mean()) if "planned_top_n" in exec_df.columns else 0.0
    buy_ratio = float(exec_df["blocked_buy_n"].sum() / (len(exec_df) * planned)) if planned > 0 else 0.0
    sell_base = float(exec_df["actual_hold_n"].replace(0, np.nan).mean())
    sell_ratio = float(exec_df["blocked_sell_n"].sum() / (len(exec_df) * sell_base)) if sell_base > 0 else 0.0
    return {
        "rebalance_count": int(len(exec_df)),
        "avg_actual_hold_n": float(exec_df["actual_hold_n"].mean()),
        "blocked_buy_ratio": buy_ratio,
        "blocked_sell_ratio": sell_ratio,
    }

