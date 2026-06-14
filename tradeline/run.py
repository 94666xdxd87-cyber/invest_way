"""
run.py — 主程式進入點，只負責串接各模組，不含任何策略或計算邏輯。

執行方式：
  cd Desktop/pro
  python run.py

輸出：
  每支股票輸出兩個檔案到 OUTPUT_DIR（見 config.py）：
    {file_stem}_交易明細.xlsx   （每日明細 / 交易記錄 / 績效摘要）
    {file_stem}_走勢圖.png      （含趨勢線、買賣訊號）

所有可調參數請到 config.py 修改。
"""

import os

from config import (
    TICKERS,
    DATA_START_YEAR, DATA_END_YEAR,
    OUTPUT_DIR,
    INITIAL_CASH, BUY_RATIO, SELL_RATIO,
    MA_PERIOD, LOCAL_WIN, TOLERANCE,
    MIN_GAP, MIN_HOLD_DAYS, MIN_TL_SPAN,
    DESKTOP,
)
from data_loader    import load_price_series
from strategy       import run_backtest
from performance    import build_daily_df, calc_performance
from report         import save_excel
from chart          import save_chart


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  趨勢線策略回測")
    print(f"  期間  ：{DATA_START_YEAR} ~ {DATA_END_YEAR}")
    print(f"  參數  ：MA={MA_PERIOD}  WIN={LOCAL_WIN}  TOL={TOLERANCE}")
    print(f"          GAP={MIN_GAP}  HOLD={MIN_HOLD_DAYS}  SPAN={MIN_TL_SPAN}")
    print(f"  資金  ：初始={INITIAL_CASH:,}  買入={BUY_RATIO}  賣出={SELL_RATIO}")
    print(f"  讀取  ：{DESKTOP}")
    print(f"  股票數：{len(TICKERS)} 支（自動掃描）")
    print(f"  輸出  ：{OUTPUT_DIR}")
    print("=" * 70)

    for file_stem, display_name in TICKERS:
        print(f"\n▶  {display_name}")

        # 1. 讀取資料
        series = load_price_series(file_stem)
        if series is None:
            continue

        series = series[
            (series.index.year >= DATA_START_YEAR) &
            (series.index.year <  DATA_END_YEAR)
        ]
        if len(series) < 50:
            print(f"  ⚠️  資料筆數不足（{len(series)} 筆），略過。")
            continue

        prices = series.values
        dates  = series.index
        print(f"  資料：{dates[0].date()} → {dates[-1].date()}  ({len(prices)} 筆)")

        # 2. 回測
        result       = run_backtest(prices, dates)
        trades       = result["trades"]
        buy_signals  = result["buy_signals"]
        sell_signals = result["sell_signals"]
        ma45         = result["ma45"]

        # 3. 績效計算
        daily_df = build_daily_df(prices, dates, ma45, trades)
        perf     = calc_performance(trades, daily_df, dates)

        cagr_disp = f"{perf['cagr'] * 100:.2f}%" if perf["cagr"] is not None else "N/A"
        print(
            f"  買入 {len(buy_signals)} 次 | 賣出 {len(sell_signals)} 次 | "
            f"CAGR {cagr_disp} | "
            f"IRR(含未平倉) {perf['irr_val']}% | "
            f"IRR(純已實現) {perf['irr_closed_only']}% | "
            f"勝率 {perf['win_rate']:.1f}%"
        )

        # 4. 輸出 Excel
        save_excel(
            output_path  = os.path.join(OUTPUT_DIR, f"{file_stem}_交易明細.xlsx"),
            display_name = display_name,
            daily_df     = daily_df,
            trades       = trades,
            perf         = perf,
            prices       = prices,
            dates        = dates,
        )

        # 5. 輸出走勢圖
        save_chart(
            chart_path    = os.path.join(OUTPUT_DIR, f"{file_stem}_走勢圖.png"),
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

    print(f"\n{'=' * 70}")
    print("🎉  全部完成！")
    print(f"  📁 輸出目錄：{OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
