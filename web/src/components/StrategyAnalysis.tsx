/** Strategy Analysis — Performance > Strategy Analysis tab.
 *
 *  Which patterns actually work, judged by REAL forward returns (close-to-close):
 *    - EOD %  — same-day close vs the alert price
 *    - EOW %  — end-of-week close vs the alert price ("did the gains hold?")
 *  Each pattern is classified Swing / Day / Avoid and given a keep/stop/promote call.
 *
 *  Recency-first, two views:
 *    - Daily  — one trading day (defaults to the latest with data). Rule engine
 *               only, instant + free.
 *    - Weekly — Mon-Fri rollup with the on-demand AI verdicts + rule/AI agreement.
 *
 *  Mobile-first: one stacked card per pattern (no dense grid).
 */

import { useState } from "react";
import {
  useStrategyAnalysis,
  useRefreshStrategyAnalysis,
  useMe,
  type StrategyPattern,
  type StrategyPeriod,
} from "../api/hooks";
import { toast } from "./Toast";
import Card from "./ui/Card";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import {
  AlertCircle, Inbox, Sparkles, Loader2, RefreshCw, ChevronLeft, ChevronRight,
} from "lucide-react";

/* ── formatting helpers ──────────────────────────────────────────── */

function fmtRelativeAge(iso: string | null): string {
  if (!iso) return "never";
  const diffH = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}
function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
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
  return v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function fmtWin(v: number | null): string {
  return v == null ? "—" : `${v.toFixed(0)}%`;
}

const CLASS_STYLE: Record<StrategyPattern["classification"], string> = {
  Swing: "bg-accent/15 text-accent",
  Day: "bg-warning/15 text-warning-text",
  Avoid: "bg-bearish/15 text-bearish-text",
};
const RECO_STYLE: Record<"keep" | "stop" | "promote", string> = {
  promote: "text-bullish-text",
  keep: "text-text-muted",
  stop: "text-bearish-text",
};

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}
function isoOffsetWeeks(iso: string, weeks: number): string {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + weeks * 7);
  return d.toISOString().slice(0, 10);
}

/* ── A labeled EOD/EOW metric line ───────────────────────────────── */

function MetricRow({ label, win, avg, pending }: {
  label: string; win: number | null; avg: number | null; pending?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] uppercase tracking-wider text-text-faint">{label}</span>
      {pending ? (
        <span className="text-[11px] text-text-faint italic">pending — week open</span>
      ) : (
        <span className="font-mono text-xs">
          <span className={`font-semibold ${winColor(win)}`}>{fmtWin(win)} win</span>
          <span className={`ml-2 ${retColor(avg)}`}>{fmtPct(avg)} avg</span>
        </span>
      )}
    </div>
  );
}

/* ── One pattern card ────────────────────────────────────────────── */

