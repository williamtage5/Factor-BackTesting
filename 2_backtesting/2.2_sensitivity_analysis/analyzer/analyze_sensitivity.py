from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def _heatmap(df: pd.DataFrame, value_col: str, title: str, output_path: Path) -> None:
    pivot = df.pivot(index="rebalance_freq", columns="top_n", values=value_col)
    pivot = pivot.reindex(index=["W", "M", "Q"])
    plt.figure(figsize=(7.5, 4.8))
    sns.heatmap(pivot, annot=True, fmt=".4f", cmap="RdYlGn", cbar=True)
    plt.title(title)
    plt.xlabel("Top N")
    plt.ylabel("Rebalance Freq")
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def main() -> None:
    this_file = Path(__file__).resolve()
    sa_root = this_file.parents[1]
    output_root = sa_root / "output"
    report_root = sa_root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for d in sorted([p for p in output_root.iterdir() if p.is_dir()]):
        status_file = d / "run_status.json"
        if not status_file.exists():
            continue
        summ = d / "summary.csv"
        ms = d / "metrics_strategy.csv"
        me = d / "metrics_execution.csv"
        if not (summ.exists() and ms.exists() and me.exists()):
            continue
        combo = d.name
        # combo format: freq-W_top-20_wm-equal_dir-top
        parts = combo.split("_")
        freq = parts[0].split("-")[1]
        top_n = int(parts[1].split("-")[1])
        wm = parts[2].split("-")[1]
        direction = parts[3].split("-")[1]

        r1 = pd.read_csv(summ).iloc[0].to_dict()
        r2 = pd.read_csv(ms).iloc[0].to_dict()
        r3 = pd.read_csv(me).iloc[0].to_dict()
        rows.append(
            {
                "combo_id": combo,
                "rebalance_freq": freq,
                "top_n": top_n,
                "weight_mode": wm,
                "factor_direction": direction,
                "ann_return": r2["ann_return"],
                "ann_vol": r2["ann_vol"],
                "max_drawdown": r2["max_drawdown"],
                "calmar": r2["calmar"],
                "final_strategy_nav": r1["final_strategy_nav"],
                "final_benchmark_nav": r1["final_benchmark_nav"],
                "final_excess_nav": r1["final_excess_nav"],
                "rebalance_count": r3["rebalance_count"],
                "avg_actual_hold_n": r3["avg_actual_hold_n"],
                "blocked_buy_ratio": r3["blocked_buy_ratio"],
                "blocked_sell_ratio": r3["blocked_sell_ratio"],
            }
        )

    if not rows:
        print("No completed run results found.")
        return

    df = pd.DataFrame(rows).sort_values(["rebalance_freq", "top_n"]).reset_index(drop=True)
    df.to_csv(report_root / "sensitivity_summary.csv", index=False, encoding="utf-8-sig")

    _heatmap(
        df,
        value_col="ann_return",
        title="Sensitivity Heatmap - Annualized Return",
        output_path=report_root / "heatmap_ann_return.png",
    )
    _heatmap(
        df,
        value_col="calmar",
        title="Sensitivity Heatmap - Calmar Ratio",
        output_path=report_root / "heatmap_calmar.png",
    )
    _heatmap(
        df,
        value_col="final_excess_nav",
        title="Sensitivity Heatmap - Final Excess NAV",
        output_path=report_root / "heatmap_final_excess_nav.png",
    )
    print("Sensitivity analysis report generated.")


if __name__ == "__main__":
    main()

