"""
data_loader.py — 資料讀取與 MA / MACD 計算。
"""

import os
import numpy as np
import pandas as pd
from config import DESKTOP, MACD_FAST, MACD_SLOW, MACD_SIGNAL

# MA 週期：僅供圖表顯示參考用，不參與傳統 MACD 交易判斷
_MA_PERIOD = 45


def load_price_series(file_stem: str) -> pd.Series | None:
    """
    從 DESKTOP 資料夾讀取 <file_stem>.csv，回傳收盤價 Series（index = datetime）。
    欄位名稱不分大小寫，支援 'close' 與 'adj_close'。
    """
    path = os.path.join(DESKTOP, f"{file_stem}.csv")
    if not os.path.exists(path):
        print(f"  ⚠️  找不到檔案：{path}")
        return None
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df.columns = [c.strip() for c in df.columns]
    col_map   = {c.lower(): c for c in df.columns}
    close_col = col_map.get("close", col_map.get("adj_close"))
    if close_col is None:
        print(f"  ⚠️  [{file_stem}] 找不到 Close 欄位")
        return None
    return df[close_col].dropna().sort_index()


def compute_ma(prices: np.ndarray) -> np.ndarray:
    """回傳與 prices 等長的 MA45 陣列（前 _MA_PERIOD-1 天為 NaN），僅供圖表顯示。"""
    return pd.Series(prices).rolling(_MA_PERIOD).mean().values


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    """
    指數移動平均（alpha = 2 / (period + 1)）。
    前 period-1 個值為 NaN，第 period 個值用簡單平均初始化。
    """
    result = np.full(len(series), np.nan)
    if len(series) < period:
        return result
    result[period - 1] = np.mean(series[:period])
    alpha = 2.0 / (period + 1)
    for i in range(period, len(series)):
        result[i] = series[i] * alpha + result[i - 1] * (1 - alpha)
    return result


def compute_macd(prices: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    計算 MACD 三條線，長度與 prices 相同，未計算部分為 NaN。

    回傳 (macd_line, signal_line, histogram)。
    """
    ema_fast  = _ema(prices, MACD_FAST)
    ema_slow  = _ema(prices, MACD_SLOW)
    macd_line = ema_fast - ema_slow   # 前 MACD_SLOW-1 天為 NaN

    # Signal 線：對 macd_line 的有效部分再做 EMA
    valid_mask  = ~np.isnan(macd_line)
    valid_start = np.where(valid_mask)[0][0] if valid_mask.any() else len(prices)

    signal_full = np.full(len(prices), np.nan)
    if valid_start < len(prices):
        macd_valid = macd_line[valid_start:]
        sig_vals   = _ema(macd_valid, MACD_SIGNAL)
        signal_full[valid_start:] = sig_vals

    histogram = macd_line - signal_full
    return macd_line, signal_full, histogram
