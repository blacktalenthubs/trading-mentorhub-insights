/** PROTOTYPE — redesigned app (Sub-spec J, #64). Clickable: Today · Discover · Trading.
 *  Self-contained, mock data, no backend wiring. View at /prototype.
 *  On-system: real theme tokens (surface-*, bullish/bearish, JetBrains Mono prices). Design prototype, not production.
 */
import { useState, type ReactNode } from "react";
import {
  ShieldCheck, TrendingUp, ChevronRight, BookOpen, LineChart, Info, Check, Flame, Search,
} from "lucide-react";

type Grade = "A" | "B" | "C";
type Side = "LONG" | "SHORT";
type Signal = {
  symbol: string; side: Side; grade: Grade; pattern: string; age: string;
  why: string; entry: number; target: number; targetLevel: string; stop: number; rNow: number; took?: boolean;
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
  { symbol: "SNDK", why: "Storage leader · 4× volume on a 3-week base", score: 92, dir: 1, tag: "Volume surge" },
  { symbol: "MU",   why: "Breakout-retest forming above 173", score: 88, dir: 1, tag: "Pre-breakout" },
  { symbol: "NBIS", why: "AI-chip group leader · holding higher lows", score: 81, dir: 1, tag: "Sector leader" },
  { symbol: "AEHR", why: "Reclaimed the 50-day on 3× volume", score: 78, dir: 1, tag: "Volume surge" },
  { symbol: "IREN", why: "Coiling under resistance · volume drying up", score: 71, dir: 1, tag: "Pre-breakout" },
  { symbol: "RKLB", why: "Sector laggard turning · first higher high", score: 64, dir: 1, tag: "Sector leader" },
  { symbol: "SPCX", why: "Lower highs, under the PDL — avoid", score: 34, dir: -1, tag: "Weak" },
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
      <div className="flex items-center gap-2">
        <span className="font-display font-semibold text-text-primary">{s.symbol}</span>
        <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{s.side}</span>
        <span className={`text-[11px] font-bold w-5 h-5 grid place-items-center rounded border ${GRADE_STYLE[s.grade]}`}>{s.grade}</span>
        <span className="ml-auto text-[11px] text-text-faint">{s.pattern}</span>
        <span className="text-[11px] text-text-faint tabular-nums">{s.age}</span>
      </div>
      <p className="mt-2 text-[13px] leading-snug text-text-secondary">{s.why}</p>
      <div className="mt-2.5 flex items-center gap-3 font-mono text-[12px] tabular-nums">
        <span className="text-text-muted">Entry <span className="text-text-primary">{px(s.entry)}</span></span>
        <span className={long ? "text-bullish-text" : "text-bearish-text"}>Target {px(s.target)} <span className="opacity-60">({s.targetLevel})</span></span>
        <span className="text-text-muted">Stop <span className="text-bearish-text">{px(s.stop)}</span></span>
      </div>
      <div className="mt-2.5 flex items-center gap-3 text-[11px] text-text-muted">
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><Info size={12}/> Why grade {s.grade}</button>
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><LineChart size={12}/> Chart</button>
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><BookOpen size={12}/> Learn</button>
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
        {s.took
          ? <span className="inline-flex items-center gap-1 text-[12px] font-medium text-bullish-text"><Check size={14}/> Took it</span>
          : <button className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors">Took it</button>}
        <span className={`font-mono text-[12px] tabular-nums font-semibold ${s.rNow >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{s.rNow >= 0 ? "▲" : "▼"} {Math.abs(s.rNow).toFixed(1)}R</span>
      </div>
    </div>
  );
}

function SectionLabel({ children, action, onAction }: { children: ReactNode; action?: string; onAction?: () => void }) {
  return (
    <div className="flex items-center justify-between px-1 mb-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{children}</span>
      {action && <button onClick={onAction} className="inline-flex items-center gap-0.5 text-[11px] text-accent hover:text-accent-hover active:opacity-70">{action}<ChevronRight size={12}/></button>}
    </div>
  );
}

function WatchRow({ w, full, onClick }: { w: typeof WATCH[number]; full?: boolean; onClick?: () => void }) {
  return (
    <div onClick={onClick} className={`flex items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5 ${onClick ? "cursor-pointer hover:bg-surface-2 active:opacity-80" : ""}`}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          {w.dir > 0 ? <TrendingUp size={13} className="text-bullish-text" /> : <Flame size={13} className="text-bearish-text rotate-180" />}
          <span className="font-display text-[13px] font-semibold">{w.symbol}</span>
          {full && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-surface-3 text-text-faint">{w.tag}</span>}
        </div>
        <p className="truncate text-[11.5px] text-text-muted mt-0.5">{w.why}</p>
      </div>
      <span className={`font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded tabular-nums ${w.score >= 70 ? "bg-bullish-subtle text-bullish-text" : "bg-surface-3 text-text-faint"}`}>{w.score}</span>
      {full && <ChevronRight size={14} className="text-text-faint" />}
    </div>
  );
}

/* ─────────────────────────── SCREENS ─────────────────────────── */

function TodayScreen({ go }: { go: (t: string) => void }) {
  return (
    <>
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
      <section className="px-4 pt-2">
        <SectionLabel action="Discover" onAction={() => go("Discover")}>Worth watching today</SectionLabel>
        <div className="space-y-1.5">{WATCH.slice(0, 4).map((w) => <WatchRow key={w.symbol} w={w} onClick={() => go("Discover")} />)}</div>
      </section>
      <section className="px-4 pt-5">
        <SectionLabel action="All signals" onAction={() => go("Trading")}>Live signals</SectionLabel>
        <div className="space-y-2.5">{SIGNALS.map((s) => <SignalCard key={s.symbol} s={s} />)}</div>
      </section>
      <section className="px-4 pt-5">
        <SectionLabel>Your day</SectionLabel>
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5">
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-text-secondary">1 position open · <span className="font-mono text-bullish-text">MU +0.4R</span></span>
            <button onClick={() => go("Performance")} className="text-[11px] text-accent hover:text-accent-hover active:opacity-70">EOD review →</button>
          </div>
          <p className="mt-1.5 text-[11.5px] text-text-faint">At close we'll ask which signals you took — that's how we learn which patterns pay.</p>
        </div>
      </section>
    </>
  );
}

function DiscoverScreen() {
  const filters = ["All", "Sector leaders", "Volume surge", "Pre-breakout"];
  const [f, setF] = useState("All");
  const rows = f === "All" ? WATCH : WATCH.filter((w) => w.tag === f);
  return (
    <>
      <header className="px-4 pt-5 pb-1">
        <h1 className="font-display text-lg font-semibold">Discover</h1>
        <p className="text-[12px] text-text-muted">Movers worth your attention — caught early, with the why.</p>
      </header>
      <div className="px-4 pt-3 flex gap-1.5 overflow-x-auto no-scrollbar">
        {filters.map((x) => (
          <button key={x} onClick={() => setF(x)}
            className={`shrink-0 text-[11px] px-2.5 py-1 rounded-full border ${f === x ? "bg-accent-subtle border-accent-muted text-accent" : "bg-surface-1 border-border-subtle text-text-muted"}`}>{x}</button>
        ))}
      </div>
      <section className="px-4 pt-3 space-y-1.5">
        {rows.map((w) => <WatchRow key={w.symbol} w={w} full />)}
        {rows.length === 0 && <p className="text-[12px] text-text-faint px-1 py-6 text-center">Nothing in this bucket right now.</p>}
      </section>
    </>
  );
}

function TradingScreen() {
  const [rail, setRail] = useState("Signals");
  // mock candles
  const candles = [12, 18, 14, 22, 19, 26, 30, 24, 28, 34, 31, 38];
  return (
    <>
      <header className="px-4 pt-5 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-display text-lg font-semibold">NVDA</span>
          <span className="font-mono text-sm text-bullish-text tabular-nums">210.40 <span className="text-[11px]">+2.0%</span></span>
        </div>
        <div className="flex gap-1 text-[11px]">
          {["1h", "4h", "D"].map((t) => (
            <button key={t} className={`px-2 py-0.5 rounded ${t === "4h" ? "bg-surface-3 text-text-primary" : "text-text-faint"}`}>{t}</button>
          ))}
        </div>
      </header>
      {/* chart mock with E/S/T level lines */}
      <div className="mx-4 rounded-xl border border-border-subtle bg-surface-1 p-3 relative h-44 overflow-hidden">
        <div className="absolute inset-x-3 top-6 border-t border-dashed border-bullish/60"><span className="font-mono text-[9px] text-bullish-text bg-surface-1 px-1 -mt-2 ml-1 inline-block">T 213.73 (PDH)</span></div>
        <div className="absolute inset-x-3 top-[64px] border-t border-dashed border-accent/60"><span className="font-mono text-[9px] text-accent bg-surface-1 px-1 -mt-2 ml-1 inline-block">E 210.40</span></div>
        <div className="absolute inset-x-3 bottom-7 border-t border-dashed border-bearish/60"><span className="font-mono text-[9px] text-bearish-text bg-surface-1 px-1 -mt-2 ml-1 inline-block">S 208.00</span></div>
        <div className="absolute inset-x-0 bottom-0 h-full flex items-end justify-center gap-1 px-4 pb-2">
          {candles.map((h, i) => (
            <div key={i} className={`w-2 rounded-sm ${i % 3 === 1 ? "bg-bearish/70" : "bg-bullish/70"}`} style={{ height: `${h * 2.4}px` }} />
          ))}
        </div>
      </div>
      {/* one segmented rail, not three panes */}
      <div className="px-4 pt-3 flex gap-1 text-[11px]">
        {["Signals", "AI", "Levels"].map((r) => (
          <button key={r} onClick={() => setRail(r)}
            className={`flex-1 py-1.5 rounded-lg border ${rail === r ? "bg-surface-3 border-border-default text-text-primary" : "bg-surface-1 border-border-subtle text-text-muted"}`}>{r}</button>
        ))}
      </div>
      <section className="px-4 pt-3 space-y-2.5">
        {rail === "Signals" && <SignalCard s={SIGNALS[0]} />}
        {rail === "AI" && (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5 text-[12px] text-text-secondary">
            <div className="flex items-center gap-1.5 text-accent mb-1.5"><Search size={13}/> Analyze NVDA</div>
            NVDA reclaimed the broken high at 210 and is holding above it — a breakout-retest. With-trend (above EMA50), volume confirming. Next wall: PDH 213.73. <span className="text-text-faint">Spend 1 token →</span>
          </div>
        )}
        {rail === "Levels" && (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-1 font-mono text-[12px] tabular-nums">
            {[["PDH","213.73","text-bearish-text"],["EMA8","211.90","text-text-muted"],["Entry","210.40","text-accent"],["EMA50","207.40","text-text-muted"],["PDL","205.10","text-bullish-text"]].map(([k,v,c]) => (
              <div key={k} className="flex justify-between px-3 py-1.5 border-b border-border-subtle last:border-0">
                <span className="text-text-muted">{k}</span><span className={c}>{v}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function Placeholder({ name }: { name: string }) {
  return <div className="px-4 pt-24 text-center text-[13px] text-text-faint">{name} — coming next in the prototype.</div>;
}

export default function PrototypeTodayPage() {
  const [tab, setTab] = useState("Today");
  return (
    <div className="min-h-screen bg-surface-0 text-text-primary font-body">
      <div className="mx-auto max-w-md min-h-screen border-x border-border-subtle bg-surface-0 pb-20">
        {tab === "Today" && <TodayScreen go={setTab} />}
        {tab === "Discover" && <DiscoverScreen />}
        {tab === "Trading" && <TradingScreen />}
        {tab === "Performance" && <Placeholder name="Performance" />}
        {tab === "More" && <Placeholder name="More" />}
      </div>
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
