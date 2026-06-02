/** Strategy Analysis — Performance > Strategy tab.
 *
 *  Which patterns actually work, judged by REAL forward returns (close-to-close)
 *  rather than the inaccurate intraday target system:
 *    - EOD %  — same-day close vs the alert price
 *    - EOW %  — end-of-week close vs the alert price ("did the gains hold?")
 *  Each pattern is classified Swing / Day / Avoid from the EOD-vs-EOW gap, and
 *  (for admins) an AI panel recommends keep / stop / promote.
 *
 *  Global across all alerts — patterns are system-wide. Leaderboard is ranked by
 *  end-of-week average return.
 */

import { useState } from "react";
import {
  useStrategyAnalysis,
  useRefreshStrategyAnalysis,
  useMe,
  type StrategyPattern,
} from "../api/hooks";
import { toast } from "./Toast";
import Card from "./ui/Card";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import { LineChart, AlertCircle, Inbox, Sparkles, Loader2, RefreshCw } from "lucide-react";

const LOOKBACKS = [30, 90, 180];

function fmtRelativeAge(iso: string | null): string {
  if (!iso) return "never";
  const diffH = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}

function retColor(v: number | null): string {
  if (v == null) return "text-text-faint";
  return v > 0 ? "text-bullish-text" : v < 0 ? "text-bearish-text" : "text-text-muted";
}

