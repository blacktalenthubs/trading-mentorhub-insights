"""Optional ``--chart`` output: one matplotlib PNG per hit.

Candles, the 20/50/200 SMAs, the detected pattern boundaries (from
``PatternHit.lines``), the buy point, and a volume subplot. matplotlib is
imported lazily so the scanner runs without it unless charts are requested.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from patterns.common import PatternHit

_LINE_COLORS = {
    "rim": "#6b7280", "cup low": "#6b7280", "handle high / buy": "#16a34a", "handle low / stop": "#dc2626",
    "base high / buy": "#16a34a", "base low / stop": "#dc2626",
    "ceiling / buy": "#16a34a", "rising lows": "#2563eb",
    "pole": "#2563eb", "flag high / buy": "#16a34a", "flag low / stop": "#dc2626",
}


def render_chart(df: pd.DataFrame, hit: PatternHit, out_dir: str | Path, context_bars: int = 40) -> Path:
    """Render ``hit`` on ``df`` (the scanned frame with derived columns) to a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{hit.ticker}_{hit.pattern}_{hit.stage}.png"

    start = max(0, hit.start_idx - context_bars)
    end = len(df)
    view = df.iloc[start:end]
    x = range(start, end)
    up = view["Close"] >= view["Open"]
    colors = ["#16a34a" if u else "#dc2626" for u in up]

    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]},
    )
    ax.vlines(x, view["Low"], view["High"], color=colors, linewidth=0.8)
    ax.bar(x, (view["Close"] - view["Open"]).abs(), bottom=view[["Open", "Close"]].min(axis=1),
           color=colors, width=0.6, linewidth=0)
    for col, c in (("sma20", "#f59e0b"), ("sma50", "#3b82f6"), ("sma200", "#8b5cf6")):
        if col in view.columns:
            ax.plot(x, view[col], color=c, linewidth=1.0, label=col.upper())
    for label, x0, y0, x1, y1 in hit.lines:
        ax.plot([x0, x1], [y0, y1], color=_LINE_COLORS.get(label, "#111827"), linewidth=1.4,
                linestyle="--" if "stop" in label else "-", label=label)
    ax.axhline(hit.buy_point, color="#16a34a", linewidth=0.8, linestyle=":")
    ax.set_title(f"{hit.ticker} — {hit.pattern} ({hit.stage}) score {hit.score:.0f} · buy {hit.buy_point:.2f} · stop {hit.suggested_stop:.2f}")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.grid(alpha=0.2)

    axv.bar(x, view["Volume"], color=colors, width=0.6, linewidth=0)
    if "avg_vol_50" in view.columns:
        axv.plot(x, view["avg_vol_50"], color="#6b7280", linewidth=1.0)
    axv.set_ylabel("volume")
    axv.grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out
