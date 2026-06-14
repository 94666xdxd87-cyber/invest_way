# 趨勢線策略回測系統

以下降壓力線突破作為買入訊號、上升支撐線跌破作為賣出訊號的量化回測框架。所有可調參數集中於 `config.py`，其餘模組各司其職，互不耦合。

---

## 快速開始

```bash
cd Desktop/pro
python run.py
```

輸出檔案會存放在 `config.py` 中 `OUTPUT_DIR` 所指定的資料夾，每支股票產生兩個檔案：

- `{stock}_交易明細.xlsx` — 每日帳戶明細、完整交易記錄、績效摘要
- `{stock}_走勢圖.png` — 含趨勢線、買賣訊號、成交連線的走勢圖

---

## 檔案結構

```
pro/
├── config.py        # 所有參數（唯一需要日常修改的檔案）
├── run.py           # 主程式進入點，串接所有模組
├── data_loader.py   # CSV 讀取與 MA 計算
├── strategy.py      # 趨勢線搜尋 + 回測引擎（核心邏輯）
├── performance.py   # IRR、CAGR、MDD、Sortino 等績效計算
├── report.py        # Excel 三分頁輸出
└── chart.py         # 走勢圖 PNG 輸出
```

---

## 模組說明

### `config.py` — 參數中心

所有參數集中於此，其他模組一律從這裡 import，不在各處硬編碼。

#### 策略參數

| 參數 | 預設值 | 說明 |
|---|---|---|
| `MA_PERIOD` | 45 | MA 均線週期，用於圖表顯示與 `MA_BUY_CAP` 濾網 |
| `LOCAL_WIN` | 2 | 局部極值點左右窗口大小（值越大，極值點越稀疏） |
| `LOOKBACK_DAYS` | 252 | 往回搜尋趨勢線錨點的最大天數（約 1 年） |
| `MIN_TOUCHES` | 4 | 趨勢線最少需碰觸的極值點數，越高訊號越可靠但越少 |
| `TOLERANCE` | 0.05 | 趨勢線容差 5%，判斷價格是否貼近趨勢線 |
| `MIN_GAP` | 14 | 兩次買入或兩次賣出之間的最短間隔（交易日） |
| `MIN_HOLD_DAYS` | 7 | 買入後最少持有天數，未達標前不觸發賣出 |
| `MIN_TL_SPAN` | 45 | 趨勢線兩端錨點的最少跨越天數 |
| `MA_BUY_CAP` | 0.20 | 買入濾網：收盤高於 MA45 超過此比例則不買入（0.20 = 20%） |

#### 趨勢線排序優先次序

```python
TL_SORT_PRIORITY = ['touches', 'slope', 'span']
```

當有多條有效趨勢線時，依此優先順序選出最佳線：

- `touches`：觸碰點數越多越好
- `slope`：斜率絕對值越小越好（越平緩）
- `span`：橫跨時間越長越好

#### 資金參數

| 參數 | 預設值 | 說明 |
|---|---|---|
| `INITIAL_CASH` | 320,000 | 回測起始資金 |
| `BUY_RATIO` | 0.5 | 每次買入動用現金的比例（50%） |
| `SELL_RATIO` | 0.8 | 每次賣出持股的比例（80%，非全倉） |

#### 路徑與資料設定

| 參數 | 說明 |
|---|---|
| `DATA_START_YEAR` | 資料起始年份 |
| `DATA_END_YEAR` | 資料結束年份（取 `year < DATA_END_YEAR` 的資料） |
| `DESKTOP` | CSV 資料來源資料夾路徑（預設為桌面 `invest_data/`） |
| `OUTPUT_DIR` | 輸出檔案目標資料夾 |
| `TICKERS` | 自動掃描 `DESKTOP` 資料夾內所有 `.csv`，無需手動維護 |

---

### `data_loader.py` — 資料讀取

負責從 CSV 讀取收盤價序列，以及計算 MA 陣列。

#### `load_price_series(file_stem)` → `pd.Series | None`

從 `DESKTOP/{file_stem}.csv` 讀取資料，回傳以日期為 index 的收盤價 Series。
欄位名稱不分大小寫，支援 `close` 與 `adj_close`。
找不到檔案或欄位時印出警告並回傳 `None`。

