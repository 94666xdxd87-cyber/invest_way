"""
config.py — 所有可調參數集中於此，其他模組一律從這裡 import。
"""

import os

# ════════════════════════════════════════════════════════════════════════════
#  ★  在這裡修改所有參數  ★
# ════════════════════════════════════════════════════════════════════════════

# ── 策略參數 ─────────────────────────────────────────────────────────────────
MA_PERIOD     = 45       # MA 均線週期（同時用於進出場判斷與圖表顯示）
LOCAL_WIN     = 3       # 局部極值點左右窗口大小 (1~7)
LOOKBACK_DAYS = 252      # 往回尋找趨勢線錨點的最大天數
MIN_TOUCHES   = 3        # 趨勢線最少觸碰極值點數
TOLERANCE     = 0.02     # 趨勢線容差（0.05 = 5%）
MIN_GAP       = 14       # 兩次買入或賣出之間最短間隔（交易日）
MIN_HOLD_DAYS = 7       # 買入後最少持有天數
MIN_TL_SPAN   = 30       # 趨勢線頭尾最少跨越天數
MA_BUY_CAP        = 0.2   # 買入前濾網：收盤高於 MA45 超過此比例則不買入（0.20 = 20%）
MA_EARLY_SELL_CAP = 0.25  # 提前賣出門檻：mode=sell 且無支撐線時，收盤高於 MA45 此比例則提前賣出
                           # 例如 0.25 → 收盤 > MA45×1.25 時視為過熱，觸發賣出
                           # 有效區間 100%~(100%+MA_EARLY_SELL_CAP)，低於 MA45 同樣賣出
                           # 設為 None 可停用此功能（退回原始邏輯：只有跌破 MA45 才賣）

# ── 趨勢線突破緩衝 ────────────────────────────────────────────────────────────
BUY_BUFFER  = 0.02  # 買入：收盤須高於下降壓力線 × (1 + BUY_BUFFER) 才觸發
                      # 0.001 = 0.1%；調大可減少假突破，調小可提早進場
SELL_BUFFER = 0.02  # 賣出：收盤須低於上升支撐線 × (1 - SELL_BUFFER) 才觸發
                      # 0.001 = 0.1%；調大可容忍更深的跌破，調小可更快停損

# ── 趨勢線排序規則優先次序 ───────────────────────────────────────────────────
# 三個排序維度：
#   "touches" → 觸碰點數量（越多越好）
#   "slope"   → 斜率絕對值（越小越好）
#   "span"    → 橫跨時間幅度（越長越好）
# 用串列指定優先次序，索引 0 = 最優先，索引 2 = 最次要
# 範例：['touches', 'slope', 'span']  表示先比觸碰數，再比斜率，再比跨幅
TL_SORT_PRIORITY = ['touches', 'slope', 'span']

# ── 資金參數 ─────────────────────────────────────────────────────────────────
INITIAL_CASH = 320_000   # 初始資金
BUY_RATIO    = 0.8     # 每次買入動用的現金比例（0.5 = 50%）
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
