from __future__ import annotations

import importlib.util
import json
import sys
import time
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


def _plot_nav(nav_df: pd.DataFrame, output_png: Path) -> None:
    plt.figure(figsize=(11, 5))
    plt.plot(nav_df["date"], nav_df["strategy_nav"], label="Strategy NAV")
    plt.plot(nav_df["date"], nav_df["benchmark_nav"], label="Benchmark NAV")
    plt.plot(nav_df["date"], nav_df["excess_nav"], label="Excess NAV")
    plt.title("Strategy / Benchmark / Excess NAV")
    plt.xlabel("Date")
    plt.ylabel("NAV")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_png, dpi=160)
    plt.close()


def main() -> None:
    this_file = Path(__file__).resolve()
    sa_root = this_file.parents[1]  # 2.2_sensitivity_analysis
    bt_root = sa_root.parent  # 2_backtesting
    project_root = bt_root.parent  # project root
    engine_root = bt_root / "2.1_backtest_engine"

    grid_mod = _load_module("grid_mod", sa_root / "configs" / "parameter_grid.py")
    data_mod = _load_module("DataAdapter", engine_root / "1_DataAdapter" / "data_adapter.py")
    cfg_layer_mod = _load_module(
        "StrategyConfigLayer", engine_root / "2_StrategyConfig" / "strategy_config.py"
    )
    sfp_mod = _load_module("SFP", engine_root / "3_SignalFilterPortfolio" / "sfp.py")
    sys.modules["_SFP"] = sfp_mod
    sys.modules["_StrategyConfig"] = cfg_layer_mod
    exec_mod = _load_module("ExecutionPolicy", engine_root / "4_ExecutionPolicy" / "execution_policy.py")
    metrics_mod = _load_module("MetricsLayer", engine_root / "5_Metrics" / "metrics.py")
    engine_cfg = _load_module("engine_cfg", engine_root / "config.py")

    panel, benchmark = data_mod.load_standard_panel(
        project_root=project_root,
        factor_dir=engine_cfg.FACTOR_DIR,
        ohlc_dir=engine_cfg.OHLC_DIR,
        trade_condition_dir=engine_cfg.TRADE_CONDITION_DIR,
        benchmark_path=engine_cfg.BENCHMARK_PATH,
    )

    output_root = sa_root / "output"
    output_root.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for p in grid_mod.get_parameter_grid():
        cid = grid_mod.combo_id(p)
        run_dir = output_root / cid
        run_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        status = {"combo_id": cid, "status": "success", "error": "", "seconds": 0.0}
        try:
            cfg = cfg_layer_mod.StrategyConfig(
                benchmark_code=engine_cfg.BENCHMARK_CODE,
                rebalance_freq=p["rebalance_freq"],
                top_n=p["top_n"],
                weight_mode=p["weight_mode"],
                factor_direction=p["factor_direction"],
                commission=p["commission"],
                slippage=p["slippage"],
                signal_lag=p["signal_lag"],
                exec_price=p["exec_price"],
                initial_cash=engine_cfg.INITIAL_CASH,
                limit_eps=engine_cfg.LIMIT_EPS,
            )
            exe_res = exec_mod.run_execution(panel=panel, cfg=cfg)
            bench_nav = metrics_mod.build_benchmark_nav(benchmark)
            nav = exe_res.nav_df.merge(bench_nav, on="date", how="left")
            nav["excess_nav"] = nav["strategy_nav"] / nav["benchmark_nav"]

            strategy_metrics = metrics_mod.calc_perf_metrics(nav["strategy_nav"])
            benchmark_metrics = metrics_mod.calc_perf_metrics(nav["benchmark_nav"])
            execution_metrics = metrics_mod.summarize_execution(exe_res.execution_log)

            nav.to_csv(run_dir / "nav_timeseries.csv", index=False, encoding="utf-8-sig")
            exe_res.execution_log.to_csv(run_dir / "execution_log.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame([strategy_metrics]).to_csv(
                run_dir / "metrics_strategy.csv", index=False, encoding="utf-8-sig"
            )
            pd.DataFrame([benchmark_metrics]).to_csv(
                run_dir / "metrics_benchmark.csv", index=False, encoding="utf-8-sig"
            )
            pd.DataFrame([execution_metrics]).to_csv(
                run_dir / "metrics_execution.csv", index=False, encoding="utf-8-sig"
            )
            pd.DataFrame(
                [
                    {"label": "strategy", **strategy_metrics},
                    {"label": "benchmark", **benchmark_metrics},
                ]
            ).to_csv(run_dir / "metrics_comparison.csv", index=False, encoding="utf-8-sig")
            summary = {
                "final_strategy_nav": float(nav["strategy_nav"].iloc[-1]),
                "final_benchmark_nav": float(nav["benchmark_nav"].iloc[-1]),
                "final_excess_nav": float(nav["excess_nav"].iloc[-1]),
            }
            pd.DataFrame([summary]).to_csv(run_dir / "summary.csv", index=False, encoding="utf-8-sig")
            _plot_nav(nav, run_dir / "nav_curve.png")

            all_rows.append(
                {
                    "combo_id": cid,
                    "rebalance_freq": p["rebalance_freq"],
                    "top_n": p["top_n"],
                    "weight_mode": p["weight_mode"],
                    "factor_direction": p["factor_direction"],
                    "ann_return": strategy_metrics["ann_return"],
                    "ann_vol": strategy_metrics["ann_vol"],
                    "max_drawdown": strategy_metrics["max_drawdown"],
                    "calmar": strategy_metrics["calmar"],
                    "final_strategy_nav": summary["final_strategy_nav"],
                    "final_benchmark_nav": summary["final_benchmark_nav"],
                    "final_excess_nav": summary["final_excess_nav"],
                    "rebalance_count": execution_metrics["rebalance_count"],
                    "avg_actual_hold_n": execution_metrics["avg_actual_hold_n"],
                    "blocked_buy_ratio": execution_metrics["blocked_buy_ratio"],
                    "blocked_sell_ratio": execution_metrics["blocked_sell_ratio"],
                }
            )
        except Exception as e:
            status["status"] = "failed"
            status["error"] = str(e)
        finally:
            status["seconds"] = round(time.time() - t0, 4)
            (run_dir / "run_status.json").write_text(
                json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    if all_rows:
        pd.DataFrame(all_rows).to_csv(
            sa_root / "reports" / "grid_run_summary.csv", index=False, encoding="utf-8-sig"
        )
    print("Grid run finished.")


if __name__ == "__main__":
    main()