function winColor(v: number | null): string {
  if (v == null) return "text-text-faint";
  if (v >= 60) return "text-bullish-text";
  if (v >= 50) return "text-warning-text";
  return "text-bearish-text";
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtWin(v: number | null): string {
  return v == null ? "—" : `${v.toFixed(0)}%`;
}

const RECO_STYLE: Record<"keep" | "stop" | "promote", string> = {
  promote: "text-bullish-text",
  keep: "text-text-muted",
  stop: "text-bearish-text",
};

/* A verdict cell: recommendation (colored) + the swing/day/avoid call beneath. */
function Verdict({
  reco, cls, dim,
}: {
  reco: "keep" | "stop" | "promote" | null;
  cls: "Swing" | "Day" | "Avoid" | null;
  dim?: boolean;
}) {
  if (!reco) return <span className="text-text-faint">—</span>;
  return (
    <span className={dim ? "opacity-90" : ""}>
      <span className={`text-[11px] font-semibold uppercase tracking-wide ${RECO_STYLE[reco]}`}>{reco}</span>
      {cls && <span className="block text-[9px] text-text-faint">{cls}</span>}
    </span>
  );
}

/* ── One pattern row ─────────────────────────────────────────────── */

function PatternRow({ p }: { p: StrategyPattern }) {
  // Disagreement gets a left accent so divergences are easy to scan.
  const diverge = p.agree === false;
  return (
    <div className={`grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border-subtle/30 last:border-b-0 items-center text-xs ${diverge ? "bg-warning/5" : ""}`}>
      <span className="col-span-3 text-text-primary truncate cursor-help" title={p.description || p.label}>
        {p.label}
        {p.confidence === "low" && (
          <span className="text-[9px] text-text-faint ml-1" title="Small sample — unproven">low n</span>
        )}
      </span>
      <span className="col-span-1 text-right font-mono text-text-secondary">{p.n}</span>
      <span className="col-span-2 text-right font-mono">
        <span className={`font-semibold ${winColor(p.win_eod_pct)}`}>{fmtWin(p.win_eod_pct)}</span>
        <span className={`ml-1 text-[10px] ${retColor(p.avg_ret_eod)}`}>{fmtPct(p.avg_ret_eod)}</span>
      </span>
      <span className="col-span-2 text-right font-mono">
        <span className={`font-semibold ${winColor(p.win_eow_pct)}`}>{fmtWin(p.win_eow_pct)}</span>
        <span className={`ml-1 text-[10px] ${retColor(p.avg_ret_eow)}`}>{fmtPct(p.avg_ret_eow)}</span>
      </span>
      <span className="col-span-2 text-right">
        <Verdict reco={p.recommendation} cls={p.classification} />
      </span>
      <span className="col-span-2 text-right">
        <span className="inline-flex items-center justify-end gap-1">
          {diverge && <span className="h-1.5 w-1.5 rounded-full bg-warning-text" title="AI disagrees with the rules" />}
          <Verdict reco={p.ai_recommendation} cls={p.ai_classification} />
        </span>
      </span>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────────── */

export default function StrategyAnalysis() {
  const [lookback, setLookback] = useState(90);
  const { data, isLoading, error } = useStrategyAnalysis(lookback);
  const refresh = useRefreshStrategyAnalysis();
  const { data: me } = useMe();
  const isAdmin = me?.tier === "admin";

  function regenerate() {
    refresh.mutate(lookback, {
      onError: (e: unknown) => {
        const msg = (e as { message?: string })?.message || "Failed to generate analysis";
        toast.error(msg);
      },
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="flex items-center justify-between">
          <Skeleton w={200} h={20} />
          <Skeleton w={120} h={28} />
        </div>
        <Card padding="none"><SkeletonRow count={8} h={42} gap={0} /></Card>
      </div>
    );
  }
  if (error) {
    return (
      <Card padding="md">
        <div className="flex items-center gap-2 text-bearish-text">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">Failed to load strategy analysis.</span>
        </div>
      </Card>
    );
  }
  if (!data) return null;

  const patterns = data.patterns;

  return (
    <div className="space-y-4">
      {/* Header — lookback selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <LineChart className="h-4 w-4 text-accent" />
          <span className="font-semibold text-text-primary">Strategy Analysis</span>
        </div>
        <div className="flex items-center gap-1 text-[11px]">
          <span className="text-text-faint uppercase tracking-wider mr-1">Lookback:</span>
          {LOOKBACKS.map(d => (
            <button
              key={d}
              onClick={() => setLookback(d)}
              className={`px-2 py-1 rounded transition-colors ${
                lookback === d ? "bg-accent/15 text-accent" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-text-faint">
        Real <span className="text-text-secondary">close-to-close</span> forward return from the alert price.
        <span className="text-text-secondary"> EOD</span> = same-day close,
        <span className="text-text-secondary"> EOW</span> = end-of-week close. Win = closed higher than the
        alert price. <span className="text-bullish-text">Swing</span> = gains hold/build into Friday;
        <span className="text-warning-text"> Day</span> = pops at EOD then fades. Ranked by EOW average.
        Indicative, not tradeable P&L.
      </p>

      {/* Rule-vs-AI agreement banner */}
      {data.agreement_pct != null && (
        <Card padding="sm">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">
              Rule engine & AI agree on{" "}
              <span className={`font-semibold ${data.agreement_pct >= 70 ? "text-bullish-text" : data.agreement_pct >= 50 ? "text-warning-text" : "text-bearish-text"}`}>
                {data.agreement_pct.toFixed(0)}%
              </span>{" "}
              of patterns
            </span>
            <span className="text-[10px] text-text-faint">
              {data.agreement_pct >= 70
                ? "High agreement — the free daily rules track the weekly AI well."
                : "Divergence — review the AI column where they disagree."}
            </span>
          </div>
        </Card>
      )}

      {/* Leaderboard */}
      {patterns.length === 0 ? (
        <Card padding="md">
          <EmptyState
            size="sm"
            icon={Inbox}
            title="No graded patterns yet"
            hint="Forward returns are computed after market close. Once alerts have at least one closed session in the window, patterns appear here."
          />
        </Card>
      ) : (
        <Card padding="none">
          <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/50 bg-surface-2/30 text-[10px] uppercase tracking-wider text-text-faint">
            <div className="col-span-3">Pattern</div>
            <div className="col-span-1 text-right">n</div>
            <div className="col-span-2 text-right">EOD win / avg</div>
            <div className="col-span-2 text-right">EOW win / avg</div>
            <div className="col-span-2 text-right">Rule</div>
            <div className="col-span-2 text-right">AI</div>
          </div>
          {patterns.map(p => <PatternRow key={p.alert_type} p={p} />)}
        </Card>
      )}

      {/* AI recommendation panel */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-accent" />
            AI Summary
          </h3>
          <div className="flex items-center gap-2">
            {data.generated_at && (
              <span className="text-[10px] text-text-faint">Updated {fmtRelativeAge(data.generated_at)}</span>
            )}
            {isAdmin && (
              <button
                onClick={regenerate}
                disabled={refresh.isPending}
                className="flex items-center gap-1.5 rounded-md bg-surface-3 hover:bg-surface-4 px-2.5 py-1.5 text-[11px] font-medium text-text-secondary transition-colors disabled:opacity-40 active:scale-95"
              >
                {refresh.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                {data.ai_summary ? "Regenerate" : "Generate"}
              </button>
            )}
          </div>
        </div>
        <Card padding="md">
          {data.ai_summary ? (
            <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-text-secondary">
              {data.ai_summary}
            </pre>
          ) : (
            <p className="text-xs text-text-faint">
              {isAdmin
                ? "No AI verdicts yet — tap Generate to have Claude judge each pattern independently, then compare it column-by-column with the rules."
                : "No AI verdicts available yet."}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}
