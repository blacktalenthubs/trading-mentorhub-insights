/** PROTOTYPE — the redesigned "Today" home + signal card (Sub-spec J, #64).
 *  Self-contained, mock data, no backend wiring. View at /prototype.
 *  On-system: uses the real theme tokens (surface-*, bullish/bearish, JetBrains Mono prices).
 *  This is a design prototype to react to — not production. Refine in AIDesigner or by hand.
 */
import { useState, type ReactNode } from "react";
import {
  ShieldCheck, TrendingUp, ChevronRight, BookOpen, LineChart, Info, Check, Flame,
} from "lucide-react";

type Grade = "A" | "B" | "C";
type Side = "LONG" | "SHORT";

type Signal = {
  symbol: string; side: Side; grade: Grade; pattern: string; age: string;
  why: string; entry: number; target: number; targetLevel: string; stop: number;
  rNow: number; took?: boolean;
};

const SIGNALS: Signal[] = [
  { symbol: "NVDA", side: "LONG", grade: "A", pattern: "RC-H · 4h", age: "2m",
    why: "Reclaimed the broken high at 210 and held — buyers defending the level.",
    entry: 210.40, target: 213.73, targetLevel: "PDH", stop: 208.00, rNow: 1.3 },
  { symbol: "MU", side: "LONG", grade: "B", pattern: "PDL reclaim", age: "14m",
    why: "Undercut yesterday's low and snapped back above on rising volume.",
    entry: 174.20, target: 178.90, targetLevel: "EMA50", stop: 172.10, rNow: 0.4, took: true },
  { symbol: "SPY", side: "SHORT", grade: "C", pattern: "PDH reject · 4h", age: "31m",
    why: "Failed the prior-day high from below and closed back under it on a red bar.",
    entry: 746.10, target: 739.24, targetLevel: "PDL", stop: 748.40, rNow: -0.2 },
];

const WATCH = [
  { symbol: "SNDK", why: "Storage leader · 4× volume on a 3-week base", score: 92, dir: 1 },
  { symbol: "MU",   why: "Breakout-retest forming above 173", score: 88, dir: 1 },
  { symbol: "NBIS", why: "AI-chip group leader · holding higher lows", score: 81, dir: 1 },
  { symbol: "SPCX", why: "Lower highs, under the PDL — avoid", score: 34, dir: -1 },
];

const px = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const GRADE_STYLE: Record<Grade, string> = {
  A: "bg-bullish-subtle text-bullish-text border-bullish-muted",
  B: "bg-warning-subtle text-warning-text border-warning-muted",
  C: "bg-surface-3 text-text-muted border-border-default",
};

