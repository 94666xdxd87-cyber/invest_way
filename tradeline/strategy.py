"""
strategy.py — 趨勢線搜尋 + 回測引擎。

買點邏輯（下降壓力線突破）：
  - 第 i 天收盤後，確認第 i-LOCAL_WIN 天是局部高點，畫出下降壓力線
  - 第 i+1 天開盤才能執行：若 prices[i+1] > line_val(i+1) * (1 + BUY_BUFFER) → 買入
  - 不再參考 MA45 濾網

賣點邏輯（上升支撐線跌破 或 MA45 相關判斷）：
  - 第 i 天收盤後，確認第 i-LOCAL_WIN 天是局部低點，畫出上升支撐線
  - 第 i+1 天開盤才能執行：若 prices[i+1] < line_val(i+1) * (1 - SELL_BUFFER) → 賣出 SELL_RATIO 比例持股（FIFO）
  - 若找不到上升支撐線，進入 MA45 判斷：
      1. 收盤 > MA45 × (1 + MA_EARLY_SELL_CAP)  → 提前賣出（過熱出場，僅 mode=sell 時觸發）
      2. 收盤 < MA45                              → 正常賣出（跌破均線）
      3. 介於兩者之間（100%~125%）               → 不賣，fallback 找買點

交替狀態機（雙向 fallback）：
  mode="buy"  → 先找買點；買到 → 切 sell；找不到 → 再找賣點；都沒有 → 下一天
  mode="sell" → 先找賣點；賣到 → 切 buy ；找不到 → 再找買點；都沒有 → 下一天
  同一天最多執行一筆交易（買或賣），不會連續兩筆。

【修正說明】
  原始版本：在第 i 天迴圈內，畫完趨勢線後立刻用 prices[i] 判斷突破 → 未來偏差
  修正版本：趨勢線在第 i 天收盤後確認；實際交易改在第 i+1 天迴圈執行
            用 pending_buy_tl / pending_sell_tl 暫存，下一天才觸發
"""

import math
import numpy as np
import pandas as pd
from config import (
    MA_PERIOD, LOCAL_WIN, LOOKBACK_DAYS, MIN_TOUCHES, TOLERANCE,
    MIN_GAP, MIN_HOLD_DAYS, MIN_TL_SPAN,
    INITIAL_CASH, BUY_RATIO, SELL_RATIO,
    TL_SORT_PRIORITY, MA_BUY_CAP, MA_EARLY_SELL_CAP,
    BUY_BUFFER, SELL_BUFFER,
)
from data_loader import compute_ma


# ── 局部極值點 ────────────────────────────────────────────────────────────────

def find_local_extrema(prices: np.ndarray) -> tuple[set, set]:
    """
    以左右各 LOCAL_WIN 個交易日為窗口，找出局部最高點（highs）與最低點（lows）。
    回傳 (highs: set[int], lows: set[int])，元素為索引值。
    """
    n = len(prices)
    highs, lows = set(), set()
    for i in range(LOCAL_WIN, n - LOCAL_WIN):
        lo     = max(0, i - LOCAL_WIN)
        hi     = min(n - 1, i + LOCAL_WIN)
        window = prices[lo: hi + 1]
        if prices[i] == max(window):
            highs.add(i)
        if prices[i] == min(window):
            lows.add(i)
    return highs, lows


# ── 趨勢線搜尋 ────────────────────────────────────────────────────────────────

