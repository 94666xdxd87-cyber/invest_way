"""
performance.py — IRR 計算、每日帳戶狀態重建、績效指標彙整。
"""

import numpy as np
import pandas as pd
import scipy.optimize as opt

from config import INITIAL_CASH

# 無風險利率（台灣定存年利率 1.7%）
RISK_FREE_RATE_ANNUAL = 0.017


# ── IRR 計算 ──────────────────────────────────────────────────────────────────

def calc_irr(trades: list, closed_only: bool = False) -> float | None:
    """
    以現金流折現法求解年化 IRR。

    closed_only=False → 含期末未平倉假設清算（trades 中 closed=False 的那筆）
    closed_only=True  → 僅計算已實現平倉交易

    回傳百分比數值（已 × 100），例如 12.34；無法計算時回傳 None。
    """
    target = [t for t in trades if (not closed_only) or t["closed"]]
    if not target:
        return None

    base   = target[0]["buy_date"]
    flows: dict[int, float] = {}

    for t in target:
        bd = int((t["buy_date"]  - base).days)
        sd = int((t["sell_date"] - base).days)
        flows[bd] = flows.get(bd, 0) - t["cost"]
        flows[sd] = flows.get(sd, 0) + t["revenue"]

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


# ── 每日帳戶狀態重建 ──────────────────────────────────────────────────────────

def build_daily_df(
    prices: np.ndarray,
    dates:  pd.DatetimeIndex,
    ma45:   np.ndarray,
    trades: list,
) -> pd.DataFrame:
    """
    逐日重建帳戶狀態，回傳 DataFrame，欄位：
      Date, Close, MA45, State, Signal,
      目前持有資金, 目前持有股票, 目前損益, 資產總價值
    """
    n = len(prices)

    buy_map:  dict[int, list] = {}
    sell_map: dict[int, list] = {}
    for t in trades:
        buy_map.setdefault(t["buy_idx"], []).append(t)
        if t["closed"]:
            sell_map.setdefault(t["sell_idx"], []).append(t)

    sim_cash   = float(INITIAL_CASH)
    sim_shares = 0
    sim_cost   = 0.0
    rows       = []

    for i in range(n):
        signals = []

        if i in buy_map:
            tb = sum(t["shares"] for t in buy_map[i])
            cb = sum(t["cost"]   for t in buy_map[i])
            sim_cash   -= cb
            sim_shares += tb
            sim_cost   += cb
            signals.append(f"買入 {tb}股 (投入{cb:,.0f})")

        if i in sell_map:
            ts = sum(t["shares"]  for t in sell_map[i])
            rs = sum(t["revenue"] for t in sell_map[i])
            cost_deducted = sim_cost * (ts / sim_shares) if sim_shares > 0 else 0.0
            sim_cash   += rs
            sim_shares -= ts
            sim_cost    = max(0.0, sim_cost - cost_deducted)
            signals.append(f"賣出 {ts}股 (收入{rs:,.0f})")

        unreal_pnl   = (sim_shares * prices[i] - sim_cost) if sim_shares > 0 else 0.0
        realized_pnl = sim_cash - INITIAL_CASH
        current_pnl  = round(realized_pnl + unreal_pnl, 2)
        total_asset  = round(sim_cash + sim_shares * prices[i], 2)

        rows.append({
            "Date":      dates[i].strftime("%Y-%m-%d"),
            "Close":     round(prices[i], 4),
            "MA45":      round(ma45[i], 4) if not np.isnan(ma45[i]) else "",
            "State":     "低於MA45" if (not np.isnan(ma45[i]) and prices[i] < ma45[i]) else "高於MA45",
            "Signal":    " / ".join(signals),
            "目前持有資金": round(sim_cash, 2),
            "目前持有股票": sim_shares,
            "目前損益":    current_pnl,
            "資產總價值":  total_asset,
        })

    return pd.DataFrame(rows)


# ── 績效指標彙整 ──────────────────────────────────────────────────────────────

