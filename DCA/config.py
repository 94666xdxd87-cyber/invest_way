"""
config.py — 所有可調參數集中於此，其他模組一律從這裡 import。
"""

import os

# ════════════════════════════════════════════════════════════════════════════
#  ★  在這裡修改所有參數  ★
# ════════════════════════════════════════════════════════════════════════════

# ── 策略參數 ─────────────────────────────────────────────────────────────────
MA_PERIOD     = 45       # MA 均線週期（同時用於進出場判斷與圖表顯示）
LOCAL_WIN     = 3        # 局部極值點左右窗口大小 (1~7)
LOOKBACK_DAYS = 252      # 往回尋找趨勢線錨點的最大天數
MIN_TOUCHES   = 4        # 趨勢線最少觸碰極值點數
TOLERANCE     = 0.05     # 趨勢線容差（0.05 = 5%）
MIN_GAP       = 14       # 兩次買入或賣出之間最短間隔（交易日）
MIN_HOLD_DAYS = 20       # 買入後最少持有天數
MIN_TL_SPAN   = 30       # 趨勢線頭尾最少跨越天數

# ── 資金參數 ─────────────────────────────────────────────────────────────────
INITIAL_CASH = 320_000   # 初始資金
BUY_RATIO    = 0.5       # 每次買入動用的現金比例（0.5 = 50%）
SELL_RATIO   = 0.8       # 每次賣出持股比例（1.0 = 全賣）

# ── 資料時間範圍 ──────────────────────────────────────────────────────────────
DATA_START_YEAR = 2025
DATA_END_YEAR   = 2027   # 取 year < DATA_END_YEAR 的資料

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
DESKTOP    = os.path.join(os.path.expanduser("~"), "Desktop", "invest_data")
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "test2_output")

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