**使用的參數：** `DESKTOP`

#### `compute_ma(prices)` → `np.ndarray`

對價格陣列計算滾動均線，回傳與 `prices` 等長的陣列，前 `MA_PERIOD - 1` 天為 `NaN`。

**使用的參數：** `MA_PERIOD`

---

### `strategy.py` — 回測引擎（核心）

趨勢線搜尋與完整回測邏輯，是系統最核心的模組。

#### 買入邏輯（下降壓力線突破）

1. 第 `i` 天收盤後確認局部高點，畫出下降壓力線（存入 `pending_buy_tl`）
2. 第 `i+1` 天起才可用（升級為 `active_buy_tl`），避免未來偏差
3. 收盤價突破趨勢線值 × 1.001（0.1% 緩衝），且：
   - 距上次買入 ≥ `MIN_GAP` 天
   - 收盤價 ≤ MA45 × (1 + `MA_BUY_CAP`)（不追高濾網）
4. 動用 `BUY_RATIO` 比例的現金買入，股數向下取整

#### 賣出邏輯（上升支撐線跌破）

1. 第 `i` 天收盤後確認局部低點，畫出上升支撐線（存入 `pending_sell_tl`）
2. 第 `i+1` 天起才可用（升級為 `active_sell_tl`）
3. 收盤價跌破趨勢線值 × 0.999（0.1% 緩衝），且：
   - 距上次賣出 ≥ `MIN_GAP` 天
   - 距上次買入 > `MIN_HOLD_DAYS` 天
4. 賣出 `SELL_RATIO` 比例的持股，依 FIFO 順序配對

#### 交替狀態機（雙向 fallback）

系統維護一個 `mode` 狀態（`"buy"` 或 `"sell"`），每天最多執行一筆交易：

```
mode="buy"  → 先找買點；買到 → 切 sell；找不到 → fallback 找賣點
mode="sell" → 先找賣點；賣到 → 切 buy；找不到 → fallback 找買點
```

#### `find_local_extrema(prices)` → `(highs, lows)`

找出所有局部高點與低點的索引集合，以左右各 `LOCAL_WIN` 天為窗口判斷。

**使用的參數：** `LOCAL_WIN`

#### `find_best_trendline(current_idx, anchor_set, prices, direction)` → `(slope, intercept, touches) | None`

在 `current_idx` 往前 `LOOKBACK_DAYS` 天的錨點中，窮舉所有兩點組合，找出最優趨勢線。

- `direction="down"`：下降壓力線（斜率 < 0）
- `direction="up"`：上升支撐線（斜率 > 0）

依 `TL_SORT_PRIORITY` 排序選出最佳線。

**使用的參數：** `LOOKBACK_DAYS`, `MIN_TOUCHES`, `TOLERANCE`, `MIN_TL_SPAN`, `TL_SORT_PRIORITY`

#### `run_backtest(prices, dates)` → `dict`

執行完整回測，回傳以下結果：

| 鍵值 | 內容 |
|---|---|
| `trades` | 所有配對交易（含期末未平倉假設清算） |
| `buy_signals` | 買入訊號列表 `[(idx, price, shares), ...]` |
| `sell_signals` | 賣出訊號列表 `[(idx, price, shares), ...]` |
| `tl_buy_drawn` | 已畫出的下降壓力線 `[(xs, xe, slope, intercept, touches), ...]` |
| `tl_sell_drawn` | 已畫出的上升支撐線（同上格式） |
| `ma45` | MA 值陣列 |

`trades` 中每筆記錄包含：`trade_no`, `buy_date`, `buy_price`, `sell_date`, `sell_price`, `shares`, `cost`, `revenue`, `pnl`, `ret_pct`, `hold_days`, `closed`, `cash_after`, `shares_after`, `unrealized_pnl`

**使用的參數：** 所有策略參數與資金參數

---

### `performance.py` — 績效計算

計算所有量化績效指標，不含任何 UI 或輸出邏輯。

#### `calc_irr(trades, closed_only)` → `float | None`

以現金流折現法（`scipy.optimize.brentq`）求解年化 IRR，回傳百分比數值。

- `closed_only=False`：含期末未平倉假設清算
- `closed_only=True`：僅計算已實現平倉交易

