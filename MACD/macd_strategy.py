"""
macd_strategy.py — 傳統 MACD 策略回測引擎

傳統 MACD 策略規則（純指標，無任何額外濾網）：
  買入：MACD 線由下往上穿越 Signal 線（金叉） → 動用所有現金全倉買入
  賣出：MACD 線由上往下穿越 Signal 線（死叉） → 全部持股賣出

資金管理：
  - BUY_RATIO  = 1.0（全倉買入）
  - SELL_RATIO = 1.0（全倉賣出）
  - 同一天最多執行一筆交易（金叉死叉同天時只執行金叉）

回傳格式與 pro/strategy.run_backtest 完全相同，
可直接接 performance.py / report.py / chart.py。
"""

import math
import numpy as np
import pandas as pd

from config import (
    INITIAL_CASH,
    BUY_RATIO, SELL_RATIO,
)
from data_loader import compute_macd, compute_ma


def run_backtest(prices: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """
    執行傳統 MACD 策略回測。

    回傳 dict，鍵值：
      trades        : list[dict]  每筆配對交易（含期末未平倉假設清算）
      buy_signals   : list[(idx, price, shares)]
      sell_signals  : list[(idx, price, shares)]
      tl_buy_drawn  : list  金叉標記（chart.py 相容格式）
      tl_sell_drawn : list  死叉標記
      ma45          : np.ndarray  MA 值序列（供 chart / performance 使用，傳統 MACD 不用於交易判斷）

    trades 欄位：
      trade_no, buy_idx, buy_date, buy_price, sell_idx, sell_date, sell_price,
      shares, cost, revenue, pnl, ret_pct, hold_days, closed,
      cash_after, shares_after, unrealized_pnl
    """
    n = len(prices)

    macd_line, signal_line, _ = compute_macd(prices)
    ma = compute_ma(prices)   # 僅供圖表 / performance 顯示，不參與交易判斷

    trades        = []
    buy_signals   = []
    sell_signals  = []
    tl_buy_drawn  = []   # 金叉標記：(xs, xe, slope, intercept, touches)
    tl_sell_drawn = []   # 死叉標記

    cash           = float(INITIAL_CASH)
    shares_held    = 0
    open_positions = []   # list of (buy_idx, buy_date, buy_price, shares)
    trade_counter  = 1

    for i in range(1, n):
        # 跳過指標尚未就緒的天（前 MACD_SLOW + MACD_SIGNAL - 2 天）
        if (np.isnan(macd_line[i])     or np.isnan(signal_line[i])
                or np.isnan(macd_line[i - 1]) or np.isnan(signal_line[i - 1])):
            continue

        prev_diff = macd_line[i - 1] - signal_line[i - 1]
        curr_diff = macd_line[i]     - signal_line[i]

        # 金叉：前一天 MACD < Signal，今天 MACD >= Signal
        is_golden = (prev_diff < 0) and (curr_diff >= 0)
        # 死叉：前一天 MACD > Signal，今天 MACD <= Signal
        is_dead   = (prev_diff > 0) and (curr_diff <= 0)

        # ── 買入（金叉） ───────────────────────────────────────────────────────
        # 優先處理買入；同天若同時發生金叉與死叉（理論上不會，邊界值才可能）
        # 以金叉為優先，不做賣出。
        if is_golden and cash > 0:
            shares = math.floor(cash * BUY_RATIO / prices[i])
            if shares > 0:
                cost         = shares * prices[i]
                cash        -= cost
                shares_held += shares
                buy_signals.append((i, prices[i], shares))
                open_positions.append((i, dates[i], prices[i], shares))
                trade_counter_before = trade_counter
                # 金叉標記（xs=xe，chart 畫垂直線）
                tl_buy_drawn.append((i, i, 0.0, prices[i], 0))
            continue   # 同天不再賣出

        # ── 賣出（死叉） ───────────────────────────────────────────────────────
        if is_dead and shares_held > 0:
            sell_sh = max(1, math.floor(shares_held * SELL_RATIO))
            if sell_sh > shares_held:
                sell_sh = shares_held

            revenue      = sell_sh * prices[i]
            cash        += revenue
            shares_held -= sell_sh
            sell_signals.append((i, prices[i], sell_sh))
            tl_sell_drawn.append((i, i, 0.0, prices[i], 0))

            # FIFO 配對
            remaining    = sell_sh
            new_open     = []
            batch_trades = []

            for b_idx, b_date, b_price, b_sh in open_positions:
                if remaining <= 0:
                    new_open.append((b_idx, b_date, b_price, b_sh))
                    continue
                sold       = min(b_sh, remaining)
                remaining -= sold
                p_cost     = b_price * sold
                p_rev      = prices[i] * sold
                p_pnl      = p_rev - p_cost
                batch_trades.append({
                    "trade_no":     trade_counter,
                    "buy_idx":      b_idx,
                    "buy_date":     b_date,
                    "buy_price":    round(b_price, 4),
                    "sell_idx":     i,
                    "sell_date":    dates[i],
                    "sell_price":   round(prices[i], 4),
                    "shares":       sold,
                    "cost":         round(p_cost, 2),
                    "revenue":      round(p_rev, 2),
                    "pnl":          round(p_pnl, 2),
                    "ret_pct":      round(p_pnl / p_cost * 100 if p_cost else 0, 4),
                    "hold_days":    int((dates[i] - b_date).days),
                    "closed":       True,
                    "cash_after":   round(cash, 2),
                    "shares_after": shares_held,
                })
                trade_counter += 1
                if b_sh - sold > 0:
                    new_open.append((b_idx, b_date, b_price, b_sh - sold))

            open_positions = new_open

            # unrealized_pnl：new_open 確定後才計算，保證數字一致
            unreal = round(
                shares_held * prices[i] - sum(s * p for _, _, p, s in open_positions),
                2,
            )
            for bt in batch_trades:
                bt["unrealized_pnl"] = unreal
                trades.append(bt)

    # ── 期末未平倉：以最後收盤價假設清算 ─────────────────────────────────────
    last_price = prices[-1]
    for pos_rank, (b_idx, b_date, b_price, b_sh) in enumerate(open_positions):
        p_cost = b_price * b_sh
        p_rev  = last_price * b_sh
        p_pnl  = p_rev - p_cost
        # shares_after：這筆之後還剩多少股
        remaining_shares = sum(s for _, _, _, s in open_positions[pos_rank + 1:])
        trades.append({
            "trade_no":       trade_counter,
            "buy_idx":        b_idx,
            "buy_date":       b_date,
            "buy_price":      round(b_price, 4),
            "sell_idx":       n - 1,
            "sell_date":      dates[-1],
            "sell_price":     round(last_price, 4),
            "shares":         b_sh,
            "cost":           round(p_cost, 2),
            "revenue":        round(p_rev, 2),
            "pnl":            round(p_pnl, 2),
            "ret_pct":        round(p_pnl / p_cost * 100 if p_cost else 0, 4),
            "hold_days":      int((dates[-1] - b_date).days),
            "closed":         False,
            "cash_after":     round(cash, 2),
            "shares_after":   remaining_shares,
            "unrealized_pnl": round(p_pnl, 2),
        })
        trade_counter += 1

    return {
        "trades":        trades,
        "buy_signals":   buy_signals,
        "sell_signals":  sell_signals,
        "tl_buy_drawn":  tl_buy_drawn,
        "tl_sell_drawn": tl_sell_drawn,
        "ma45":          ma,
    }
