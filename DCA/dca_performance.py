"""
dca_performance.py — DCA 策略績效計算。

與 performance.py 邏輯平行，但針對 DCA 特性調整：
  - DCA 無賣出，所有持倉均以期末收盤價假設清算
  - IRR 以每筆買入現金流 + 期末清算現金流計算
  - Sortino 計算時扣除每月新增本金（消除現金流污染）
"""

import numpy as np
import pandas as pd
import scipy.optimize as opt

from dca_config import RISK_FREE_RATE_ANNUAL, DCA_MONTHLY_AMOUNT


# ── IRR ───────────────────────────────────────────────────────────────────────

def calc_dca_irr(trades: list, prices: np.ndarray, dates: pd.DatetimeIndex) -> float | None:
    """
    以現金流折現法求年化 IRR。
    現金流：每次買入為負（流出），期末全部清算為正（流入）。
    """
    if not trades:
        return None

    base  = trades[0]["buy_date"]
    flows: dict[int, float] = {}

    for t in trades:
        d = int((t["buy_date"] - base).days)
        flows[d] = flows.get(d, 0) - t["cost"]

    last_day      = int((dates[-1] - base).days)
    last_price    = prices[-1]
    total_revenue = sum(t["shares"] * last_price for t in trades)
    flows[last_day] = flows.get(last_day, 0) + total_revenue

    days_sorted = sorted(flows)
    cf = [flows[d] for d in days_sorted]
    ty = [d / 365.0 for d in days_sorted]

    def npv(r):
        return sum(c / (1 + r) ** t for c, t in zip(cf, ty))

    try:
        irr = opt.brentq(npv, -0.9999, 50.0, maxiter=1000)
        return round(irr * 100, 2)
    except Exception:
        return None


# ── 每日帳戶市值重建 ──────────────────────────────────────────────────────────

def build_dca_daily_df(
    prices:        np.ndarray,
    dates:         pd.DatetimeIndex,
    trades:        list,
    cash_residual: float,
) -> pd.DataFrame:
    """
    逐日重建 DCA 帳戶狀態。

    欄位：
      Date, Close, 累計投入, 持有股數, 帳戶市值, 未實現損益, 報酬率%, 當日新增投入
      （「當日新增投入」供 Sortino 計算時扣除現金流污染用，非投入日為 0）
    """
    buy_map: dict[int, list] = {}
    for t in trades:
        buy_map.setdefault(t["buy_idx"], []).append(t)

    shares_held    = 0
    total_invested = 0.0
    rows           = []

    for i in range(len(prices)):
        new_investment = 0.0      # 該日實際轉換成股票的本金（非投入日為 0）
        if i in buy_map:
            for t in buy_map[i]:
                shares_held    += t["shares"]
                total_invested += t["cost"]
                new_investment += t["cost"]

        market_val = round(shares_held * prices[i] + cash_residual, 2)
        unreal_pnl = round(market_val - total_invested, 2)
        ret_pct    = round(unreal_pnl / total_invested * 100, 2) if total_invested > 0 else 0.0

        rows.append({
            "Date":       dates[i].strftime("%Y-%m-%d"),
            "Close":      round(prices[i], 4),
            "累計投入":   round(total_invested, 2),
            "持有股數":   shares_held,
            "帳戶市值":   market_val,
            "未實現損益": unreal_pnl,
            "報酬率%":    ret_pct,
            "當日新增投入": round(new_investment, 2),
        })

    return pd.DataFrame(rows)


# ── 績效彙整 ──────────────────────────────────────────────────────────────────

def calc_dca_performance(
    trades:        list,
    daily_df:      pd.DataFrame,
    dates:         pd.DatetimeIndex,
    prices:        np.ndarray,
    cash_residual: float,
) -> dict:
    """
    計算並回傳 DCA 所有績效指標。
    """
    if not trades:
        return {}

    total_invested = sum(t["cost"] for t in trades)
    total_months   = len(trades)
    last_price     = prices[-1]
    total_shares   = sum(t["shares"] for t in trades)
    final_value    = round(total_shares * last_price + cash_residual, 2)
    total_pnl      = round(final_value - total_invested, 2)
    cumulative_ret = round(total_pnl / total_invested, 6) if total_invested > 0 else 0.0

    avg_cost = round(total_invested / total_shares, 4) if total_shares > 0 else 0.0

    # CAGR
    holding_years = (dates[-1] - trades[0]["buy_date"]).days / 365.0
    cagr = None
    if holding_years > 0 and final_value > 0 and total_invested > 0:
        cagr = round((final_value / total_invested) ** (1.0 / holding_years) - 1, 6)

    # IRR
    irr_val = calc_dca_irr(trades, prices, dates)

    # MDD
    daily_val        = daily_df["帳戶市值"].values.astype(float)
    peak, max_dd = float(daily_val[0]), 0.0
    for v in daily_val:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    # ── Sortino Ratio ─────────────────────────────────────────────────────────
    # 關鍵修正：每月投入當日帳戶市值因新增本金而跳升，
    # 若直接用 np.diff(market_val) / market_val[:-1] 會把新增本金誤算為市場報酬。
    # 正確做法：市值變動先扣除當日新增本金，剩下才是純市場報酬。
    #   pure_change[i] = (market_val[i] - market_val[i-1]) - new_investment[i]
    #   daily_return[i] = pure_change[i] / market_val[i-1]
    sortino_ratio = None
    if len(daily_val) > 1:
        daily_inflow   = daily_df["當日新增投入"].values[1:].astype(float)  # 與 diff 對齊
        price_change   = np.diff(daily_val) - daily_inflow   # 扣除本金後的純市場變動
        daily_returns  = price_change / daily_val[:-1]        # 純市場報酬率
        rf_daily       = RISK_FREE_RATE_ANNUAL / 252
        excess_returns = daily_returns - rf_daily
        downside_part  = np.minimum(excess_returns, 0.0)      # 補 0，保留總天數當分母
        downside_std   = np.sqrt(np.mean(downside_part ** 2))
        if downside_std > 0:
            sortino_ratio = round(
                (np.mean(excess_returns) / downside_std) * np.sqrt(252), 4
            )

    return {
        "total_months":   total_months,
        "total_invested": round(total_invested, 2),
        "cash_residual":  round(cash_residual, 2),
        "total_shares":   total_shares,
        "avg_cost":       avg_cost,
        "last_price":     round(last_price, 4),
        "final_value":    final_value,
        "total_pnl":      total_pnl,
        "cumulative_ret": cumulative_ret,
        "cagr":           cagr,
        "irr_val":        irr_val,
        "max_drawdown":   round(max_dd, 6),
        "sortino_ratio":  sortino_ratio,
        "monthly_amount": DCA_MONTHLY_AMOUNT,
        "date_range": (
            f"{dates[0].strftime('%Y-%m-%d')} ~ {dates[-1].strftime('%Y-%m-%d')}"
        ),
    }