**使用的參數：** `INITIAL_CASH`

#### `build_daily_df(prices, dates, ma45, trades)` → `pd.DataFrame`

逐日重建帳戶狀態，輸出欄位：

`Date`, `Close`, `MA45`, `State`（高於/低於 MA45）, `Signal`（當日買賣記錄）, `目前持有資金`, `目前持有股票`, `目前損益`, `資產總價值`

**使用的參數：** `INITIAL_CASH`

#### `calc_performance(trades, daily_df, dates)` → `dict`

彙整所有績效指標，回傳以下鍵值：

| 鍵值 | 說明 |
|---|---|
| `irr_val` | 年化 IRR（含未平倉假設清算） |
| `irr_closed_only` | 年化 IRR（純已實現） |
| `cagr` | 複合年化成長率 |
| `total_pnl` / `realized_pnl` | 總損益 / 已實現損益 |
| `win_trades` / `win_rate` | 獲利筆數 / 勝率 |
| `max_drawdown` | 最大回撤 MDD |
| `cumulative_return` | 累積報酬率 |
| `sortino_ratio` | Sortino Ratio（無風險利率 1.7%） |
| `final_total_asset` | 期末資產總價值 |

**Sortino Ratio 計算方式：** 以每日資產報酬率計算下行標準差，分母為總交易日數（非僅負報酬日），再年化（× √252）。

---

### `report.py` — Excel 輸出

輸出含三張工作表的 `.xlsx` 報告。

#### `save_excel(output_path, display_name, daily_df, trades, perf, prices, dates)`

| 工作表 | 內容 |
|---|---|
| 每日明細 | 逐日帳戶狀態，買賣當日以金/紅色高亮，損益以顏色標示正負 |
| 交易記錄 | 每筆配對交易完整資訊，獲利列綠色、虧損列紅色，未平倉標注 ★ |
| 績效摘要 | 所有績效指標，含使用參數記錄，便於不同參數組合的比對存檔 |

**使用的參數：** `INITIAL_CASH`, `MA_PERIOD`, `LOCAL_WIN`, `TOLERANCE`, `MIN_GAP`, `MIN_HOLD_DAYS`, `MIN_TL_SPAN`

---

### `chart.py` — 走勢圖輸出

輸出深色背景的走勢圖 PNG。

#### `save_chart(chart_path, display_name, prices, dates, ma45, trades, buy_signals, sell_signals, tl_buy_drawn, tl_sell_drawn, irr_val)`

圖表包含：

- 收盤價曲線（藍）、MA 均線（橙虛線）
- 下降壓力線（綠，最多顯示最近 25 條）
- 上升支撐線（橙，最多顯示最近 25 條）
- 買入訊號（紅色上三角 ▲）、賣出訊號（青色下三角 ▽），含日期與股數標注
- 已平倉成交連線（獲利綠色虛線、虧損紅色虛線）

**使用的參數：** `MA_PERIOD`, `LOCAL_WIN`, `TOLERANCE`, `MIN_GAP`, `MIN_HOLD_DAYS`, `MIN_TL_SPAN`

---

### `run.py` — 主程式

只負責串接各模組，不含任何策略或計算邏輯。執行流程：

```
讀取 CSV → run_backtest → build_daily_df → calc_performance → save_excel → save_chart
```

每支股票依序執行，並在 console 印出進度摘要。

---

## 資料格式

CSV 檔案需放置於 `DESKTOP`（預設 `~/Desktop/invest_data/`），格式要求：

```
date,close
2005-01-03,100.5
2005-01-04,101.2
...
```

- index 欄位名稱必須為 `date`
- 收盤價欄位支援 `close` 或 `adj_close`（不分大小寫）
- 檔名即為股票代碼（例如 `2330.csv` → display name 為 `2330`）

---

## 模組依賴關係

```
config.py
    ↑
    ├── data_loader.py
    ├── strategy.py  ←── data_loader.py
    ├── performance.py
    ├── report.py
    ├── chart.py
    └── run.py（串接全部）
```

所有模組都只從 `config.py` 讀取參數，互相之間不會直接 import 對方（除了 `strategy.py` 使用 `data_loader.compute_ma`）。
