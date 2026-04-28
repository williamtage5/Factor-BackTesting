from __future__ import annotations

import argparse
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


def _chunks(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


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


def _query_range_trade_status(
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
        frames.append(run_query(sql))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _query_by_codes(
    run_query,
    sql_template: str,
    codes: list[str],
    code_chunk_size: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for code_chunk in _chunks(codes, code_chunk_size):
        code_list_sql = ",".join([f"'{c}'" for c in code_chunk])
        sql = sql_template.replace("{CODE_LIST}", code_list_sql)
        frames.append(run_query(sql))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _normalize_trade_status(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "stock_code",
                "close",
                "trade_status",
                "trade_status_code",
                "up_limit_price",
                "down_limit_price",
            ]
        )

    out = df.rename(
        columns={
            "TRADE_DT": "trade_date",
            "S_INFO_WINDCODE": "stock_code",
            "S_DQ_CLOSE": "close",
            "S_DQ_TRADESTATUS": "trade_status",
            "S_DQ_TRADESTATUSCODE": "trade_status_code",
            "S_DQ_LIMIT": "up_limit_price",
            "S_DQ_STOPPING": "down_limit_price",
        }
    )
    out["trade_date"] = out["trade_date"].astype(str)
    out["stock_code"] = out["stock_code"].astype(str)
    out = out[
        [
            "trade_date",
            "stock_code",
            "close",
            "trade_status",
            "trade_status_code",
            "up_limit_price",
            "down_limit_price",
        ]
    ].drop_duplicates(subset=["trade_date", "stock_code"], keep="first")
    return out


def _normalize_st(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["stock_code", "st_type", "entry_dt", "remove_dt"])
    out = df.rename(
        columns={
            "S_INFO_WINDCODE": "stock_code",
            "S_TYPE_ST": "st_type",
            "ENTRY_DT": "entry_dt",
            "REMOVE_DT": "remove_dt",
        }
    )
    out["stock_code"] = out["stock_code"].astype(str)
    out["entry_dt"] = out["entry_dt"].astype(str).str.replace(".0", "", regex=False)
    out["remove_dt"] = out["remove_dt"].astype(str).str.replace(".0", "", regex=False)
    out.loc[out["entry_dt"].isin(["nan", "None", ""]), "entry_dt"] = ""
    out.loc[out["remove_dt"].isin(["nan", "None", ""]), "remove_dt"] = ""
    return out[["stock_code", "st_type", "entry_dt", "remove_dt"]]


def _normalize_delist(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["stock_code", "delist_date", "is_delisted"])
    out = df.rename(
        columns={
            "S_INFO_WINDCODE": "stock_code",
            "S_INFO_DELISTDATE": "delist_date",
            "IS_DELISTED": "is_delisted",
        }
    )
    out["stock_code"] = out["stock_code"].astype(str)
    out["delist_date"] = out["delist_date"].astype(str).str.replace(".0", "", regex=False)
    out.loc[out["delist_date"].isin(["nan", "None", ""]), "delist_date"] = ""
    out["is_delisted"] = out["is_delisted"].astype(str)
    return out[["stock_code", "delist_date", "is_delisted"]].drop_duplicates(
        subset=["stock_code"], keep="first"
    )


def _build_st_daily_flags(shell: pd.DataFrame, st_df: pd.DataFrame) -> pd.DataFrame:
    if st_df.empty:
        return pd.DataFrame(
            {"trade_date": shell["trade_date"], "stock_code": shell["stock_code"], "is_st_window": 0}
        )

    shell_idx = shell.copy()
    shell_idx["key"] = shell_idx["trade_date"] + "|" + shell_idx["stock_code"]
    flag = pd.Series(0, index=shell_idx["key"].values, dtype="int8")

    for _, row in st_df.iterrows():
        code = row["stock_code"]
        entry = row["entry_dt"]
        remove = row["remove_dt"]
        if not entry:
            continue
        cond = shell_idx["stock_code"] == code
        cond = cond & (shell_idx["trade_date"] >= entry)
        if remove:
            cond = cond & (shell_idx["trade_date"] <= remove)
        keys = shell_idx.loc[cond, "key"]
        if not keys.empty:
            flag.loc[keys.values] = 1

    out = shell_idx[["trade_date", "stock_code", "key"]].copy()
    out["is_st_window"] = out["key"].map(flag).fillna(0).astype(int)
    return out[["trade_date", "stock_code", "is_st_window"]]


def _calc_rules(df: pd.DataFrame, eps: float) -> pd.DataFrame:
    out = df.copy()
    out["is_imputed"] = 0
    out["impute_reason"] = ""

    status_missing = out["trade_status"].isna() | out["trade_status"].astype(str).str.strip().eq("")
    out.loc[status_missing, "is_imputed"] = 1
    out.loc[status_missing, "impute_reason"] = (
        out.loc[status_missing, "impute_reason"].astype(str) + "|missing_trade_status"
    )

    out["is_suspended"] = 0
    out.loc[status_missing, "is_suspended"] = 1
    out.loc[
        out["trade_status"].astype(str).str.strip().ne("交易") & (~status_missing), "is_suspended"
    ] = 1

    # ST / delist risk
    out["is_st_risk"] = 0
    out.loc[out["is_st_window"] == 1, "is_st_risk"] = 1
    out.loc[out["is_delisted"].astype(str).str.upper().isin(["1", "Y", "YES", "TRUE"]), "is_st_risk"] = 1
    out.loc[(out["delist_date"].astype(str).str.len() >= 8) & (out["trade_date"] >= out["delist_date"]), "is_st_risk"] = 1

    # limit up/down by price threshold
    out["is_limit_up"] = 0
    out["is_limit_down"] = 0

    up_ok = out["close"].notna() & out["up_limit_price"].notna()
    down_ok = out["close"].notna() & out["down_limit_price"].notna()
    out.loc[up_ok & (out["close"] >= out["up_limit_price"] * (1 - eps)), "is_limit_up"] = 1
    out.loc[down_ok & (out["close"] <= out["down_limit_price"] * (1 + eps)), "is_limit_down"] = 1

    # conservative fallback for missing key fields
    miss_key = out["close"].isna() | out["up_limit_price"].isna() | out["down_limit_price"].isna()
    out.loc[miss_key, "is_imputed"] = 1
    out.loc[miss_key, "impute_reason"] = (
        out.loc[miss_key, "impute_reason"].astype(str) + "|missing_limit_fields"
    )

    # tradability with st risk included
    out["can_buy"] = 1
    out["can_sell"] = 1
    out.loc[(out["is_suspended"] == 1) | (out["is_limit_up"] == 1) | (out["is_st_risk"] == 1), "can_buy"] = 0
    out.loc[(out["is_suspended"] == 1) | (out["is_limit_down"] == 1) | (out["is_st_risk"] == 1), "can_sell"] = 0

    out["impute_reason"] = out["impute_reason"].astype(str).str.strip("|").replace({"": "none"})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build trade condition constraints aligned with factor shell."
    )
    parser.add_argument(
        "--factor-dir",
        default="data/2023example/synthesized_factors",
        help="Factor daily csv directory for key shell.",
    )
    parser.add_argument(
        "--status-sql",
        default="1_data_request/1.3_trade_condition/sql/01_get_trade_status_by_daterange_codes.sql",
        help="SQL template for trade status request.",
    )
    parser.add_argument(
        "--st-sql",
        default="1_data_request/1.3_trade_condition/sql/02_get_st_intervals_by_codes.sql",
        help="SQL template for ST intervals request.",
    )
    parser.add_argument(
        "--delist-sql",
        default="1_data_request/1.3_trade_condition/sql/03_get_delist_info_by_codes.sql",
        help="SQL template for delist info request.",
    )
    parser.add_argument(
        "--output-dir",
        default="1_data_request/1.3_trade_condition/output/trade_condition_daily_2023example",
        help="Output directory for daily trade-condition csv files.",
    )
    parser.add_argument("--chunk-size", type=int, default=200, help="Code chunk size for IN clause.")
    parser.add_argument("--eps", type=float, default=0.0005, help="Price tolerance for limit checks.")
    args = parser.parse_args()

    root = _project_root()
    factor_dir = (root / args.factor_dir).resolve()
    status_sql_path = (root / args.status_sql).resolve()
    st_sql_path = (root / args.st_sql).resolve()
    delist_sql_path = (root / args.delist_sql).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_query = _load_run_query(root)
    shell = _build_shell_from_factors(factor_dir)
    all_dates = sorted(shell["trade_date"].astype(str).unique().tolist())
    all_codes = sorted(shell["stock_code"].astype(str).unique().tolist())

    status_sql_t = _load_sql(status_sql_path)
    st_sql_t = _load_sql(st_sql_path)
    delist_sql_t = _load_sql(delist_sql_path)

    status_raw = _query_range_trade_status(
        run_query=run_query,
        sql_template=status_sql_t,
        trade_dt_from=all_dates[0],
        trade_dt_to=all_dates[-1],
        codes=all_codes,
        code_chunk_size=args.chunk_size,
    )
    st_raw = _query_by_codes(
        run_query=run_query,
        sql_template=st_sql_t,
        codes=all_codes,
        code_chunk_size=args.chunk_size,
    )
    delist_raw = _query_by_codes(
        run_query=run_query,
        sql_template=delist_sql_t,
        codes=all_codes,
        code_chunk_size=args.chunk_size,
    )

    status = _normalize_trade_status(status_raw)
    st_df = _normalize_st(st_raw)
    delist_df = _normalize_delist(delist_raw)

    st_daily = _build_st_daily_flags(shell, st_df)
    merged = shell.merge(status, on=["trade_date", "stock_code"], how="left")
    merged = merged.merge(st_daily, on=["trade_date", "stock_code"], how="left")
    merged = merged.merge(delist_df, on=["stock_code"], how="left")
    merged["is_st_window"] = merged["is_st_window"].fillna(0).astype(int)
    merged["is_delisted"] = merged["is_delisted"].fillna("")
    merged["delist_date"] = merged["delist_date"].fillna("")

    merged = _calc_rules(merged, eps=args.eps)

    # Global strict checks
    shell_n = len(shell)
    out_n = len(merged)
    out_key_n = merged[["trade_date", "stock_code"]].drop_duplicates().shape[0]
    if not (shell_n == out_n == out_key_n):
        raise RuntimeError(
            f"Global key mismatch: shell_n={shell_n}, out_n={out_n}, out_key_n={out_key_n}"
        )

    report_rows: list[dict] = []
    for trade_date, day_df in merged.groupby("trade_date", sort=True):
        day_df = day_df.sort_values(["trade_date", "stock_code"]).reset_index(drop=True)
        day_path = output_dir / f"{trade_date}.csv"
        day_df.to_csv(day_path, index=False, encoding="utf-8-sig")

        factor_n = int((shell["trade_date"] == trade_date).sum())
        output_n = int(len(day_df))
        key_match = int(
            output_n == factor_n
            and day_df[["trade_date", "stock_code"]].drop_duplicates().shape[0] == factor_n
        )
        report_rows.append(
            {
                "trade_date": trade_date,
                "factor_shell_n": factor_n,
                "output_n": output_n,
                "key_match": key_match,
                "suspended_n": int((day_df["is_suspended"] == 1).sum()),
                "st_risk_n": int((day_df["is_st_risk"] == 1).sum()),
                "limit_up_n": int((day_df["is_limit_up"] == 1).sum()),
                "limit_down_n": int((day_df["is_limit_down"] == 1).sum()),
                "can_buy_0_n": int((day_df["can_buy"] == 0).sum()),
                "can_sell_0_n": int((day_df["can_sell"] == 0).sum()),
                "imputed_n": int((day_df["is_imputed"] == 1).sum()),
            }
        )

    report = pd.DataFrame(report_rows).sort_values("trade_date").reset_index(drop=True)
    report_path = output_dir / "request_report.csv"
    report.to_csv(report_path, index=False, encoding="utf-8-sig")

    print("Completed trade-condition build and alignment.")
    print(f"shell_n={shell_n}, out_n={out_n}, out_key_n={out_key_n}")
    print(f"daily_files={report.shape[0]}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()