def find_best_trendline(
    current_idx: int,
    anchor_set: set,
    prices: np.ndarray,
    direction: str,          # "down"（下降壓力線）或 "up"（上升支撐線）
) -> tuple | None:
    """
    從 current_idx 往前 LOOKBACK_DAYS 天的範圍內，
    對所有局部極值點做 C(n,2) 兩兩組合，窮舉所有候選趨勢線。

    direction="down"：斜率必須 < 0（下降壓力線），任何點不得顯著突破上方。
    direction="up"  ：斜率必須 > 0（上升支撐線），任何點不得顯著跌破下方。

    優先權（由高到低）：
      1. 觸碰點數量最多
      2. 斜率絕對值最小
      3. 橫跨時間幅度最長（右端點索引 - 左端點索引）

    回傳 (slope, intercept, touches) 或 None。
    """
    left_bound = max(0, current_idx - LOOKBACK_DAYS)
    candidates = sorted(i for i in anchor_set if left_bound <= i <= current_idx)
    if len(candidates) < 2:
        return None

    slope_sign = 1 if direction == "down" else -1   # down → 要求斜率 < 0

    valid_lines = []  # list of (touches, abs_slope, span, slope, intercept)

    for i, left_idx in enumerate(candidates):
        for right_idx in candidates[i + 1:]:
            span = right_idx - left_idx
            if span < MIN_TL_SPAN:
                continue

            slope     = (prices[right_idx] - prices[left_idx]) / span
            if slope * slope_sign >= 0:
                continue                            # 方向不符，跳過

            intercept = prices[left_idx] - slope * left_idx

            # 驗證趨勢線在 [left_idx, right_idx] 區間內未被顯著違反
            violated = False
            for xi in range(left_idx, right_idx + 1):
                lv = slope * xi + intercept
                if lv <= 0:
                    continue
                if direction == "down" and prices[xi] > lv * (1 + TOLERANCE):
                    violated = True; break
                if direction == "up"   and prices[xi] < lv * (1 - TOLERANCE):
                    violated = True; break
            if violated:
                continue

            # 計算觸碰次數（錨點集合中，落在趨勢線容差內的點）
            touches = sum(
                1 for xi in anchor_set
                if left_idx <= xi <= right_idx
                and (lv := slope * xi + intercept) > 0
                and abs(prices[xi] - lv) / lv <= TOLERANCE
            )
            if touches < MIN_TOUCHES:
                continue

            valid_lines.append((touches, abs(slope), span, slope, intercept))

    if not valid_lines:
        return None

    # 依 TL_SORT_PRIORITY 動態組合排序鍵
    # valid_lines 格式：(touches, abs_slope, span, slope, intercept)
    # touches 越多越好、abs_slope 越小越好、span 越長越好
    _field_idx  = {'touches': 0, 'slope': 1, 'span': 2}
    _field_sign = {'touches': 1, 'slope': -1, 'span': 1}  # 1=越大越好, -1=越小越好

    def sort_key(x):
        return tuple(_field_sign[f] * x[_field_idx[f]] for f in TL_SORT_PRIORITY)

    best = max(valid_lines, key=sort_key)
    return (best[3], best[4], best[0])


# ── 回測引擎 ──────────────────────────────────────────────────────────────────

