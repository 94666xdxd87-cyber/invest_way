"""
dca_strategy.py — DCA（定期定額）回測引擎。

策略規則：
  - 每月第一個交易日，固定投入 DCA_MONTHLY_AMOUNT 元買入股票
  - 買入股數 = floor(DCA_MONTHLY_AMOUNT / 當日收盤價)
  - 若當月剩餘現金不足買一股，則跳過該月（現金累積至下月）
  - 持股期間從不賣出，回測結束時以最後收盤價假設清算計算損益
  - 所有買入紀錄保留，用於計算 IRR / CAGR / Sortino 等績效指標
"""

import math
import numpy as np
import pandas as pd

from dca_config import DCA_MONTHLY_AMOUNT, DCA_BUY_DAY


def run_dca(prices: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """
    執行 DCA 回測。

    回傳 dict：
      trades        : list[dict]  每筆買入紀錄（含期末假設清算欄位）
      buy_signals   : list[(idx, price, shares)]
      total_invested: float  實際累計投入金額
      cash_residual : float  未用完的零頭現金
    """
    n              = len(prices)
    trades         = []
    buy_signals    = []
    cash           = 0.0          # 現金池（每月加入 DCA_MONTHLY_AMOUNT）
    shares_held    = 0
    total_invested = 0.0          # 累計已投入（已轉換成股票的金額）
    trade_counter  = 1

    # 記錄已處理過的「年月」，確保每月只買一次
    processed_ym: set[tuple[int, int]] = set()

    for i in range(n):
        ym = (dates[i].year, dates[i].month)

        # ── 每月注資 ──────────────────────────────────────────────────────────
        # 每月第一個交易日補充資金（只補一次）
        if ym not in processed_ym:
            cash += DCA_MONTHLY_AMOUNT
            processed_ym.add(ym)

            # ── 買入 ──────────────────────────────────────────────────────────
            shares = math.floor(cash / prices[i])
            if shares > 0:
                cost          = shares * prices[i]
                cash         -= cost
                shares_held  += shares
                total_invested += cost
                buy_signals.append((i, prices[i], shares))
                trades.append({
                    "trade_no":   trade_counter,
                    "buy_idx":    i,
                    "buy_date":   dates[i],
                    "buy_price":  round(prices[i], 4),
                    "shares":     shares,
                    "cost":       round(cost, 2),
                    # 賣出欄位先填期末清算值，後面統一覆蓋
                    "sell_idx":   n - 1,
                    "sell_date":  dates[-1],
                    "sell_price": round(prices[-1], 4),
                    "revenue":    round(shares * prices[-1], 2),
                    "pnl":        round(shares * prices[-1] - cost, 2),
                    "ret_pct":    round((shares * prices[-1] - cost) / cost * 100, 4),
                    "hold_days":  int((dates[-1] - dates[i]).days),
                    "closed":     False,
                })
                trade_counter += 1

    return {
        "trades":         trades,
        "buy_signals":    buy_signals,
        "total_invested": round(total_invested, 2),
        "cash_residual":  round(cash, 2),
    }
