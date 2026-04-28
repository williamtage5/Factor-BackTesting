from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def _build_date_shell(factor_dir: Path) -> pd.DataFrame:
    files = sorted([p for p in factor_dir.glob("*.csv") if p.name != "run_meta.json"])
    if not files:
        raise FileNotFoundError(f"No factor CSV files found in: {factor_dir}")

    dates = [p.stem for p in files]
    shell = pd.DataFrame({"trade_date": dates})
    shell["trade_date"] = shell["trade_date"].astype(str)
    shell = shell.drop_duplicates(subset=["trade_date"], keep="first")
    shell = shell.sort_values("trade_date").reset_index(drop=True)
    return shell


def _apply_close_imputation(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_imputed"] = 0
    out["impute_reason"] = "none"

    close_missing_before = out["close"].isna()

    out["close"] = out["close"].ffill()
    ffilled = close_missing_before & out["close"].notna()
    out.loc[ffilled, "is_imputed"] = 1
    out.loc[ffilled, "impute_reason"] = "close_ffill"

    still_missing = out["close"].isna()
    out["close"] = out["close"].bfill()
    bfilled = still_missing & out["close"].notna()
    out.loc[bfilled, "is_imputed"] = 1
    out.loc[bfilled, "impute_reason"] = "close_bfill"

    unresolved = out["close"].isna()
    out.loc[unresolved, "is_imputed"] = 1
    out.loc[unresolved, "impute_reason"] = "unresolved"

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Request HS300 close from Wind SQLServer and align to factor trade dates."
    )
    parser.add_argument(
        "--factor-dir",
        default="data/2023example/synthesized_factors",
        help="Factor daily csv directory for date shell.",
    )
    parser.add_argument(
        "--sql-template",
        default="1_data_request/1.2_SH.300/sql/01_get_hs300_close_by_daterange.sql",
        help="SQL template file path.",
    )
    parser.add_argument(
        "--output-dir",
        default="1_data_request/1.2_SH.300/output/hs300_2023example",
        help="Output directory for hs300 files.",
    )
    args = parser.parse_args()

    root = _project_root()
    factor_dir = (root / args.factor_dir).resolve()
    sql_template_path = (root / args.sql_template).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_query = _load_run_query(root)
    sql_template = _load_sql(sql_template_path)
    shell = _build_date_shell(factor_dir)
    dt_from = shell["trade_date"].iloc[0]
    dt_to = shell["trade_date"].iloc[-1]

    sql = (
        sql_template.replace("{TRADE_DT_FROM}", str(dt_from)).replace(
            "{TRADE_DT_TO}", str(dt_to)
        )
    )
    raw = run_query(sql)
    raw = raw.rename(
        columns={
            "TRADE_DT": "trade_date",
            "S_INFO_WINDCODE": "index_code",
            "S_DQ_CLOSE": "close",
        }
    )
    raw["trade_date"] = raw["trade_date"].astype(str)
    raw["index_code"] = raw["index_code"].astype(str)
    raw = raw[["trade_date", "index_code", "close"]]
    raw = raw.drop_duplicates(subset=["trade_date"], keep="first")

    out = shell.merge(raw, on="trade_date", how="left")
    out["index_code"] = out["index_code"].fillna("000300.SH")
    out["missing_before_impute"] = out["close"].isna()
    out = _apply_close_imputation(out)
    out = out.sort_values("trade_date").reset_index(drop=True)

    output_path = output_dir / "hs300_daily.csv"
    out.to_csv(output_path, index=False, encoding="utf-8-sig")

    report = pd.DataFrame(
        [
            {
                "date_n_shell": int(len(shell)),
                "date_n_raw": int(len(raw)),
                "date_n_output": int(len(out)),
                "missing_before_impute_n": int(out["missing_before_impute"].sum()),
                "imputed_n": int((out["is_imputed"] == 1).sum()),
                "unresolved_n": int((out["impute_reason"] == "unresolved").sum()),
                "date_match_flag": int(len(shell) == len(out)),
            }
        ]
    )
    report_path = output_dir / "hs300_report.csv"
    report.to_csv(report_path, index=False, encoding="utf-8-sig")

    if out["trade_date"].duplicated().any():
        raise RuntimeError("Duplicate trade_date found in hs300 output.")
    if len(out) != len(shell):
        raise RuntimeError(
            f"Date alignment mismatch: shell={len(shell)}, output={len(out)}"
        )

    print("Completed HS300 request and alignment.")
    print(f"date_n_shell={len(shell)}, date_n_raw={len(raw)}, date_n_output={len(out)}")
    print(f"output={output_path}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()

