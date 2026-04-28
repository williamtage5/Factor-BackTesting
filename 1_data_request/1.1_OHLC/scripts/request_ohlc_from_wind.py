from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_run_query(project_root: Path):
    module_dir = project_root / "0_common" / "request_from_sqlsever"
    sys.path.insert(0, str(module_dir))
    from sql_server_client import run_query  # type: ignore

    return run_query


def _load_sql(sql_path: Path) -> str:
    return sql_path.read_text(encoding="utf-8")


def _build_shell_from_factors(factor_dir: Path) -> pd.DataFrame:
    files = sorted([p for p in factor_dir.glob("*.csv") if p.name != "run_meta.json"])
    if not files:
        raise FileNotFoundError(f"No factor CSV files found in: {factor_dir}")

    parts: list[pd.DataFrame] = []
    for fp in files:
        df = pd.read_csv(fp, usecols=["trade_date", "stock_code"])
        df["trade_date"] = df["trade_date"].astype(str)
        df["stock_code"] = df["stock_code"].astype(str)
        parts.append(df)

    shell = pd.concat(parts, ignore_index=True).drop_duplicates(
        subset=["trade_date", "stock_code"], keep="first"
    )
    shell = shell.sort_values(["trade_date", "stock_code"]).reset_index(drop=True)
    return shell


