from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read_daily_csvs(folder: Path) -> pd.DataFrame:
    files = sorted([p for p in folder.glob("*.csv") if p.stem.isdigit() and len(p.stem) == 8])
    if not files:
        raise FileNotFoundError(f"No daily csv files found in: {folder}")
    parts = [pd.read_csv(p) for p in files]
    return pd.concat(parts, ignore_index=True)


def load_standard_panel(
    project_root: Path,
    factor_dir: str,
    ohlc_dir: str,
    trade_condition_dir: str,
    benchmark_path: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_path = (project_root / factor_dir).resolve()
    ohlc_path = (project_root / ohlc_dir).resolve()
    cond_path = (project_root / trade_condition_dir).resolve()
    bench_path = (project_root / benchmark_path).resolve()

    ohlc = _read_daily_csvs(ohlc_path)
    cond = _read_daily_csvs(cond_path)
    factor = _read_daily_csvs(factor_path)
    bench = pd.read_csv(bench_path)

    for df in [ohlc, cond, factor]:
        df["trade_date"] = df["trade_date"].astype(str)
        df["stock_code"] = df["stock_code"].astype(str)
    bench["trade_date"] = bench["trade_date"].astype(str)

    factor = factor.rename(columns={"IC-weighted synthesis factor": "factor_score"})

    panel = ohlc.merge(
        factor[["trade_date", "stock_code", "factor_score"]],
        on=["trade_date", "stock_code"],
        how="left",
    )
    panel = panel.merge(
        cond[["trade_date", "stock_code", "can_buy", "can_sell"]],
        on=["trade_date", "stock_code"],
        how="left",
    )

    panel["date"] = pd.to_datetime(panel["trade_date"], format="%Y%m%d")
    panel = panel.rename(columns={"stock_code": "code"})

    standard_cols = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "adjfactor",
        "volume",
        "amount",
        "can_buy",
        "can_sell",
        "factor_score",
    ]
    panel = panel[standard_cols].sort_values(["date", "code"]).reset_index(drop=True)

    bench["date"] = pd.to_datetime(bench["trade_date"], format="%Y%m%d")
    benchmark = bench[["date", "index_code", "close"]].rename(columns={"close": "benchmark_close"})
    benchmark = benchmark.sort_values("date").reset_index(drop=True)

    return panel, benchmark

