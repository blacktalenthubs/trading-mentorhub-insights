"""Optional --chart output: a PNG per hit — candles, the three SMAs, the buy point (TBA) and
stop drawn as lines, and a volume subplot. Headless (Agg). Best-effort; never blocks a scan."""
from __future__ import annotations

import os


def render_hit(df, row: dict, outdir: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bars = max(int(row.get("base_length_days", 60)) * 2, 120)
    seg = df.tail(bars).reset_index(drop=True)
    x = range(len(seg))

    fig, (ax, axv) = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    for i in x:
        o, h, l, c = seg["Open"][i], seg["High"][i], seg["Low"][i], seg["Close"][i]
        up = c >= o
        col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l, h], color=col, linewidth=0.7)
        ax.plot([i, i], [o, c], color=col, linewidth=3)
    for ma, col in (("sma20", "#2962ff"), ("sma50", "#f7931a"), ("sma200", "#787b86")):
        if ma in seg:
            ax.plot(x, seg[ma], color=col, linewidth=1, label=ma)
    ax.axhline(row["buy_point"], color="#16a34a", linestyle="--", linewidth=1.2, label=f"buy {row['buy_point']:.2f}")
    ax.axhline(row["suggested_stop"], color="#ef4444", linestyle=":", linewidth=1.2, label=f"stop {row['suggested_stop']:.2f}")
    ax.set_title(f"{row['ticker']} · {row['pattern']} · {row['stage']} · score {row['score']} — {row['reason']}", fontsize=9)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.15)

    vcol = ["#26a69a" if seg["Close"][i] >= seg["Open"][i] else "#ef5350" for i in x]
    axv.bar(x, seg["Volume"], color=vcol, width=0.8)
    if "avg_vol_50" in seg:
        axv.plot(x, seg["avg_vol_50"], color="#787b86", linewidth=1)
    axv.grid(alpha=0.15)
    fig.tight_layout()

    path = os.path.join(outdir, f"{row['ticker']}_{row['pattern']}_{row['stage']}.png")
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return path
