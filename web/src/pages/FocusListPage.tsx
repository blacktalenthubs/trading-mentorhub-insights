/** Trade Ideas — forward-looking ideas across three boards: Conviction (weekly-stage
 *  leaders), Emerging (early momentum turns), and Long Term (growth leaders). Old
 *  /focus-list · /conviction · /dashboard routes redirect here (App.tsx).
 *
 *  AI Scans + Social Buzz were REMOVED (no longer part of the product). Above the three
 *  boards sits the CONFLUENCE strip — names showing up on ≥2 boards at once, which is
 *  the strongest read (independent scans agreeing). Computed here by intersecting the
 *  three boards' symbols; no new backend.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Target, Gem, Compass, TrendingUp } from "lucide-react";
import { useEmerging, useWeeklyStage, useGrowth } from "../api/hooks";
import { ConvictionTabView } from "./ConvictionPage";
import { GrowthLeadersTabView } from "./GrowthLeadersPage";
import { EmergingTabView } from "./EmergingLeadersPage";

type IdeasTab = "conviction" | "emerging" | "long_term";

const IDEAS_TABS: { id: IdeasTab; label: string; icon: typeof Target }[] = [
  { id: "conviction", label: "Conviction", icon: Gem },
  { id: "emerging", label: "Emerging", icon: Compass },
  { id: "long_term", label: "Long Term", icon: TrendingUp },
];

/* ── Confluence — the mock's "🔥 On Multiple Boards": a name that surfaces on two or
   three independent boards is the highest-conviction read. Board keys map to the tabs:
   T = Turn (Emerging) · C = Conviction (Weekly Stage) · L = Long-term Core (Growth). ── */
type Board = "T" | "C" | "L";
type RankedConf = { symbol: string; boards: Board[]; why: string[]; conf: number };

const BOARD_META: Record<Board, { label: string; cls: string }> = {
  T: { label: "Early Turn", cls: "border-warning/40 bg-warning/10 text-warning-text" },
  C: { label: "Conviction", cls: "border-accent/40 bg-accent/10 text-accent" },
  L: { label: "Long-term Core", cls: "border-violet-400/40 bg-violet-400/10 text-violet-400" },
};

function ConfCard({ c, onChart }: { c: RankedConf; onChart: (s: string) => void }) {
  const order: Board[] = ["T", "C", "L"];
  return (
    <button onClick={() => onChart(c.symbol)} className="rounded-xl border border-border-subtle bg-surface-1 p-3 text-left transition-colors hover:border-warning/50">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[16px] font-bold text-text-primary">{c.symbol}</span>
        <div className="flex gap-1">
          {order.filter((b) => c.boards.includes(b)).map((b) => (
            <span key={b} title={BOARD_META[b].label} className={`rounded border px-1 py-0.5 text-[8.5px] font-bold uppercase ${BOARD_META[b].cls}`}>{b}</span>
          ))}
        </div>
        <span className="ml-auto font-mono text-[15px] font-bold text-bullish-text">{c.conf}</span>
      </div>
      <p className="mt-1.5 text-[11px] leading-snug text-text-muted">
        On <b className="text-text-secondary">{c.boards.length} boards</b> · {c.why.slice(0, 2).join(" · ")}
      </p>
    </button>
  );
}

function ConfluenceStrip({ onChart }: { onChart: (s: string) => void }) {
  const { data: em } = useEmerging();
  const { data: wk } = useWeeklyStage();
  const { data: gr } = useGrowth();
  const items = useMemo<RankedConf[]>(() => {
    const boards = new Map<string, Set<Board>>();
    const scores = new Map<string, number[]>();
    const whys = new Map<string, string[]>();
    const touch = (symbol: string, b: Board, score: number | null, why: string) => {
      const k = symbol.toUpperCase();
      if (!boards.has(k)) { boards.set(k, new Set()); scores.set(k, []); whys.set(k, []); }
      boards.get(k)!.add(b);
      if (score != null) scores.get(k)!.push(score);
      if (why) whys.get(k)!.push(why);
    };
    for (const e of em?.entries ?? []) touch(e.symbol, "T", e.score, e.why || "early turn");
    for (const e of wk?.entries ?? []) touch(e.symbol, "C", null, e.stage_label || "");
    for (const e of gr?.entries ?? []) touch(e.symbol, "L", e.score, `long-term ${e.grade}${e.rs_vs_spy != null ? ` · RS ${e.rs_vs_spy >= 0 ? "+" : ""}${Math.round(e.rs_vs_spy)}` : ""}`);
    return [...boards.entries()]
      .filter(([, set]) => set.size >= 2)
      .map(([symbol, set]) => {
        const s = scores.get(symbol)!;
        return {
          symbol,
          boards: [...set],
          why: whys.get(symbol)!,
          conf: s.length ? Math.round(s.reduce((a, b) => a + b, 0) / s.length) : 70,
        };
      })
      .sort((a, b) => b.boards.length - a.boards.length || b.conf - a.conf)
      .slice(0, 6);
  }, [em, wk, gr]);

  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-warning-text">🔥 On Multiple Boards</h2>
      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => <ConfCard key={c.symbol} c={c} onChart={onChart} />)}
      </div>
    </div>
  );
}

export default function FocusListPage() {
  const nav = useNavigate();
  const goChart = (s: string) => nav(`/trading?symbol=${encodeURIComponent(s)}`);
  const [tab, setTab] = useState<IdeasTab>(() => {
    if (typeof window === "undefined") return "conviction";
    // Deep-link from a notification tap: ?tab=emerging (or any valid Ideas tab).
    const valid: IdeasTab[] = ["conviction", "emerging", "long_term"];
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q && valid.includes(q as IdeasTab)) return q as IdeasTab;
    const saved = localStorage.getItem("ideas_active_tab");
    return valid.includes(saved as IdeasTab) ? (saved as IdeasTab) : "conviction";  // drop legacy social/ai/day/swing
  });
  function pickTab(t: IdeasTab) {
    setTab(t);
    try { localStorage.setItem("ideas_active_tab", t); } catch { /* ignore */ }
  }

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4">
        {/* Header + tab bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Trade Ideas</h1>
              <p className="text-[11px] text-text-muted">
                High-conviction, emerging, and long-term ideas — what to look at this session.
              </p>
            </div>
          </div>
          <div className="flex bg-surface-2 rounded-lg p-0.5">
            {IDEAS_TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => pickTab(t.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    tab === t.id
                      ? "bg-surface-4 text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <Icon className="h-3 w-3" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Confluence — names on ≥2 boards, the strongest cross-board read (all boards) */}
        <ConfluenceStrip onChart={goChart} />

        {tab === "conviction" && <ConvictionTabView />}
        {tab === "emerging" && <EmergingTabView />}
        {tab === "long_term" && <GrowthLeadersTabView />}
      </div>
    </div>
  );
}
