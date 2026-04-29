from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import backtrader as bt
import pandas as pd

from _SFP import build_target_weights, filter_by_tradability_for_buy, get_rebalance_dates, signal_rank
from _StrategyConfig import StrategyConfig


class FactorPandasData(bt.feeds.PandasData):
    lines = ("can_buy", "can_sell")
    params = (
        ("datetime", None),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", -1),
        ("can_buy", "can_buy"),
        ("can_sell", "can_sell"),
    )


class DailyRebalanceStrategy(bt.Strategy):
    params = dict(
        rebalance_dates=None,
        signal_map=None,
        top_n=20,
        weight_mode="equal",
        factor_direction="top",
        commission=0.001,
        slippage=0.0005,
    )

    def __init__(self):
        self._rebalance_dates = set(self.p.rebalance_dates or [])
        self._signal_map = self.p.signal_map or {}
        self.exec_logs: List[dict] = []
        self.nav_logs: List[dict] = []
        self._processed_date: str | None = None
        self._open_orders = []

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            if order in self._open_orders:
                self._open_orders.remove(order)

    def _on_bar(self):
        cur_date = bt.num2date(self.datas[0].datetime[0]).date().isoformat()
        # In multi-data setups Backtrader may invoke next/prenext multiple times per same date.
        # Ensure we process each trading date once.
        if self._processed_date == cur_date:
            return
        self._processed_date = cur_date
        if cur_date not in self._rebalance_dates:
            self.nav_logs.append({"date": cur_date, "portfolio_value": self.broker.getvalue()})
            return

        # Cancel stale pending orders before a fresh rebalance batch.
        for o in list(self._open_orders):
            self.cancel(o)

        signal_day = self._signal_map.get(cur_date)
        if signal_day is None or signal_day.empty:
            return

        ranked = signal_rank(signal_day, self.p.factor_direction)
        tradable = filter_by_tradability_for_buy(ranked)
        target_w = build_target_weights(tradable, top_n=self.p.top_n, weight_mode=self.p.weight_mode)
        target_codes = set(target_w.keys())

        # map code -> data feed
        code2data = {d._name: d for d in self.datas}
        cur_value = self.broker.getvalue()

        # Long-only safety: flatten any accidental short positions first.
        forced_cover_n = 0
        for d in self.datas:
            pos = self.getposition(d).size
            if pos < 0:
                o = self.order_target_size(data=d, target=0.0)
                if o is not None:
                    self._open_orders.append(o)
                forced_cover_n += 1

        # sell first
        blocked_sell = 0
        for d in self.datas:
            code = d._name
            pos = self.getposition(d).size
            if pos <= 0:
                continue
            can_sell = int(getattr(d, "can_sell")[0]) if len(d) > 0 else 0
            if code not in target_codes:
                if can_sell == 1:
                    o = self.order_target_size(data=d, target=0.0)
                    if o is not None:
                        self._open_orders.append(o)
                else:
                    blocked_sell += 1

        # buy / rebalance second (cash-constrained to avoid negative cash)
        cash_now = self.broker.getcash()
        buy_candidates = []
        for code, w in target_w.items():
            d = code2data.get(code)
            if d is None or len(d) == 0:
                continue
            if int(getattr(d, "can_buy")[0]) != 1:
                continue
            px = float(d.close[0])
            if px <= 0:
                continue
            target_value = max(0.0, w * cur_value)
            current_value = self.getposition(d).size * px
            need_value = max(0.0, target_value - current_value)
            if need_value > 0:
                buy_candidates.append((code, d, px, need_value))

        blocked_buy = 0
        for code, w in target_w.items():
            d = code2data.get(code)
            if d is None or len(d) == 0:
                continue
            can_buy = int(getattr(d, "can_buy")[0])
            if can_buy != 1:
                blocked_buy += 1

        total_need = sum(x[3] for x in buy_candidates)
        scale = 1.0
        if total_need > 0:
            # include slippage and commission costs
            gross_need = total_need * (1.0 + self.p.commission + self.p.slippage)
            if gross_need > cash_now:
                scale = cash_now / gross_need if gross_need > 0 else 0.0

        for code, d, px, need_value in buy_candidates:
            alloc_value = need_value * scale
            target_size = self.getposition(d).size + (alloc_value / px if px > 0 else 0.0)
            o = self.order_target_size(data=d, target=target_size)
            if o is not None:
                self._open_orders.append(o)

        actual_hold_n = sum(1 for d in self.datas if self.getposition(d).size > 0)
        short_hold_n = sum(1 for d in self.datas if self.getposition(d).size < 0)
        self.exec_logs.append(
            {
                "date": cur_date,
                "planned_top_n": self.p.top_n,
                "actual_hold_n": actual_hold_n,
                "short_hold_n": short_hold_n,
                "forced_cover_n": forced_cover_n,
                "blocked_buy_n": blocked_buy,
                "blocked_sell_n": blocked_sell,
                "cash_after_rebalance": self.broker.getcash(),
            }
        )
        self.nav_logs.append({"date": cur_date, "portfolio_value": self.broker.getvalue()})

    def prenext(self):
        self._on_bar()

    def next(self):
        self._on_bar()

    def stop(self):
        # ensure last day is recorded
        cur_date = bt.num2date(self.datas[0].datetime[0]).date().isoformat()
        if not self.nav_logs or self.nav_logs[-1]["date"] != cur_date:
            self.nav_logs.append({"date": cur_date, "portfolio_value": self.broker.getvalue()})


