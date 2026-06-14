"""
autotest.py — 自動化參數掃描回測
=================================
對所有 (LOCAL_WIN × GAP × HOLD) 組合批次跑回測，
每個組合的輸出放在：
  Desktop/datas/(LOCAL_WIN,GAP,HOLD)/
    {stock}_交易明細.xlsx
    {stock}_走勢圖.png

執行方式：
  cd Desktop/pro
  python autotest.py

想調整掃描範圍，修改下方「★ 掃描參數設定 ★」區塊即可。
"""

import os
import sys
import time
import itertools
import importlib
import types

# ══════════════════════════════════════════════════════════════════════════════
#  ★  掃描參數設定  ★
# ══════════════════════════════════════════════════════════════════════════════

LOCAL_WIN_LIST  = [3, 4]          # LOCAL_WIN 掃描範圍
GAP_LIST        = [5, 15, 25, 35]   # MIN_GAP 掃描範圍（交易日）
HOLD_LIST       = [3, 7, 14, 20]    # MIN_HOLD_DAYS 掃描範圍（天）

# 輸出根目錄（每個參數組合會在這裡建一個子資料夾）
DATAS_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "datas")

# ══════════════════════════════════════════════════════════════════════════════
#  動態覆蓋 config 模組的工具
# ══════════════════════════════════════════════════════════════════════════════

# 確保 pro 資料夾在 import 路徑裡
PRO_DIR = os.path.dirname(os.path.abspath(__file__))
if PRO_DIR not in sys.path:
    sys.path.insert(0, PRO_DIR)


def _patch_config(local_win: int, gap: int, hold: int, output_dir: str) -> None:
    """
    直接修改已載入的 config 模組物件，讓所有 import config 的子模組
    在同一 Python 進程內都讀到新值，不需要重啟。
    """
    import config
    config.LOCAL_WIN     = local_win
    config.MIN_GAP       = gap
    config.MIN_HOLD_DAYS = hold
    config.OUTPUT_DIR    = output_dir


def _reload_modules() -> None:
    """
    strategy / performance / report / chart / data_loader 都在頂層 import config，
    reload 讓它們重新執行模組級的 import，確保拿到最新 config 值。
    """
    for mod_name in ["data_loader", "performance", "strategy", "report", "chart"]:
        if mod_name in sys.modules:
            importlib.reload(sys.modules[mod_name])


# ══════════════════════════════════════════════════════════════════════════════
#  單次回測（對所有股票跑一組參數）
# ══════════════════════════════════════════════════════════════════════════════

def run_one_combo(local_win: int, gap: int, hold: int) -> None:
    combo_name = f"({local_win},{gap},{hold})"
    output_dir = os.path.join(DATAS_DIR, combo_name)
    os.makedirs(output_dir, exist_ok=True)

    # 1. 覆蓋參數
    _patch_config(local_win, gap, hold, output_dir)
    _reload_modules()

    # 2. 重新載入各模組（確保拿到剛覆蓋的值）
    from config import (
        TICKERS, DATA_START_YEAR, DATA_END_YEAR,
        INITIAL_CASH, BUY_RATIO, SELL_RATIO,
        MA_PERIOD, TOLERANCE, MIN_TL_SPAN, DESKTOP,
        LOCAL_WIN as LW, MIN_GAP as MG, MIN_HOLD_DAYS as MH,
    )
    from data_loader import load_price_series
    from strategy    import run_backtest
    from performance import build_daily_df, calc_performance
    from report      import save_excel
    from chart       import save_chart

    if not TICKERS:
        print(f"  ⚠️  DESKTOP 資料夾沒有 CSV：{DESKTOP}")
        return

    for file_stem, display_name in TICKERS:
        series = load_price_series(file_stem)
        if series is None:
            continue
        series = series[
            (series.index.year >= DATA_START_YEAR) &
            (series.index.year <  DATA_END_YEAR)
        ]
        if len(series) < 50:
            print(f"    ⚠️  {display_name} 資料不足，略過")
            continue

        prices = series.values
        dates  = series.index

        result       = run_backtest(prices, dates)
        trades       = result["trades"]
        buy_signals  = result["buy_signals"]
        sell_signals = result["sell_signals"]
        ma45         = result["ma45"]

        daily_df = build_daily_df(prices, dates, ma45, trades)
        perf     = calc_performance(trades, daily_df, dates)

        cagr_str = (f"{perf['cagr'] * 100:.2f}%"
                    if perf["cagr"] is not None else "N/A")
        print(f"    {display_name:20s}  CAGR={cagr_str:>8}  "
              f"IRR={perf['irr_val']}%  "
              f"買{len(buy_signals)}次/賣{len(sell_signals)}次")

        save_excel(
            output_path  = os.path.join(output_dir, f"{file_stem}_交易明細.xlsx"),
            display_name = display_name,
            daily_df     = daily_df,
            trades       = trades,
            perf         = perf,
            prices       = prices,
            dates        = dates,
        )
        save_chart(
            chart_path    = os.path.join(output_dir, f"{file_stem}_走勢圖.png"),
            display_name  = display_name,
            prices        = prices,
            dates         = dates,
            ma45          = ma45,
            trades        = trades,
            buy_signals   = buy_signals,
            sell_signals  = sell_signals,
            tl_buy_drawn  = result["tl_buy_drawn"],
            tl_sell_drawn = result["tl_sell_drawn"],
            irr_val       = perf["irr_val"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    combos     = list(itertools.product(LOCAL_WIN_LIST, GAP_LIST, HOLD_LIST))
    total      = len(combos)
    start_time = time.time()

    print("=" * 70)
    print("  autotest — 批次參數掃描")
    print(f"  LOCAL_WIN : {LOCAL_WIN_LIST}")
    print(f"  GAP       : {GAP_LIST}")
    print(f"  HOLD      : {HOLD_LIST}")
    print(f"  總組合數  : {total}")
    print(f"  輸出根目錄: {DATAS_DIR}")
    print("=" * 70)

    for idx, (lw, gap, hold) in enumerate(combos, 1):
        combo_name = f"({lw},{gap},{hold})"
        elapsed    = time.time() - start_time
        eta_str    = ""
        if idx > 1:
            avg = elapsed / (idx - 1)
            remaining = avg * (total - idx + 1)
            eta_str = f"  ETA ~{remaining / 60:.1f} 分鐘"

        print(f"\n[{idx:>3}/{total}]  {combo_name}{eta_str}")
        print(f"  LOCAL_WIN={lw}  GAP={gap}  HOLD={hold}  → {DATAS_DIR}/{combo_name}/")

        try:
            run_one_combo(lw, gap, hold)
        except Exception as e:
            print(f"  ❌  {combo_name} 發生錯誤：{e}")
            import traceback
            traceback.print_exc()

    total_time = time.time() - start_time
    print(f"\n{'=' * 70}")
    print(f"🎉  全部完成！共 {total} 組  ·  耗時 {total_time / 60:.1f} 分鐘")
    print(f"  📁 輸出目錄：{DATAS_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