def _chunks(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _query_one_day_ohlc(
    run_query,
    sql_template: str,
    trade_date: str,
    codes: list[str],
    code_chunk_size: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for code_chunk in _chunks(codes, code_chunk_size):
        code_list_sql = ",".join([f"'{c}'" for c in code_chunk])
        sql = (
            sql_template.replace("{TRADE_DT}", trade_date).replace(
                "{CODE_LIST}", code_list_sql
            )
        )
        df = run_query(sql)
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _query_range_ohlc(
    run_query,
    sql_template: str,
    trade_dt_from: str,
    trade_dt_to: str,
    codes: list[str],
    code_chunk_size: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for code_chunk in _chunks(codes, code_chunk_size):
        code_list_sql = ",".join([f"'{c}'" for c in code_chunk])
        sql = (
            sql_template.replace("{TRADE_DT_FROM}", trade_dt_from)
            .replace("{TRADE_DT_TO}", trade_dt_to)
            .replace("{CODE_LIST}", code_list_sql)
        )
        df = run_query(sql)
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _normalize_wind_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "stock_code",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "adjfactor",
                "adj_open",
                "adj_high",
                "adj_low",
                "adj_close",
                "trade_status",
                "trade_status_code",
                "limit_flag",
                "stopping_flag",
            ]
        )

    rename_map = {
        "TRADE_DT": "trade_date",
        "S_INFO_WINDCODE": "stock_code",
        "S_DQ_OPEN": "open",
        "S_DQ_HIGH": "high",
        "S_DQ_LOW": "low",
        "S_DQ_CLOSE": "close",
        "S_DQ_VOLUME": "volume",
        "S_DQ_AMOUNT": "amount",
        "S_DQ_ADJFACTOR": "adjfactor",
        "S_DQ_ADJOPEN": "adj_open",
        "S_DQ_ADJHIGH": "adj_high",
        "S_DQ_ADJLOW": "adj_low",
        "S_DQ_ADJCLOSE": "adj_close",
        "S_DQ_TRADESTATUS": "trade_status",
        "S_DQ_TRADESTATUSCODE": "trade_status_code",
        "S_DQ_LIMIT": "limit_flag",
        "S_DQ_STOPPING": "stopping_flag",
    }
    out = df.rename(columns=rename_map)
    out["trade_date"] = out["trade_date"].astype(str)
    out["stock_code"] = out["stock_code"].astype(str)

    cols = [
        "trade_date",
        "stock_code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjfactor",
        "adj_open",
        "adj_high",
        "adj_low",
        "adj_close",
        "trade_status",
        "trade_status_code",
        "limit_flag",
        "stopping_flag",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[cols]
    out = out.drop_duplicates(subset=["trade_date", "stock_code"], keep="first")
    return out


def _apply_imputation(df: pd.DataFrame) -> pd.DataFrame:
    # Keep traceability of which row has imputation.
    out = df.copy()
    out["is_imputed"] = 0
    out["impute_reason"] = ""

    # Forward fill close within stock, then fallback 0 for very first missing.
    close_missing_before = out["close"].isna()
    out["close"] = out.groupby("stock_code", group_keys=False)["close"].ffill()
    out.loc[out["close"].isna(), "close"] = 0.0
    close_filled = close_missing_before & out["close"].notna()
    out.loc[close_filled, "is_imputed"] = 1
    out.loc[close_filled, "impute_reason"] = (
        out.loc[close_filled, "impute_reason"].astype(str) + "|close_ffill_or_zero"
    )

    # Open/high/low fallback to close when missing.
    for col in ["open", "high", "low"]:
        miss = out[col].isna() & out["close"].notna()
        out.loc[miss, col] = out.loc[miss, "close"]
        out.loc[miss, "is_imputed"] = 1
        out.loc[miss, "impute_reason"] = (
            out.loc[miss, "impute_reason"].astype(str) + f"|{col}_from_close"
        )

    # volume/amount default 0.
    for col in ["volume", "amount"]:
        miss = out[col].isna()
        out.loc[miss, col] = 0.0
        out.loc[miss, "is_imputed"] = 1
        out.loc[miss, "impute_reason"] = (
            out.loc[miss, "impute_reason"].astype(str) + f"|{col}_zero"
        )

    # adjfactor ffill by stock, fallback 1.0.
    adj_missing_before = out["adjfactor"].isna()
    out["adjfactor"] = out.groupby("stock_code", group_keys=False)["adjfactor"].ffill()
    out.loc[out["adjfactor"].isna(), "adjfactor"] = 1.0
    adj_filled = adj_missing_before & out["adjfactor"].notna()
    out.loc[adj_filled, "is_imputed"] = 1
    out.loc[adj_filled, "impute_reason"] = (
        out.loc[adj_filled, "impute_reason"].astype(str) + "|adjfactor_ffill_or_one"
    )

    # Forward fill adjusted prices; fallback from raw prices * adjfactor.
    for adj_col, raw_col in [
        ("adj_open", "open"),
        ("adj_high", "high"),
        ("adj_low", "low"),
        ("adj_close", "close"),
    ]:
        miss_before = out[adj_col].isna()
        out[adj_col] = out.groupby("stock_code", group_keys=False)[adj_col].ffill()
        miss_after_ffill = out[adj_col].isna()
        fallback_mask = miss_after_ffill & out[raw_col].notna() & out["adjfactor"].notna()
        out.loc[fallback_mask, adj_col] = (
            out.loc[fallback_mask, raw_col] * out.loc[fallback_mask, "adjfactor"]
        )
        filled = miss_before & out[adj_col].notna()
        out.loc[filled, "is_imputed"] = 1
        out.loc[filled, "impute_reason"] = (
            out.loc[filled, "impute_reason"].astype(str) + f"|{adj_col}_ffill_or_calc"
        )

    out["impute_reason"] = (
        out["impute_reason"].astype(str).str.strip("|").replace({"": "none"})
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Request A-share OHLC from Wind SQLServer and align to factor key shell."
    )
    parser.add_argument(
        "--factor-dir",
        default="data/2023example/synthesized_factors",
        help="Factor daily csv directory for key shell.",
    )
    parser.add_argument(
        "--sql-template",
        default="1_data_request/1.1_OHLC/sql/02_get_ohlc_by_daterange_codes.sql",
        help="SQL template file path.",
    )
    parser.add_argument(
        "--output-dir",
        default="1_data_request/1.1_OHLC/output/ohlc_daily_2023example",
        help="Output directory for daily OHLC csv files.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=200,
        help="Code chunk size for IN clause.",
    )
    args = parser.parse_args()

    root = _project_root()
    factor_dir = (root / args.factor_dir).resolve()
    sql_template_path = (root / args.sql_template).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_query = _load_run_query(root)
    sql_template = _load_sql(sql_template_path)
    shell = _build_shell_from_factors(factor_dir)
    all_dates = sorted(shell["trade_date"].astype(str).unique().tolist())
    all_codes = sorted(shell["stock_code"].astype(str).unique().tolist())
    dt_from = all_dates[0]
    dt_to = all_dates[-1]

    wind_range_raw = _query_range_ohlc(
        run_query=run_query,
        sql_template=sql_template,
        trade_dt_from=dt_from,
        trade_dt_to=dt_to,
        codes=all_codes,
        code_chunk_size=args.chunk_size,
    )
    wind_range = _normalize_wind_columns(wind_range_raw)
    wind_range = wind_range[
        wind_range["trade_date"].isin(all_dates) & wind_range["stock_code"].isin(all_codes)
    ].copy()
    wind_range = wind_range.drop_duplicates(
        subset=["trade_date", "stock_code"], keep="first"
    )

    daily_frames: list[pd.DataFrame] = []
    report_rows: list[dict] = []

    for trade_date, day_shell in shell.groupby("trade_date", sort=True):
        day_shell = day_shell[["trade_date", "stock_code"]].copy()
        codes = day_shell["stock_code"].astype(str).tolist()

        wind = wind_range[
            (wind_range["trade_date"] == str(trade_date))
            & (wind_range["stock_code"].isin(codes))
        ].copy()

        merged = day_shell.merge(wind, on=["trade_date", "stock_code"], how="left")
        merged["missing_any_before_impute"] = merged[
            ["open", "high", "low", "close", "volume", "amount", "adjfactor"]
        ].isna().any(axis=1)
        merged = _apply_imputation(merged)

        # Final key strictness checks.
        expected_n = len(day_shell)
        actual_n = len(merged)
        key_match = (
            expected_n == actual_n
            and merged[["trade_date", "stock_code"]]
            .drop_duplicates()
            .shape[0]
            == expected_n
        )
        if not key_match:
            raise RuntimeError(
                f"Key mismatch on {trade_date}: expected={expected_n}, actual={actual_n}"
            )

        day_path = output_dir / f"{trade_date}.csv"
        merged = merged.sort_values(["trade_date", "stock_code"]).reset_index(drop=True)
        merged.to_csv(day_path, index=False, encoding="utf-8-sig")

        report_rows.append(
            {
                "trade_date": trade_date,
                "factor_shell_n": int(expected_n),
                "wind_raw_n": int(len(wind)),
                "output_n": int(actual_n),
                "missing_row_before_impute_n": int(
                    merged["missing_any_before_impute"].sum()
                ),
                "imputed_row_n": int((merged["is_imputed"] == 1).sum()),
                "key_match": int(key_match),
            }
        )
        daily_frames.append(merged)

    all_df = pd.concat(daily_frames, ignore_index=True)
    report = pd.DataFrame(report_rows).sort_values("trade_date").reset_index(drop=True)
    report_path = output_dir / "request_report.csv"
    report.to_csv(report_path, index=False, encoding="utf-8-sig")

    # Global strict checks.
    shell_n = len(shell)
    out_n = len(all_df)
    out_key_n = all_df[["trade_date", "stock_code"]].drop_duplicates().shape[0]
    if not (shell_n == out_n == out_key_n):
        raise RuntimeError(
            f"Global key mismatch: shell_n={shell_n}, out_n={out_n}, out_key_n={out_key_n}"
        )

    print("Completed OHLC request and alignment.")
    print(f"shell_n={shell_n}, out_n={out_n}, out_key_n={out_key_n}")
    print(f"daily_files={report.shape[0]}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