function PatternCard({ p, showAi }: { p: StrategyPattern; showAi: boolean }) {
  const diverge = showAi && p.agree === false;
  const eowPending = p.n_eow === 0 || p.avg_ret_eow == null;
  return (
    <Card padding="md" className={diverge ? "border-l-2 border-l-warning-text" : ""}>
      <div className="space-y-2">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <span className="text-sm font-semibold text-text-primary truncate" title={p.description || p.label}>
              {p.label}
            </span>
            <span className="ml-2 text-[10px] text-text-faint">n={p.n}{p.confidence === "low" && " · low n"}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${CLASS_STYLE[p.classification]}`}>
              {p.classification}
            </span>
            <span className={`text-[11px] font-semibold uppercase tracking-wide ${RECO_STYLE[p.recommendation]}`}>
              {p.recommendation}
            </span>
          </div>
        </div>

        {/* Metrics */}
        <div className="space-y-1 border-t border-border-subtle/40 pt-2">
          <MetricRow label="EOD" win={p.win_eod_pct} avg={p.avg_ret_eod} />
          <MetricRow label="EOW" win={p.win_eow_pct} avg={p.avg_ret_eow} pending={eowPending} />
        </div>

        {/* AI verdict (weekly only) */}
        {showAi && (
          <div className="flex items-center justify-between border-t border-border-subtle/40 pt-2">
            <span className="text-[10px] uppercase tracking-wider text-text-faint">AI</span>
            {p.ai_recommendation ? (
              <span className="flex items-center gap-1.5">
                {diverge && <span className="h-1.5 w-1.5 rounded-full bg-warning-text" title="AI disagrees with the rules" />}
                <span className={`text-[11px] font-semibold uppercase tracking-wide ${RECO_STYLE[p.ai_recommendation]}`}>
                  {p.ai_recommendation}
                </span>
                {p.ai_classification && <span className="text-[9px] text-text-faint">{p.ai_classification}</span>}
              </span>
            ) : (
              <span className="text-[11px] text-text-faint">not run</span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

/* ── Main component ──────────────────────────────────────────────── */

export default function StrategyAnalysis() {
  const [period, setPeriodState] = useState<StrategyPeriod>(() => {
    if (typeof window === "undefined") return "day";
    return (localStorage.getItem("strategy_period") as StrategyPeriod) || "day";
  });
  const [day, setDay] = useState<string | undefined>(undefined);     // undefined = latest graded
  const [weekAnchor, setWeekAnchor] = useState<string>(isoToday());
  const anchor = period === "day" ? day : weekAnchor;

  const { data, isLoading, error } = useStrategyAnalysis(period, anchor);
  const refresh = useRefreshStrategyAnalysis();
  const { data: me } = useMe();
  const isAdmin = me?.tier === "admin";

  function setPeriod(p: StrategyPeriod) {
    setPeriodState(p);
    try { localStorage.setItem("strategy_period", p); } catch { /* ignore */ }
  }

  function regenerate() {
    if (!data?.week_start) return;
    refresh.mutate(data.week_start, {
      onError: (e: unknown) => toast.error((e as { message?: string })?.message || "Failed to generate analysis"),
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton w={220} h={28} />
        <SkeletonRow count={5} h={96} gap={12} />
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

  // Sort per view: Daily by EOD (EOW usually pending), Weekly by EOW.
  const patterns = [...data.patterns].sort((a, b) => {
    const key = period === "day"
      ? [a.avg_ret_eod, b.avg_ret_eod]
      : [a.avg_ret_eow, b.avg_ret_eow];
    return (key[1] ?? -Infinity) - (key[0] ?? -Infinity);
  });

  // Day navigator state derived from available_days (newest first).
  const days = data.available_days ?? [];
  const curIdx = data.date ? days.indexOf(data.date) : -1;
  const olderDay = curIdx >= 0 && curIdx < days.length - 1 ? days[curIdx + 1] : null;
  const newerDay = curIdx > 0 ? days[curIdx - 1] : null;

  return (
    <div className="space-y-3">
      {/* View toggle */}
      <div className="flex items-center gap-1 border-b border-border-subtle">
        {(["day", "week"] as StrategyPeriod[]).map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
              period === p ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-secondary"
            }`}
          >
            {p === "day" ? "Daily" : "Weekly"}
          </button>
        ))}
      </div>

      {/* Navigator */}
      <div className="flex items-center justify-between gap-2">
        {period === "day" ? (
          <div className="flex items-center gap-2">
            <button
              onClick={() => olderDay && setDay(olderDay)}
              disabled={!olderDay}
              className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted disabled:opacity-30 transition-colors"
              title="Previous day"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-semibold text-text-primary">{fmtDay(data.date)}</span>
            <button
              onClick={() => newerDay && setDay(newerDay)}
              disabled={!newerDay}
              className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted disabled:opacity-30 transition-colors"
              title="Next day"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setWeekAnchor(isoOffsetWeeks(weekAnchor, -1))}
              className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted transition-colors"
              title="Previous week"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-semibold text-text-primary">
              {fmtDay(data.week_start)} – {fmtDay(data.week_end)}
            </span>
            <button
              onClick={() => setWeekAnchor(isoOffsetWeeks(weekAnchor, 1))}
              className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted transition-colors"
              title="Next week"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
            {weekAnchor !== isoToday() && (
              <button onClick={() => setWeekAnchor(isoToday())} className="text-[11px] text-accent hover:underline ml-1">
                this week
              </button>
            )}
          </div>
        )}
        <span className="text-[10px] text-text-faint">{patterns.length} patterns</span>
      </div>

      <p className="text-[11px] text-text-faint leading-relaxed">
        Real close-to-close forward return from the alert price. <span className="text-text-secondary">EOD</span> = same-day
        close, <span className="text-text-secondary">EOW</span> = end-of-week close. Win = closed higher than the alert price.
        <span className="text-accent"> Swing</span> = gains hold into Friday; <span className="text-warning-text">Day</span> =
        pops at EOD then fades. {period === "day" ? "Ranked by EOD average." : "Ranked by EOW average."} Indicative, not tradeable P&L.
      </p>

      {/* Weekly: rule-vs-AI agreement banner */}
      {period === "week" && data.agreement_pct != null && (
        <Card padding="sm">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">
              Rule & AI agree on{" "}
              <span className={`font-semibold ${data.agreement_pct >= 70 ? "text-bullish-text" : data.agreement_pct >= 50 ? "text-warning-text" : "text-bearish-text"}`}>
                {data.agreement_pct.toFixed(0)}%
              </span>{" "}
              of patterns
            </span>
            <span className="text-[10px] text-text-faint">
              {data.agreement_pct >= 70 ? "rules track the AI well" : "review where they disagree"}
            </span>
          </div>
        </Card>
      )}

      {/* Pattern cards */}
      {patterns.length === 0 ? (
        <Card padding="md">
          <EmptyState
            size="sm"
            icon={Inbox}
            title={period === "day" ? "No graded patterns for this day" : "No graded patterns this week"}
            hint="Forward returns are computed after market close. Step to a day/week that has closed sessions, or wait for tonight's backfill."
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {patterns.map((p) => <PatternCard key={p.alert_type} p={p} showAi={period === "week"} />)}
        </div>
      )}

      {/* Weekly: on-demand AI summary */}
      {period === "week" && (
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
              <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-text-secondary">{data.ai_summary}</pre>
            ) : (
              <p className="text-xs text-text-faint">
                {isAdmin
                  ? "No AI verdicts for this week yet — tap Generate to have Claude judge each pattern, then compare against the rules."
                  : "No AI verdicts for this week yet."}
              </p>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
