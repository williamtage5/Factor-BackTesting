from __future__ import annotations

import pandas as pd


def get_rebalance_dates(all_dates: list[pd.Timestamp], freq: str) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(all_dates).sort_values()
    if freq == "W":
        return list(pd.Series(idx, index=idx).resample("W-FRI").last().dropna().values)
    if freq == "M":
        return list(pd.Series(idx, index=idx).resample("ME").last().dropna().values)
    if freq == "Q":
        return list(pd.Series(idx, index=idx).resample("QE").last().dropna().values)
    raise ValueError(f"Unsupported rebalance_freq: {freq}")


def signal_rank(day_df: pd.DataFrame, factor_direction: str) -> pd.DataFrame:
    ascending = factor_direction == "bottom"
    return day_df.sort_values("factor_score", ascending=ascending)


def filter_by_tradability_for_buy(day_df: pd.DataFrame) -> pd.DataFrame:
    return day_df.loc[day_df["can_buy"].fillna(0).astype(int) == 1].copy()


def build_target_weights(
    ranked_df: pd.DataFrame, top_n: int, weight_mode: str = "equal"
) -> dict[str, float]:
    selected = ranked_df.head(top_n).copy()
    if selected.empty:
        return {}

    if weight_mode == "equal":
        w = 1.0 / len(selected)
        return {c: w for c in selected["code"].tolist()}

    # risk_parity placeholder: fallback to equal
    w = 1.0 / len(selected)
    return {c: w for c in selected["code"].tolist()}