def run_backtest(prices: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """
    執行完整回測，回傳：
      trades        : list[dict]，每筆配對交易（含期末未平倉假設清算）
      buy_signals   : list[(idx, price, shares)]
      sell_signals  : list[(idx, price, shares)]
      tl_buy_drawn  : list[(xs, xe, slope, intercept, touches)]  下降壓力線
      tl_sell_drawn : list[(xs, xe, slope, intercept, touches)]  上升支撐線
      ma45          : np.ndarray，MA 值序列

    trades 欄位說明：
      closed=True  → 真實成交；cost/revenue/pnl 為實際金額
      closed=False → 期末未平倉，以最後收盤價假設清算，用於 IRR/CAGR 計算
      unrealized_pnl → 該筆交易成交當下，帳上仍持有的其他部位浮動損益
                        （在整批 FIFO 配對完成後才計算，確保數字一致）
    """
    n    = len(prices)
    ma45 = compute_ma(prices)
    # 【修正】不再預先對全資料計算極值（會偷看未來）
    # 改為在步驟三逐日增量更新，每天只確認 i - LOCAL_WIN 這個點
    highs, lows = set(), set()

    trades        = []
    buy_signals   = []
    sell_signals  = []
    tl_buy_drawn  = []
    tl_sell_drawn = []

    active_buy_tl   = None   # 當天已可用的下降壓力線（前一天收盤後確認）
    active_sell_tl  = None   # 當天已可用的上升支撐線（前一天收盤後確認）
    pending_buy_tl  = None   # 今天收盤後剛畫好，明天才能用
    pending_sell_tl = None   # 今天收盤後剛畫好，明天才能用
    last_buy_idx    = -999
    last_sell_idx   = -999
    mode            = "buy"   # 交替狀態機："buy" 或 "sell"

    cash           = float(INITIAL_CASH)
    shares_held    = 0
    # open_positions: list of (buy_idx, buy_date, buy_price_exact, shares)
    # buy_price_exact 保留原始浮點，避免 round 累積成本誤差
    open_positions = []
    trade_counter  = 1

    # 預先計算緩衝倍數，避免迴圈內重複運算
    buy_threshold  = 1 + BUY_BUFFER   # 例：1.001
    sell_threshold = 1 - SELL_BUFFER  # 例：0.999

    for i in range(MA_PERIOD, n):
        if np.isnan(ma45[i]):
            continue

        # ── 步驟一：將昨天 pending 的趨勢線升級為今天可用（active） ──────────
        # pending_*_tl 是上一個迴圈（第 i-1 天）收盤後剛畫好的線，
        # 現在進入第 i 天，才正式允許用來觸發交易。
        if pending_buy_tl is not None:
            active_buy_tl  = pending_buy_tl
            pending_buy_tl = None
        if pending_sell_tl is not None:
            active_sell_tl  = pending_sell_tl
            pending_sell_tl = None

        # ── 步驟二：買入 / 賣出（使用當天已生效的趨勢線） ───────────────────
        # 此時 active_*_tl 最早也是前一天收盤後確認的線，無未來偏差。
        # 雙向 fallback：mode="buy" 先找買點，找不到再找賣點；
        #                mode="sell" 先找賣點，找不到再找買點。
        # 同一天最多成交一筆，用 traded 旗標防止雙重成交。

        traded = False

        # ── 主要方向 ────────────────────────────────────────────────────────────
        if mode == "buy":
            # 先找買點
            if not traded and cash > 0 and active_buy_tl is not None:
                sl, ic, _ = active_buy_tl
                lv = sl * i + ic
                ma_ok = np.isnan(ma45[i]) or (prices[i] <= ma45[i] * (1 + MA_BUY_CAP))
                if lv > 0 and prices[i] > lv * buy_threshold and (i - last_buy_idx) >= MIN_GAP and ma_ok:
                    shares = math.floor(cash * BUY_RATIO / prices[i])
                    if shares > 0:
                        cost         = shares * prices[i]
                        cash        -= cost
                        shares_held += shares
                        buy_signals.append((i, prices[i], shares))
                        open_positions.append((i, dates[i], prices[i], shares))
                        last_buy_idx  = i
                        active_buy_tl = None
                        mode          = "sell"
                        traded        = True
            # 找不到買點 → fallback 找賣點（上升支撐線）
            if not traded and shares_held > 0 and active_sell_tl is not None:
                sl, ic, _ = active_sell_tl
                lv = sl * i + ic
                if (lv > 0
                        and prices[i] < lv * sell_threshold
                        and (i - last_sell_idx) >= MIN_GAP
                        and (i - last_buy_idx)  >  MIN_HOLD_DAYS):
                    traded = True   # 進入賣出流程，下方統一處理
            # 找不到上升支撐線 → MA45 fallback 賣出
            if (not traded
                    and shares_held > 0
                    and active_sell_tl is None
                    and not np.isnan(ma45[i])
                    and prices[i] < ma45[i]
                    and (i - last_sell_idx) >= MIN_GAP
                    and (i - last_buy_idx)  >  MIN_HOLD_DAYS):
                traded = True   # 進入賣出流程，下方統一處理

        else:  # mode == "sell"
            # 先找賣點（上升支撐線）
            if not traded and shares_held > 0 and active_sell_tl is not None:
                sl, ic, _ = active_sell_tl
                lv = sl * i + ic
                if (lv > 0
                        and prices[i] < lv * sell_threshold
                        and (i - last_sell_idx) >= MIN_GAP
                        and (i - last_buy_idx)  >  MIN_HOLD_DAYS):
                    traded = True   # 進入賣出流程，下方統一處理

            # 找不到上升支撐線 → 三段式 MA45 判斷（僅 mode=sell）
            # ┌─ 區間 1：收盤 > MA45 × (1 + MA_EARLY_SELL_CAP)  → 過熱提前賣出
            # ├─ 區間 2：收盤 < MA45                             → 跌破均線賣出
            # └─ 區間 3：介於兩者之間（100%~125%）               → 不賣，留給 fallback 買點
            if (not traded
                    and shares_held > 0
                    and active_sell_tl is None
                    and not np.isnan(ma45[i])
                    and (i - last_sell_idx) >= MIN_GAP
                    and (i - last_buy_idx)  >  MIN_HOLD_DAYS):

                _early_cap = MA_EARLY_SELL_CAP  # None 表示停用提前賣出功能
                _above_ma  = prices[i] > ma45[i]
                _over_cap  = (
                    _early_cap is not None
                    and prices[i] > ma45[i] * (1 + _early_cap)
                )

                if _over_cap:
                    # 區間 1：過熱 → 提前賣出
                    traded = True
                elif not _above_ma:
                    # 區間 2：跌破 MA45 → 正常賣出
                    traded = True
                # 區間 3：介於中間 → 什麼都不做，讓 fallback 找買點

            # 找不到賣點 → fallback 找買點
            if not traded and cash > 0 and active_buy_tl is not None:
                sl, ic, _ = active_buy_tl
                lv = sl * i + ic
                ma_ok = np.isnan(ma45[i]) or (prices[i] <= ma45[i] * (1 + MA_BUY_CAP))
                if lv > 0 and prices[i] > lv * buy_threshold and (i - last_buy_idx) >= MIN_GAP and ma_ok:
                    shares = math.floor(cash * BUY_RATIO / prices[i])
                    if shares > 0:
                        cost         = shares * prices[i]
                        cash        -= cost
                        shares_held += shares
                        buy_signals.append((i, prices[i], shares))
                        open_positions.append((i, dates[i], prices[i], shares))
                        last_buy_idx  = i
                        active_buy_tl = None
                        mode          = "sell"
                        traded        = True

        # ── 賣出執行（traded=True 且本天未成交買入才觸發） ──────────────────────
        # 上方兩個分支都可能設 traded=True 來標記「賣出條件成立」；
        # 若本天已買，buy_signals[-1][0] == i，不再賣出。
        _sell_triggered = (
            traded
            and shares_held > 0
            and not (buy_signals and buy_signals[-1][0] == i)
        )

        if _sell_triggered:
            sell_sh = max(1, math.floor(shares_held * SELL_RATIO))
            if sell_sh > shares_held:
                sell_sh = shares_held

            revenue      = sell_sh * prices[i]
            cash        += revenue
            shares_held -= sell_sh
            sell_signals.append((i, prices[i], sell_sh))

            # FIFO 配對：暫存 batch，等 new_open 確定後再算 unrealized_pnl
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
                2
            )
            for bt in batch_trades:
                bt["unrealized_pnl"] = unreal
                trades.append(bt)

            last_sell_idx  = i
            active_sell_tl = None
            mode           = "buy"   # 賣完 → 切換優先找買點

        # ── 步驟三：增量更新極值集合，再搜尋趨勢線，存入 pending ──────────────
        # 每天只判斷 check_idx = i - LOCAL_WIN 這一個點是否為極值：
        #   窗口右邊界剛好是第 i 天（prices[check_idx + LOCAL_WIN] = prices[i]），
        #   這是目前已知的最新資料，完全不偷看未來。
        # 確認後才加入 highs / lows，再交給 find_best_trendline 使用，
        #   此時 anchor_set 裡所有點都是已被時間驗證的真實極值。
        check_idx = i - LOCAL_WIN

        if check_idx >= 0:
            lo     = check_idx - LOCAL_WIN
            hi_win = check_idx + LOCAL_WIN   # == i，目前最新天，安全
            if lo >= 0:
                window = prices[lo : hi_win + 1]
                if prices[check_idx] == window.max():
                    highs.add(check_idx)
                if prices[check_idx] == window.min():
                    lows.add(check_idx)

        if check_idx >= 0 and check_idx in highs:
            r = find_best_trendline(i, highs, prices, "down")
            if r:
                sl, ic, tc = r
                pending_buy_tl = (sl, ic, check_idx)
                tl_buy_drawn.append((check_idx, min(n - 1, check_idx + 120), sl, ic, tc))

        if check_idx >= 0 and check_idx in lows:
            r = find_best_trendline(i, lows, prices, "up")
            if r:
                sl, ic, tc = r
                pending_sell_tl = (sl, ic, check_idx)
                tl_sell_drawn.append((check_idx, min(n - 1, check_idx + 120), sl, ic, tc))

    # ── 期末未平倉：以最後收盤價假設清算 ─────────────────────────────────────
    last_price = prices[-1]
    for b_idx, b_date, b_price, b_sh in open_positions:
        p_cost = b_price * b_sh
        p_rev  = last_price * b_sh
        p_pnl  = p_rev - p_cost
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
            "shares_after":   b_sh,
            "unrealized_pnl": round(p_pnl, 2),
        })
        trade_counter += 1

    return {
        "trades":        trades,
        "buy_signals":   buy_signals,
        "sell_signals":  sell_signals,
        "tl_buy_drawn":  tl_buy_drawn,
        "tl_sell_drawn": tl_sell_drawn,
        "ma45":          ma45,
    }
