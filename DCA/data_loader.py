"""
data_loader.py — 資料讀取與 MA 計算。
"""

import os
import numpy as np
import pandas as pd
from config import DESKTOP, MA_PERIOD


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
    """回傳與 prices 等長的 MA 陣列（前 MA_PERIOD-1 天為 NaN）。"""
    return pd.Series(prices).rolling(MA_PERIOD).mean().values
