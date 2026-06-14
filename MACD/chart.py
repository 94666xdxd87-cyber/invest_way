"""
chart.py — 傳統 MACD 策略走勢圖輸出（PNG）。

圖表包含：
  - 上方主圖：收盤價（藍）、MA 均線（橙虛線，僅供參考）、買賣訊號三角、成交連線
              金叉位置（綠色垂直虛線）、死叉位置（橙色垂直虛線）
  - 下方副圖：MACD 柱狀圖（Histogram）、MACD 線（青）、Signal 線（橙）
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D

from config import MACD_FAST, MACD_SLOW, MACD_SIGNAL
from data_loader import compute_macd, compute_ma


def save_chart(
    chart_path:    str,
    display_name:  str,
    prices:        np.ndarray,
    dates,
    ma45:          np.ndarray,
    trades:        list,
    buy_signals:   list,
    sell_signals:  list,
    tl_buy_drawn:  list,   # 金叉標記 [(idx, idx, 0.0, price, 0), ...]
    tl_sell_drawn: list,   # 死叉標記
    irr_val,
) -> None:
    """
    輸出傳統 MACD 策略走勢圖 PNG，含主圖（價格）與副圖（MACD 指標）。
    """
    n = len(prices)
    macd_line, signal_line, histogram = compute_macd(prices)

    # ── 畫布：主圖 70% / 副圖 30% ─────────────────────────────────────────────
    fig = plt.figure(figsize=(26, 13))
    fig.patch.set_facecolor("#0d1117")
    gs  = gridspec.GridSpec(2, 1, height_ratios=[7, 3], hspace=0.04)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    for ax in (ax1, ax2):
        ax.set_facecolor("#0d1117")
        ax.grid(color="#21262d", linestyle="--", linewidth=0.5, zorder=0)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")

    xs = range(n)

    # ══════════════════════════════════════════════════════════════════════════
    # 主圖：收盤價 / MA（參考用）/ 買賣訊號 / 成交連線 / 金死叉垂直線
    # ══════════════════════════════════════════════════════════════════════════

    # 收盤價
    ax1.plot(xs, prices, color="#58a6ff", linewidth=1.0, label="Close", zorder=2)

    # MA 均線（僅供視覺參考，不參與傳統 MACD 交易判斷）
    mx = [i for i in xs if not np.isnan(ma45[i])]
    if mx:
        ax1.plot(mx, [ma45[i] for i in mx],
                 color="#f0a500", linewidth=1.0, linestyle="--",
                 alpha=0.5, label="MA（參考）", zorder=2)

    # 金叉垂直線（綠）
    for xs_mark, *_ in tl_buy_drawn:
        ax1.axvline(xs_mark, color="#3fb950", linewidth=0.7, linestyle=":", alpha=0.5, zorder=3)

    # 死叉垂直線（橙）
    for xs_mark, *_ in tl_sell_drawn:
        ax1.axvline(xs_mark, color="#f7922a", linewidth=0.7, linestyle=":", alpha=0.5, zorder=3)

    # 買入訊號 ▲
    for idx, p, sh in buy_signals:
        ax1.scatter(idx, p, color="#ff4444", s=130, zorder=5, marker="^")
        ax1.annotate(
            f"Buy {sh}股\n{dates[idx].strftime('%y/%m/%d')}",
            xy=(idx, p), xytext=(idx + 4, p * 1.03),
            fontsize=6, color="#ff4444",
            arrowprops=dict(arrowstyle="->", color="#ff4444", lw=0.7),
        )

    # 賣出訊號 ▽
    for idx, p, sh in sell_signals:
        ax1.scatter(idx, p, color="#00e5ff", s=130, zorder=5, marker="v")
        ax1.annotate(
            f"Sell {sh}股\n{dates[idx].strftime('%y/%m/%d')}",
            xy=(idx, p), xytext=(idx + 4, p * 0.97),
            fontsize=6, color="#00e5ff",
            arrowprops=dict(arrowstyle="->", color="#00e5ff", lw=0.7),
        )

    # 成交連線（已平倉）
    for t in trades:
        if t["closed"]:
            c = "#2ea043" if t["pnl"] > 0 else "#f85149"
            ax1.plot(
                [t["buy_idx"], t["sell_idx"]],
                [t["buy_price"], t["sell_price"]],
                color=c, linewidth=0.8, linestyle=":", alpha=0.5, zorder=4,
            )

    # 標題
    ax1.set_title(
        f"{display_name} — 傳統 MACD({MACD_FAST},{MACD_SLOW},{MACD_SIGNAL}) 策略  "
        f"[買入 {len(buy_signals)} 次 | 賣出 {len(sell_signals)} 次 | IRR {irr_val}%]",
        color="#f0f6fc", fontsize=11, pad=14,
    )
    ax1.set_ylabel("Price", color="#8b949e", fontsize=9)
    ax1.yaxis.set_tick_params(labelcolor="#8b949e", labelsize=8)

    # 圖例
    legend_elements = [
        Line2D([0], [0], color="#58a6ff", lw=1.5, label="Close"),
        Line2D([0], [0], color="#f0a500", lw=1.0, linestyle="--", alpha=0.5, label="MA（參考）"),
        Line2D([0], [0], color="#3fb950", lw=1.0, linestyle=":", label="金叉"),
        Line2D([0], [0], color="#f7922a", lw=1.0, linestyle=":", label="死叉"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#ff4444",
               markersize=9, label=f"買入 ({len(buy_signals)}次)"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="#00e5ff",
               markersize=9, label=f"賣出 ({len(sell_signals)}次)"),
    ]
    ax1.legend(handles=legend_elements,
               facecolor="#161b22", edgecolor="#30363d",
               labelcolor="#f0f6fc", fontsize=9, loc="upper left")

    plt.setp(ax1.get_xticklabels(), visible=False)

    # ══════════════════════════════════════════════════════════════════════════
    # 副圖：MACD Histogram / MACD 線 / Signal 線
    # ══════════════════════════════════════════════════════════════════════════

    valid = [i for i in xs if not np.isnan(histogram[i])]

    # Histogram 柱狀圖：正值綠、負值紅
    hist_colors = ["#2ea043" if histogram[i] >= 0 else "#f85149" for i in valid]
    ax2.bar(valid, [histogram[i] for i in valid],
            color=hist_colors, alpha=0.6, width=1.0, zorder=2, label="Histogram")

    # MACD 線 & Signal 線
    macd_valid = [i for i in xs if not np.isnan(macd_line[i])]
    sig_valid  = [i for i in xs if not np.isnan(signal_line[i])]
    ax2.plot(macd_valid, [macd_line[i]   for i in macd_valid],
             color="#00e5ff", linewidth=1.0, label="MACD",   zorder=3)
    ax2.plot(sig_valid,  [signal_line[i] for i in sig_valid],
             color="#f0a500", linewidth=1.0, label="Signal", zorder=3)
    ax2.axhline(0, color="#8b949e", linewidth=0.6, linestyle="--", zorder=1)

    # 副圖也標注金叉死叉
    for xs_mark, *_ in tl_buy_drawn:
        ax2.axvline(xs_mark, color="#3fb950", linewidth=0.7, linestyle=":", alpha=0.5)
    for xs_mark, *_ in tl_sell_drawn:
        ax2.axvline(xs_mark, color="#f7922a", linewidth=0.7, linestyle=":", alpha=0.5)

    ax2.set_ylabel("MACD", color="#8b949e", fontsize=9)
    ax2.yaxis.set_tick_params(labelcolor="#8b949e", labelsize=7)
    ax2.legend(facecolor="#161b22", edgecolor="#30363d",
               labelcolor="#f0f6fc", fontsize=8, loc="upper left")

    # X 軸日期標籤（只在副圖顯示）
    step = max(1, n // 20)
    ax2.set_xticks(range(0, n, step))
    ax2.set_xticklabels(
        [dates[i].strftime("%Y-%m") for i in range(0, n, step)],
        rotation=45, fontsize=7, color="#8b949e",
    )
    ax2.set_xlabel("Date", color="#8b949e", fontsize=9)

    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  ✅ 走勢圖 → {chart_path}")
