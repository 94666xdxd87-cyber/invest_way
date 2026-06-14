"""
config.py — 傳統 MACD 策略所有可調參數集中於此，其他模組一律從這裡 import。

傳統 MACD 策略規則：
  買入：MACD 線金叉 Signal 線 → 全倉買入
  賣出：MACD 線死叉 Signal 線 → 全倉賣出
  無任何額外濾網（無均線濾網、無冷卻期、無持有天數限制）
"""

import os

# ════════════════════════════════════════════════════════════════════════════
#  ★  在這裡修改所有參數  ★
# ════════════════════════════════════════════════════════════════════════════

# ── MACD 指標參數（傳統預設值） ───────────────────────────────────────────────
MACD_FAST    = 12    # 短期 EMA 週期
MACD_SLOW    = 26    # 長期 EMA 週期
MACD_SIGNAL  = 9     # Signal 線 EMA 週期

# ── 資金參數 ─────────────────────────────────────────────────────────────────
INITIAL_CASH  = 320_000   # 初始資金
BUY_RATIO     = 0.8      # 傳統 MACD：全倉買入（動用所有現金）
SELL_RATIO    = 0.8       # 傳統 MACD：全倉賣出（賣出所有持股）

# ── 資料時間範圍 ──────────────────────────────────────────────────────────────
DATA_START_YEAR = 2025
DATA_END_YEAR   = 2027   # 取 year < DATA_END_YEAR 的資料

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
DESKTOP    = os.path.join(os.path.expanduser("~"), "Desktop", "invest_data")
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "macd_output")

# ── 股票清單：自動掃描 DESKTOP 資料夾內所有 CSV ────────────────────────────────
def _scan_tickers(folder: str) -> list[tuple[str, str]]:
    if not os.path.isdir(folder):
        return []
    return [
        (os.path.splitext(f)[0], os.path.splitext(f)[0])
        for f in sorted(os.listdir(folder))
        if f.lower().endswith(".csv")
    ]

TICKERS = _scan_tickers(DESKTOP)