function SignalCard({ s }: { s: Signal }) {
  const long = s.side === "LONG";
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5 shadow-card">
      {/* header */}
      <div className="flex items-center gap-2">
        <span className="font-display font-semibold text-text-primary">{s.symbol}</span>
        <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{s.side}</span>
        <span className={`text-[11px] font-bold w-5 h-5 grid place-items-center rounded border ${GRADE_STYLE[s.grade]}`}>{s.grade}</span>
        <span className="ml-auto text-[11px] text-text-faint">{s.pattern}</span>
        <span className="text-[11px] text-text-faint tabular-nums">{s.age}</span>
      </div>
      {/* the WHY */}
      <p className="mt-2 text-[13px] leading-snug text-text-secondary">{s.why}</p>
      {/* entry · ONE target labeled with its level · stop */}
      <div className="mt-2.5 flex items-center gap-3 font-mono text-[12px] tabular-nums">
        <span className="text-text-muted">Entry <span className="text-text-primary">{px(s.entry)}</span></span>
        <span className={long ? "text-bullish-text" : "text-bearish-text"}>Target {px(s.target)} <span className="opacity-60">({s.targetLevel})</span></span>
        <span className="text-text-muted">Stop <span className="text-bearish-text">{px(s.stop)}</span></span>
      </div>
      {/* progressive disclosure */}
      <div className="mt-2.5 flex items-center gap-3 text-[11px] text-text-muted">
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><Info size={12}/> Why grade {s.grade}</button>
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><LineChart size={12}/> Chart</button>
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><BookOpen size={12}/> Learn</button>
      </div>
      {/* action + live R */}
      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
        {s.took
          ? <span className="inline-flex items-center gap-1 text-[12px] font-medium text-bullish-text"><Check size={14}/> Took it</span>
          : <button className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors">Took it</button>}
        <span className={`font-mono text-[12px] tabular-nums font-semibold ${s.rNow >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
          {s.rNow >= 0 ? "▲" : "▼"} {Math.abs(s.rNow).toFixed(1)}R
        </span>
      </div>
    </div>
  );
}

function SectionLabel({ children, action }: { children: ReactNode; action?: string }) {
  return (
    <div className="flex items-center justify-between px-1 mb-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{children}</span>
      {action && <button className="inline-flex items-center gap-0.5 text-[11px] text-accent hover:text-accent-hover">{action}<ChevronRight size={12}/></button>}
    </div>
  );
}

export default function PrototypeTodayPage() {
  const [tab, setTab] = useState("Today");
  return (
    <div className="min-h-screen bg-surface-0 text-text-primary font-body">
      {/* phone frame for the mobile-first prototype */}
      <div className="mx-auto max-w-md min-h-screen border-x border-border-subtle bg-surface-0 pb-20">
        {/* market read + posture */}
        <header className="px-4 pt-5 pb-3">
          <div className="flex items-baseline justify-between">
            <h1 className="font-display text-lg font-semibold">Good morning, B.</h1>
            <div className="flex items-center gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bullish-subtle text-bullish-text">● SPY HEALTHY</span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bearish-subtle text-bearish-text">BTC ↓</span>
            </div>
          </div>
          <div className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-text-muted">
            <ShieldCheck size={14} className="text-text-faint" /> Stops on every position · <span className="text-bullish-text font-medium">NORMAL</span>
          </div>
        </header>

        {/* worth watching today */}
        <section className="px-4 pt-2">
          <SectionLabel action="Discover">Worth watching today</SectionLabel>
          <div className="space-y-1.5">
            {WATCH.map((w) => (
              <div key={w.symbol} className="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {w.dir > 0 ? <TrendingUp size={13} className="text-bullish-text" /> : <Flame size={13} className="text-bearish-text rotate-180" />}
                    <span className="font-display text-[13px] font-semibold">{w.symbol}</span>
                  </div>
                  <p className="truncate text-[11.5px] text-text-muted mt-0.5">{w.why}</p>
                </div>
                <span className={`font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded tabular-nums ${w.score >= 70 ? "bg-bullish-subtle text-bullish-text" : "bg-surface-3 text-text-faint"}`}>{w.score}</span>
              </div>
            ))}
          </div>
        </section>

        {/* live signals */}
        <section className="px-4 pt-5">
          <SectionLabel action="All signals">Live signals</SectionLabel>
          <div className="space-y-2.5">
            {SIGNALS.map((s) => <SignalCard key={s.symbol} s={s} />)}
          </div>
        </section>

        {/* your day */}
        <section className="px-4 pt-5">
          <SectionLabel>Your day</SectionLabel>
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5">
            <div className="flex items-center justify-between text-[12px]">
              <span className="text-text-secondary">1 position open · <span className="font-mono text-bullish-text">MU +0.4R</span></span>
              <button className="text-[11px] text-accent hover:text-accent-hover">EOD review →</button>
            </div>
            <p className="mt-1.5 text-[11.5px] text-text-faint">At close we'll ask which signals you took — that's how we learn which patterns pay.</p>
          </div>
        </section>
      </div>

      {/* bottom nav (mobile) */}
      <nav className="fixed bottom-0 inset-x-0 mx-auto max-w-md border-t border-border-subtle bg-surface-1/95 backdrop-blur px-2 py-2 flex justify-around text-[10px]">
        {["Today", "Discover", "Trading", "Performance", "More"].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg ${tab === t ? "text-accent" : "text-text-faint"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${tab === t ? "bg-accent" : "bg-transparent"}`} />
            {t}
          </button>
        ))}
      </nav>
    </div>
  );
}