def calc_performance(
    trades:   list,
    daily_df: pd.DataFrame,
    dates:    pd.DatetimeIndex,
) -> dict:
    """
    計算並回傳所有績效指標：
      irr_val, irr_closed_only, cagr,
      total_cost, total_revenue, total_pnl, realized_pnl,
      win_trades, win_rate,
      final_cash, final_shares, final_pnl, final_total_asset,
      max_drawdown, cumulative_return, date_range
    """
    closed_trades = [t for t in trades if t["closed"]]

    total_cost    = sum(t["cost"]    for t in trades)
    total_revenue = sum(t["revenue"] for t in trades)
    total_pnl     = total_revenue - total_cost
    realized_pnl  = sum(t["pnl"] for t in closed_trades)

    win_trades = sum(1 for t in closed_trades if t["pnl"] > 0)
    win_rate   = win_trades / len(closed_trades) * 100 if closed_trades else 0.0

    irr_val         = calc_irr(trades, closed_only=False)
    irr_closed_only = calc_irr(trades, closed_only=True)

    final_cash        = daily_df["目前持有資金"].iloc[-1]
    final_shares      = daily_df["目前持有股票"].iloc[-1]
    final_pnl         = daily_df["目前損益"].iloc[-1]
    final_total_asset = daily_df["資產總價值"].iloc[-1]

    cumulative_return = (float(final_total_asset) - INITIAL_CASH) / INITIAL_CASH

    cagr = None
    if trades:
        holding_years = (dates[-1] - trades[0]["buy_date"]).days / 365.0
        if holding_years > 0 and float(final_total_asset) > 0:
            cagr = round(
                (float(final_total_asset) / float(INITIAL_CASH)) ** (1.0 / holding_years) - 1,
                6,
            )

    # 最大回撤（MDD）
    daily_asset = daily_df["資產總價值"].values.astype(float)
    peak, max_dd = float(INITIAL_CASH), 0.0
    for asset in daily_asset:
        if asset > peak:
            peak = asset
        dd = (asset - peak) / peak
        if dd < max_dd:
            max_dd = dd

    # ── Sortino Ratio ────────────────────────────────────────────────────────
    # 以每日資產總價值計算每日報酬率，再與無風險日利率比較
    # 下行離差（Downside Deviation）分母為「總交易日數」，超額報酬 >= 0 的天以 0 代入，
    # 而非直接剔除，否則分母縮小會誇大下行標準差並低估 Sortino Ratio。
    sortino_ratio = None
    if len(daily_asset) > 1:
        daily_returns  = np.diff(daily_asset) / daily_asset[:-1]          # 每日報酬率
        rf_daily       = RISK_FREE_RATE_ANNUAL / 252                       # 無風險日利率
        excess_returns = daily_returns - rf_daily                          # 超額報酬
        # 下行部分：超額報酬 < 0 保留原值；>= 0 填 0（分母仍為總天數）
        downside_part  = np.minimum(excess_returns, 0.0)
        downside_std   = np.sqrt(np.mean(downside_part ** 2))              # 下行標準差
        if downside_std > 0:
            mean_excess   = np.mean(excess_returns)
            sortino_ratio = round(
                (mean_excess / downside_std) * np.sqrt(252), 4             # 年化
            )

    return {
        "irr_val":           irr_val,
        "irr_closed_only":   irr_closed_only,
        "cagr":              cagr,
        "total_cost":        round(total_cost, 2),
        "total_revenue":     round(total_revenue, 2),
        "total_pnl":         round(total_pnl, 2),
        "realized_pnl":      round(realized_pnl, 2),
        "win_trades":        win_trades,
        "win_rate":          win_rate,
        "final_cash":        final_cash,
        "final_shares":      final_shares,
        "final_pnl":         final_pnl,
        "final_total_asset": final_total_asset,
        "max_drawdown":      round(max_dd, 6),
        "cumulative_return": round(cumulative_return, 6),
        "sortino_ratio":    sortino_ratio,
        "date_range": (
            f"{dates[0].strftime('%Y-%m-%d')} ~ {dates[-1].strftime('%Y-%m-%d')}"
        ),
    }
