"""
chart.py — 走勢圖輸出（PNG）。
接受回測結果，繪製收盤價、MA 均線、趨勢線、買賣訊號與成交連線。
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from config import MA_PERIOD, LOCAL_WIN, TOLERANCE, MIN_GAP, MIN_HOLD_DAYS, MIN_TL_SPAN


def save_chart(
    chart_path:   str,
    display_name: str,
    prices:       np.ndarray,
    dates,
    ma45:         np.ndarray,
    trades:       list,
    buy_signals:  list,
    sell_signals: list,
    tl_buy_drawn: list,
    tl_sell_drawn: list,
    irr_val,
) -> None:
    """
    輸出走勢圖 PNG。

    參數說明：
      tl_buy_drawn  : list of (xs, xe, slope, intercept, touches)  — 下降壓力線
      tl_sell_drawn : list of (xs, xe, slope, intercept, touches)  — 上升支撐線
      buy_signals   : list of (idx, price, shares)
      sell_signals  : list of (idx, price, shares)
      irr_val       : float | None，顯示在標題
    """
    n = len(prices)
    fig, ax = plt.subplots(figsize=(26, 11))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    # ── 收盤價 & MA ───────────────────────────────────────────────────────────
    ax.plot(range(n), prices, color="#58a6ff", linewidth=1.0, label="Close", zorder=2)
    mx = [i for i in range(n) if not np.isnan(ma45[i])]
    ax.plot(mx, [ma45[i] for i in mx],
            color="#f0a500", linewidth=1.2, linestyle="--",
            label=f"MA{MA_PERIOD}", zorder=2)

    # ── 趨勢線（最多顯示最近 25 條，避免畫面過於雜亂） ────────────────────────
    shown_buy  = tl_buy_drawn[-25:]  if len(tl_buy_drawn)  > 25 else tl_buy_drawn
    shown_sell = tl_sell_drawn[-25:] if len(tl_sell_drawn) > 25 else tl_sell_drawn
    for xs, xe, sl, ic, _ in shown_buy:
        ax.plot([xs, xe], [sl * xs + ic, sl * xe + ic],
                color="#3fb950", linewidth=0.8, alpha=0.45, zorder=3)
    for xs, xe, sl, ic, _ in shown_sell:
        ax.plot([xs, xe], [sl * xs + ic, sl * xe + ic],
                color="#f7922a", linewidth=0.8, alpha=0.45, zorder=3)

    # ── 買入訊號 ──────────────────────────────────────────────────────────────
    for idx, p, sh in buy_signals:
        ax.scatter(idx, p, color="#ff4444", s=130, zorder=5, marker="^")
        ax.annotate(
            f"Buy {sh}股\n{dates[idx].strftime('%y/%m/%d')}",
            xy=(idx, p), xytext=(idx + 4, p * 1.03),
            fontsize=6, color="#ff4444",
            arrowprops=dict(arrowstyle="->", color="#ff4444", lw=0.7),
        )

    # ── 賣出訊號 ──────────────────────────────────────────────────────────────
    for idx, p, sh in sell_signals:
        ax.scatter(idx, p, color="#00e5ff", s=130, zorder=5, marker="v")
        ax.annotate(
            f"Sell {sh}股\n{dates[idx].strftime('%y/%m/%d')}",
            xy=(idx, p), xytext=(idx + 4, p * 0.97),
            fontsize=6, color="#00e5ff",
            arrowprops=dict(arrowstyle="->", color="#00e5ff", lw=0.7),
        )

    # ── 成交連線（已平倉：綠=獲利 / 紅=虧損） ─────────────────────────────────
    for t in trades:
        if t["closed"]:
            c = "#2ea043" if t["pnl"] > 0 else "#f85149"
            ax.plot(
                [t["buy_idx"], t["sell_idx"]],
                [t["buy_price"], t["sell_price"]],
                color=c, linewidth=0.8, linestyle=":", alpha=0.5, zorder=4,
            )

    # ── X 軸日期標籤 ──────────────────────────────────────────────────────────
    step = max(1, n // 20)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels(
        [dates[i].strftime("%Y-%m") for i in range(0, n, step)],
        rotation=45, fontsize=7, color="#8b949e",
    )
    ax.yaxis.set_tick_params(labelcolor="#8b949e", labelsize=8)
    ax.set_xlabel("Date",  color="#8b949e", fontsize=9)
    ax.set_ylabel("Price", color="#8b949e", fontsize=9)

    # ── 標題 ──────────────────────────────────────────────────────────────────
    ax.set_title(
        f"{display_name} — 趨勢線策略  "
        f"[買入 {len(buy_signals)} 次 | 賣出 {len(sell_signals)} 次 | IRR {irr_val}%]  "
        f"MA={MA_PERIOD}(參考) WIN={LOCAL_WIN} TOL={TOLERANCE} "
        f"GAP={MIN_GAP} HOLD={MIN_HOLD_DAYS} SPAN={MIN_TL_SPAN}",
        color="#f0f6fc", fontsize=11, pad=14,
    )

    # ── 格線 & 外框 ───────────────────────────────────────────────────────────
    ax.grid(color="#21262d", linestyle="--", linewidth=0.5, zorder=0)
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

    # ── 圖例 ──────────────────────────────────────────────────────────────────
    legend_elements = [
        Line2D([0], [0], color="#58a6ff", lw=1.5, label="Close"),
        Line2D([0], [0], color="#f0a500", lw=1.5, linestyle="--", label=f"MA{MA_PERIOD}"),
        Line2D([0], [0], color="#3fb950", lw=1.2, label="下降趨勢線"),
        Line2D([0], [0], color="#f7922a", lw=1.2, label="上升趨勢線"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#ff4444",
               markersize=9, label=f"買入 ({len(buy_signals)}次)"),
        Line2D([0], [0], marker="v", color="w", markerfacecolor="#00e5ff",
               markersize=9, label=f"賣出 ({len(sell_signals)}次)"),
    ]
    ax.legend(handles=legend_elements,
              facecolor="#161b22", edgecolor="#30363d",
              labelcolor="#f0f6fc", fontsize=9, loc="upper left")

    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  ✅ 走勢圖 → {chart_path}")
