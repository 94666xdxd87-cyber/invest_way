"""
dca_config.py — DCA 策略專屬參數。
資料路徑、股票清單、輸出目錄與 config.py 共用；
僅定義 DCA 策略本身所需的額外設定。
"""

# ── DCA 策略參數 ──────────────────────────────────────────────────────────────
DCA_MONTHLY_AMOUNT = 10_000      # 每月固定投入金額（元）
DCA_BUY_DAY        = 1           # 每月幾號買入（1 = 每月第一個交易日）

# ── 無風險利率（同 performance.py，供 Sortino 計算用） ────────────────────────
RISK_FREE_RATE_ANNUAL = 0.017    # 台灣定存年利率 1.7%

# ── 輸出目錄（與主策略共用 OUTPUT_DIR，檔名加 _DCA 區別） ─────────────────────
# 直接 import config.OUTPUT_DIR 即可，此處不重複定義。
