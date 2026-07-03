/** Gap & Go Queue — the top-3 quality-ranked premarket gappers, on the Today tab.
 *
 *  Reads the live gap board (usePremarketGaps), which now carries quality_score +
 *  queue_rank (backend step 1). Shows only the queued names (rank 1-3), each as a
 *  compact card: rank · symbol · gap% · quality · ▲PDH · catalyst. Click → chart.
 *  Renders NOTHING when there's no queue, so it stays out of the way mid-day.
 */

import { usePremarketGaps } from "../api/hooks";

export default function GapGoQueue({ onChart }: { onChart: (s: string) => void }) {
  const { data } = usePremarketGaps();
  const queue = (data?.entries ?? [])
    .filter((e) => e.queue_rank != null)
    .sort((a, b) => (a.queue_rank ?? 9) - (b.queue_rank ?? 9))
    .slice(0, 3);

  if (queue.length === 0) return null;

  return (
    <section className="mb-6">
      <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-warning-text">
        🚀 Gap &amp; Go Queue
        <span className="font-normal normal-case text-text-faint">· top gappers by quality</span>
      </h3>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
        {queue.map((e) => {
          const overPdh = e.pm_last != null && e.pdh != null && e.pm_last > e.pdh;
          const gap = e.gap_pct ?? 0;
          return (
            <button
              key={e.symbol}
              onClick={() => onChart(e.symbol)}
              className="rounded-xl border border-warning/30 bg-warning/5 p-3 text-left transition-colors hover:border-warning/60"
            >
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-warning/20 text-[11px] font-bold text-warning-text">
                  {e.queue_rank}
                </span>
                <span className="font-mono text-[15px] font-bold text-text-primary">{e.symbol}</span>
                <span className={`ml-auto font-mono text-[12px] font-bold ${gap >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                  {gap >= 0 ? "+" : ""}{gap.toFixed(1)}%
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                <span className="font-mono font-bold text-warning-text">Q{e.quality_score ?? "—"}</span>
                {overPdh && <span className="font-semibold text-bullish-text">▲ over PDH</span>}
              </div>
              {e.catalyst && (
                <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-text-muted">{e.catalyst}</p>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
