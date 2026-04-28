from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    bt_root = Path(__file__).resolve().parent
    project_root = bt_root.parents[1]

    cfg_mod = _load_module("bt_config", bt_root / "config.py")
    data_mod = _load_module("DataAdapter", bt_root / "1_DataAdapter" / "data_adapter.py")
    cfg_layer_mod = _load_module("StrategyConfigLayer", bt_root / "2_StrategyConfig" / "strategy_config.py")
    sfp_mod = _load_module("SFP", bt_root / "3_SignalFilterPortfolio" / "sfp.py")
    sys.modules["_SFP"] = sfp_mod
    sys.modules["_StrategyConfig"] = cfg_layer_mod
    exec_mod = _load_module("ExecutionPolicy", bt_root / "4_ExecutionPolicy" / "execution_policy.py")
    metrics_mod = _load_module("MetricsLayer", bt_root / "5_Metrics" / "metrics.py")

    panel, benchmark = data_mod.load_standard_panel(
        project_root=project_root,
        factor_dir=cfg_mod.FACTOR_DIR,
        ohlc_dir=cfg_mod.OHLC_DIR,
        trade_condition_dir=cfg_mod.TRADE_CONDITION_DIR,
        benchmark_path=cfg_mod.BENCHMARK_PATH,
    )

    cfg = cfg_layer_mod.StrategyConfig(
        benchmark_code=cfg_mod.BENCHMARK_CODE,
        rebalance_freq=cfg_mod.REBALANCE_FREQ,
        top_n=cfg_mod.TOP_N,
        weight_mode=cfg_mod.WEIGHT_MODE,
        factor_direction=cfg_mod.FACTOR_DIRECTION,
        commission=cfg_mod.COMMISSION,
        slippage=cfg_mod.SLIPPAGE,
        signal_lag=cfg_mod.SIGNAL_LAG,
        exec_price=cfg_mod.EXEC_PRICE,
        initial_cash=cfg_mod.INITIAL_CASH,
        limit_eps=cfg_mod.LIMIT_EPS,
    )

    exe_res = exec_mod.run_execution(panel=panel, cfg=cfg)
    bench_nav = metrics_mod.build_benchmark_nav(benchmark)

    nav = exe_res.nav_df.merge(bench_nav, on="date", how="left")
    nav["excess_nav"] = nav["strategy_nav"] / nav["benchmark_nav"]

    strategy_metrics = metrics_mod.calc_perf_metrics(nav["strategy_nav"])
    benchmark_metrics = metrics_mod.calc_perf_metrics(nav["benchmark_nav"])
    execution_metrics = metrics_mod.summarize_execution(exe_res.execution_log)

    out_dir = (project_root / cfg_mod.OUTPUT_DIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    nav.to_csv(out_dir / "nav_timeseries.csv", index=False, encoding="utf-8-sig")
    exe_res.execution_log.to_csv(out_dir / "execution_log.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([strategy_metrics]).to_csv(out_dir / "metrics_strategy.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([benchmark_metrics]).to_csv(out_dir / "metrics_benchmark.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([execution_metrics]).to_csv(out_dir / "metrics_execution.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {"label": "strategy", **strategy_metrics},
            {"label": "benchmark", **benchmark_metrics},
        ]
    ).to_csv(out_dir / "metrics_comparison.csv", index=False, encoding="utf-8-sig")

    summary = {
        "config": asdict(cfg),
        "strategy": strategy_metrics,
        "benchmark": benchmark_metrics,
        "execution": execution_metrics,
        "final_strategy_nav": float(nav["strategy_nav"].iloc[-1]),
        "final_benchmark_nav": float(nav["benchmark_nav"].iloc[-1]),
        "final_excess_nav": float(nav["excess_nav"].iloc[-1]),
    }
    pd.DataFrame(
        [
            {
                "final_strategy_nav": summary["final_strategy_nav"],
                "final_benchmark_nav": summary["final_benchmark_nav"],
                "final_excess_nav": summary["final_excess_nav"],
                "strategy_ann_return": strategy_metrics["ann_return"],
                "strategy_ann_vol": strategy_metrics["ann_vol"],
                "strategy_max_drawdown": strategy_metrics["max_drawdown"],
                "strategy_calmar": strategy_metrics["calmar"],
                "benchmark_ann_return": benchmark_metrics["ann_return"],
                "benchmark_ann_vol": benchmark_metrics["ann_vol"],
                "benchmark_max_drawdown": benchmark_metrics["max_drawdown"],
                "benchmark_calmar": benchmark_metrics["calmar"],
            }
        ]
    ).to_csv(out_dir / "summary.csv", index=False, encoding="utf-8-sig")

    plt.figure(figsize=(11, 5))
    plt.plot(nav["date"], nav["strategy_nav"], label="Strategy NAV")
    plt.plot(nav["date"], nav["benchmark_nav"], label="Benchmark NAV")
    plt.plot(nav["date"], nav["excess_nav"], label="Excess NAV")
    plt.title("Strategy / Benchmark / Excess NAV")
    plt.xlabel("Date")
    plt.ylabel("NAV")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "nav_curve.png", dpi=160)
    plt.close()

    print("Backtest completed.")
    print("Output:", out_dir)
    print("Strategy metrics:", strategy_metrics)
    print("Benchmark metrics:", benchmark_metrics)
    print("Execution metrics:", execution_metrics)
    print(
        {
            "final_strategy_nav": summary["final_strategy_nav"],
            "final_benchmark_nav": summary["final_benchmark_nav"],
            "final_excess_nav": summary["final_excess_nav"],
        }
    )


if __name__ == "__main__":
    main()
