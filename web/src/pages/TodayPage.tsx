/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  The day in one screen: market read + worth-watching + live signals + your day.
 *  Reuses the live hooks; renders the redesigned AlertCard. Its own scroll root
 *  (AppLayout <main> is overflow-hidden — see feedback_page_scroll_container).
 */
import { useMemo, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, TrendingUp, ChevronRight, Flame } from "lucide-react";
import { useAlertsToday, useSpyLiveRegime, useBtcLiveRegime, useWatchlistRank } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";
import { isFeedSignal } from "../lib/alertFormat";
import AlertCard from "../components/AlertCard";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function RegimeChip({ label, r }: { label: string; r?: SpyRegimeSnapshot }) {
  const ok = r?.status === "ok";
  const weak = !!r?.below_pdl;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${!ok ? "bg-surface-3 text-text-faint" : weak ? "bg-bearish-subtle text-bearish-text" : "bg-bullish-subtle text-bullish-text"}`}>
      ● {label} {ok ? (weak ? "WEAK" : "HEALTHY") : "—"}
    </span>
  );
}

function SectionLabel({ children, action, onAction }: { children: ReactNode; action?: string; onAction?: () => void }) {
  return (
    <div className="flex items-center justify-between px-1 mb-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{children}</span>
      {action && <button onClick={onAction} className="inline-flex items-center gap-0.5 text-[11px] text-accent hover:text-accent-hover active:opacity-70">{action}<ChevronRight size={12} /></button>}
    </div>
  );
}

export default function TodayPage() {
  const nav = useNavigate();
  const { data: alerts } = useAlertsToday();
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  const { data: rank } = useWatchlistRank();

  const goChart = (symbol: string) => nav(`/trading?symbol=${encodeURIComponent(symbol)}`);

  const liveSignals = useMemo(
    () => (alerts ?? [])
      .filter((a) => isFeedSignal(a.alert_type) && !a.suppressed_reason)
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .slice(0, 6),
    [alerts],
  );
  const took = useMemo(() => (alerts ?? []).filter((a) => a.user_action === "took"), [alerts]);
  const watch = useMemo(() => (rank ?? []).slice(0, 5), [rank]);

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6 pb-16">
        {/* market read + posture */}
        <header className="pb-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="font-display text-lg font-semibold text-text-primary">{greeting()}</h1>
            <div className="flex items-center gap-2">
              <RegimeChip label="SPY" r={spy} />
              <RegimeChip label="BTC" r={btc} />
            </div>
          </div>
          <div className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-text-muted">
            <ShieldCheck size={14} className="text-text-faint" /> Stops on every position ·{" "}
            <span className={spy?.below_pdl ? "text-warning-text font-medium" : "text-bullish-text font-medium"}>
              {spy?.below_pdl ? "DEFENSIVE" : "NORMAL"}
            </span>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
          {/* main column — live signals */}
          <section className="lg:col-span-2">
            <SectionLabel action="Trading" onAction={() => nav("/trading")}>Live signals</SectionLabel>
            {liveSignals.length > 0 ? (
              <div className="space-y-2.5">
                {liveSignals.map((a) => <AlertCard key={a.id} a={a} onChart={goChart} />)}
              </div>
            ) : (
              <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
                No live signals yet today. The market read above tells you the regime.
              </div>
            )}
          </section>

          {/* side column — worth watching + your day */}
          <div className="space-y-6">
            {watch.length > 0 && (
              <section>
                <SectionLabel>Worth watching today</SectionLabel>
                <div className="space-y-1.5">
                  {watch.map((w) => (
                    <button key={w.symbol} onClick={() => goChart(w.symbol)}
                      className="flex w-full items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5 text-left hover:bg-surface-2 active:opacity-80">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          {w.score >= 60 ? <TrendingUp size={13} className="text-bullish-text" /> : <Flame size={13} className="text-bearish-text rotate-180" />}
                          <span className="font-display text-[13px] font-semibold text-text-primary">{w.symbol}</span>
                        </div>
                        <p className="truncate text-[11.5px] text-text-muted mt-0.5">{w.signal || w.nearest_level || "—"}</p>
                      </div>
                      <span className={`font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded tabular-nums ${w.score >= 60 ? "bg-bullish-subtle text-bullish-text" : "bg-surface-3 text-text-faint"}`}>{Math.round(w.score)}</span>
                      <ChevronRight size={14} className="text-text-faint" />
                    </button>
                  ))}
                </div>
              </section>
            )}
            <section>
              <SectionLabel>Your day</SectionLabel>
              <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5">
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-text-secondary">
                    {took.length > 0 ? `${took.length} position${took.length > 1 ? "s" : ""} marked Took` : "No positions marked yet"}
                  </span>
                  <button onClick={() => nav("/performance")} className="text-[11px] text-accent hover:text-accent-hover">EOD review →</button>
                </div>
                <p className="mt-1.5 text-[11.5px] text-text-faint">At close, review which signals you took — that's how we learn which patterns pay.</p>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
