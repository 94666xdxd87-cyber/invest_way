"""
run_dca.py — DCA 策略主程式進入點。

執行方式：
  cd Desktop/pro
  python run_dca.py

輸出（寫入 OUTPUT_DIR）：
  {file_stem}_DCA明細.xlsx   （每日帳戶明細 / 買入記錄 / 績效摘要）

資料來源、股票清單、期間設定與 run.py 共用 config.py。
DCA 專屬參數（每月金額等）見 dca_config.py。
"""

import os

from config import (
    TICKERS, DATA_START_YEAR, DATA_END_YEAR,
    DESKTOP,
)

# DCA 輸出至獨立資料夾，不與趨勢線策略混用
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "test_3 output")
from dca_config     import DCA_MONTHLY_AMOUNT
from data_loader    import load_price_series
from dca_strategy   import run_dca
from dca_performance import build_dca_daily_df, calc_dca_performance
from dca_report     import save_dca_excel


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  DCA 定期定額回測")
    print(f"  每月投入：{DCA_MONTHLY_AMOUNT:,} 元")
    print(f"  期間    ：{DATA_START_YEAR} ~ {DATA_END_YEAR}")
    print(f"  讀取    ：{DESKTOP}")
    print(f"  股票數  ：{len(TICKERS)} 支（自動掃描）")
    print(f"  輸出    ：{OUTPUT_DIR}")
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
        if len(series) < 20:
            print(f"  ⚠️  資料筆數不足（{len(series)} 筆），略過。")
            continue

        prices = series.values
        dates  = series.index
        print(f"  資料：{dates[0].date()} → {dates[-1].date()}  ({len(prices)} 筆)")

        # 2. DCA 回測
        result        = run_dca(prices, dates)
        trades        = result["trades"]
        cash_residual = result["cash_residual"]

        if not trades:
            print("  ⚠️  無任何買入紀錄，略過。")
            continue

        # 3. 績效計算
        daily_df = build_dca_daily_df(prices, dates, trades, cash_residual)
        perf     = calc_dca_performance(trades, daily_df, dates, prices, cash_residual)

        cagr_disp = f"{perf['cagr'] * 100:.2f}%" if perf.get("cagr") is not None else "N/A"
        print(
            f"  買入 {perf['total_months']} 次 | "
            f"投入 {perf['total_invested']:,.0f} 元 | "
            f"期末市值 {perf['final_value']:,.0f} 元 | "
            f"損益 {perf['total_pnl']:+,.0f} 元 | "
            f"累積報酬 {perf['cumulative_ret']*100:.1f}% | "
            f"CAGR {cagr_disp} | "
            f"IRR {perf['irr_val']}%"
        )

        # 4. 輸出 Excel
        save_dca_excel(
            output_path  = os.path.join(OUTPUT_DIR, f"{file_stem}_DCA明細.xlsx"),
            display_name = display_name,
            daily_df     = daily_df,
            trades       = trades,
            perf         = perf,
        )

    print(f"\n{'=' * 70}")
    print("🎉  DCA 回測完成！")
    print(f"  📁 輸出目錄：{OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