class SlippageCommission(bt.CommInfoBase):
    params = (("commission", 0.001), ("stocklike", True), ("commtype", bt.CommInfoBase.COMM_PERC),)

    def _getcommission(self, size, price, pseudoexec):
        return abs(size) * price * self.p.commission


@dataclass
class ExecutionResult:
    nav_df: pd.DataFrame
    execution_log: pd.DataFrame


def run_execution(panel: pd.DataFrame, cfg: StrategyConfig) -> ExecutionResult:
    if cfg.signal_lag != 1:
        raise ValueError("Backtrader execution currently supports signal_lag=1 only.")

    all_dates = sorted(pd.to_datetime(panel["date"]).drop_duplicates().tolist())
    all_dates = [pd.Timestamp(d).normalize() for d in all_dates]
    rb_dates_raw = get_rebalance_dates(all_dates, cfg.rebalance_freq)
    rb_dates = [pd.Timestamp(d).normalize() for d in rb_dates_raw]
    next_day = {all_dates[i]: all_dates[i + 1] for i in range(len(all_dates) - 1)}

    signal_map: Dict[str, pd.DataFrame] = {}
    rebalance_exec_dates: List[str] = []
    for d in rb_dates:
        if d not in next_day:
            continue
        exec_d = next_day[d]
        rebalance_exec_dates.append(exec_d.date().isoformat())
        sig = panel.loc[pd.to_datetime(panel["date"]).dt.normalize() == d, ["code", "factor_score", "can_buy"]].copy()
        signal_map[exec_d.date().isoformat()] = sig

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cfg.initial_cash)
    cerebro.broker.addcommissioninfo(SlippageCommission(commission=cfg.commission))
    cerebro.broker.set_slippage_perc(cfg.slippage, slip_open=False, slip_limit=False, slip_match=True, slip_out=False)

    # add per-stock data feeds
    for code, dfc in panel.groupby("code", sort=False):
        dfd = dfc[["date", "open", "high", "low", "close", "volume", "can_buy", "can_sell"]].copy()
        dfd = dfd.sort_values("date").set_index("date")
        feed = FactorPandasData(dataname=dfd)
        cerebro.adddata(feed, name=code)

    # analyzer for daily portfolio value
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn", timeframe=bt.TimeFrame.Days)
    cerebro.addstrategy(
        DailyRebalanceStrategy,
        rebalance_dates=rebalance_exec_dates,
        signal_map=signal_map,
        top_n=cfg.top_n,
        weight_mode=cfg.weight_mode,
        factor_direction=cfg.factor_direction,
        commission=cfg.commission,
        slippage=cfg.slippage,
    )

    results = cerebro.run()
    strat = results[0]

    nav_rows = []
    for x in strat.nav_logs:
        nav_rows.append(
            {
                "date": pd.to_datetime(x["date"]).normalize(),
                "portfolio_value": float(x["portfolio_value"]),
            }
        )
    nav_df = pd.DataFrame(nav_rows).sort_values("date").reset_index(drop=True)
    nav_df["date"] = pd.to_datetime(nav_df["date"])
    nav_df["strategy_nav"] = nav_df["portfolio_value"] / nav_df["portfolio_value"].iloc[0]
    nav_df = nav_df[["date", "strategy_nav"]]

    exec_df = pd.DataFrame(strat.exec_logs)
    return ExecutionResult(nav_df=nav_df, execution_log=exec_df)
