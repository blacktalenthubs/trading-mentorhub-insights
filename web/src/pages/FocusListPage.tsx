/** Trade Ideas — ONE unified pipeline (the mock merges the old 3 tabs into a single
 *  lens-filtered table). Three scan boards feed it: Early Turn (Emerging), Conviction
 *  (Weekly Stage), Long-term Core (Growth). Each symbol becomes one row carrying the
 *  union of the boards' data; a name on ≥2 boards floats up in the Confluence strip.
 *
 *  AI Scans + Social Buzz were REMOVED (retired features). All computed frontend-side
 *  from the existing board snapshots — no new backend. (Work 3b will add the expandable
 *  per-symbol scorecard.)
 */

import { Fragment, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Target, Plus, Check, ChevronRight, RefreshCw, Info } from "lucide-react";
import { useEmerging, useWeeklyStage, useGrowth, useWatchlist, useAddSymbol, useRefreshEmerging, useRefreshWeeklyStage, useRefreshGrowth, useLongTermFinders, type LongTermFinders, type Finder } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import type { EmergingEntry, WeeklyStageEntry, GrowthEntry, EmergingSnapshot, WeeklyStageSnapshot, GrowthSnapshot } from "./InPlay.types";

/* ── Boards. T = Early Turn (Emerging) · C = Conviction (Weekly Stage) · L = Long-term
   Core (Growth). One row per symbol carries whichever boards flagged it. ── */
type Board = "T" | "C" | "L";
const BOARD_ORDER: Board[] = ["T", "C", "L"];
const BOARD_META: Record<Board, { label: string; desc: string; cls: string; dot: string }> = {
  T: { label: "Early Turn", desc: "just turning up from a base (Stage 1→2) — the earliest entry, higher risk/reward", cls: "border-warning/40 bg-warning/10 text-warning-text", dot: "bg-warning" },
  C: { label: "Conviction", desc: "an established leader in a healthy weekly uptrend (above a rising 30-week MA)", cls: "border-accent/40 bg-accent/10 text-accent", dot: "bg-accent" },
  L: { label: "Long-term Core", desc: "a fundamentally strong growth leader to hold for the long run", cls: "border-violet-400/40 bg-violet-400/10 text-violet-400", dot: "bg-violet-400" },
};

/* Plain-language key — the boards + metrics are jargon to a busy trader, and this is an
   education-first product. Collapsed by default; one tap teaches the whole vocabulary. */
function Legend() {
  const Row = ({ b, children }: { b: Board; children: ReactNode }) => (
    <li className="flex gap-1.5">
      <span className={`h-fit shrink-0 rounded border px-1 py-0.5 text-[8.5px] font-bold uppercase ${BOARD_META[b].cls}`}>{b}</span>
      <span>{children}</span>
    </li>
  );
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-4 text-[11px] leading-relaxed">
      <div className="grid gap-5 sm:grid-cols-3">
        <div>
          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">The three boards</div>
          <ul className="space-y-1.5 text-text-muted">
            <Row b="T"><b className="text-text-secondary">Early Turn</b> — {BOARD_META.T.desc}.</Row>
            <Row b="C"><b className="text-text-secondary">Conviction</b> — {BOARD_META.C.desc}.</Row>
            <Row b="L"><b className="text-text-secondary">Long-term Core</b> — {BOARD_META.L.desc}.</Row>
          </ul>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">Setup terms</div>
          <ul className="space-y-1.5 text-text-muted">
            <li><b className="text-text-secondary">Stage 2</b> — Weinstein's "advancing" phase: price above a rising 30-week MA — the uptrend sweet spot. (1 base → 2 advance → 3 top → 4 decline.)</li>
            <li><b className="text-text-secondary">On N boards</b> — how many of the three scans flagged the name. Two or three independent signals agreeing is the strongest read.</li>
          </ul>
        </div>
        <div>
          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">The numbers</div>
          <ul className="space-y-1.5 text-text-muted">
            <li><b className="text-text-secondary">RS</b> — relative strength vs the S&amp;P 500. Higher = a stronger leader.</li>
            <li><b className="text-text-secondary">Off 52wH</b> — % below the 52-week high. Closer to 0 = near new highs.</li>
            <li><b className="text-text-secondary">GR</b> — grade A/B/C · <b className="text-text-secondary">Score</b> — a 0–100 composite quality read.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

type MergedRow = {
  symbol: string;
  sector: string | null;
  boards: Board[];
  price: number | null;
  rs: number | null;        // RS vs SPY
  off52: number | null;     // % off the 52-week high
  score: number | null;     // best board score (0–100)
  grade: string | null;     // best board grade
  why: string;
  em?: EmergingEntry;
  wk?: WeeklyStageEntry;
  gr?: GrowthEntry;
};

const GRANK: Record<string, number> = { A: 0, "A-": 0.5, B: 1, "B-": 1.5, C: 2, "C-": 2.5, D: 3 };
const bestGrade = (a: string | null, b: string): string => (!a ? b : (GRANK[a] ?? 9) <= (GRANK[b] ?? 9) ? a : b);

function buildRows(em?: EmergingSnapshot, wk?: WeeklyStageSnapshot, gr?: GrowthSnapshot): MergedRow[] {
  const m = new Map<string, MergedRow>();
  const base = (symbol: string): MergedRow => {
    const k = symbol.toUpperCase();
    let r = m.get(k);
    if (!r) { r = { symbol: k, sector: null, boards: [], price: null, rs: null, off52: null, score: null, grade: null, why: "" }; m.set(k, r); }
    return r;
  };
  for (const e of gr?.entries ?? []) {
    const r = base(e.symbol); r.boards.push("L"); r.gr = e;
    r.sector ??= e.sector; r.price ??= e.last_price; r.rs ??= e.rs_vs_spy; r.off52 ??= e.pct_off_52wh;
    r.score = Math.max(r.score ?? 0, e.score); r.grade = bestGrade(r.grade, e.grade);
    if (!r.why) r.why = `long-term core${e.stage2 ? " · stage 2" : ""}`;
  }
  for (const e of em?.entries ?? []) {
    const r = base(e.symbol); r.boards.push("T"); r.em = e;
    r.sector ??= e.sector; r.price ??= e.last_price; r.rs ??= e.rs_vs_spy; r.off52 ??= e.pct_off_52wh;
    r.score = Math.max(r.score ?? 0, e.score); r.grade = bestGrade(r.grade, e.grade);
    if (!r.why) r.why = e.why || "early turn";
  }
  for (const e of wk?.entries ?? []) {
    const r = base(e.symbol); r.boards.push("C"); r.wk = e;
    r.price ??= e.price;
    if (!r.why) r.why = e.stage_label || "conviction";
  }
  return [...m.values()];
}

function GradeDot({ g }: { g: string | null }) {
  if (!g) return <span className="text-text-faint">—</span>;
  const c = g.startsWith("A") ? "bg-bullish-subtle text-bullish-text" : g.startsWith("B") ? "bg-accent/15 text-accent" : "bg-surface-3 text-text-muted";
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${c}`}>{g}</span>;
}

function Boards({ boards }: { boards: Board[] }) {
  return (
    <div className="flex gap-1">
      {BOARD_ORDER.filter((b) => boards.includes(b)).map((b) => (
        <span key={b} title={`${BOARD_META[b].label} — ${BOARD_META[b].desc}`} className={`rounded border px-1 py-0.5 text-[8.5px] font-bold uppercase ${BOARD_META[b].cls}`}>{b}</span>
      ))}
    </div>
  );
}

/* ── Confluence — names on ≥2 boards (the strongest cross-board read). ── */
function ConfluenceStrip({ rows, onChart }: { rows: MergedRow[]; onChart: (s: string) => void }) {
  const items = useMemo(
    () => rows.filter((r) => r.boards.length >= 2).sort((a, b) => b.boards.length - a.boards.length || (b.score ?? 0) - (a.score ?? 0)).slice(0, 6),
    [rows],
  );
  if (items.length === 0) return null;
  return (
    <div className="space-y-2">
      <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-warning-text">🔥 On Multiple Boards</h2>
      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 lg:grid-cols-3">
        {items.map((c) => (
          <button key={c.symbol} onClick={() => onChart(c.symbol)} className="rounded-xl border border-border-subtle bg-surface-1 p-3 text-left transition-colors hover:border-warning/50">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[16px] font-bold text-text-primary">{c.symbol}</span>
              <Boards boards={c.boards} />
              <span className="ml-auto font-mono text-[15px] font-bold text-bullish-text">{c.score ?? "—"}</span>
            </div>
            <p className="mt-1.5 text-[11px] leading-snug text-text-muted"><b className="text-text-secondary">On {c.boards.length} boards</b> · {c.why}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

type SortKey = "score" | "rs" | "off52" | "price" | "symbol";
function sortVal(r: MergedRow, k: SortKey): number | string {
  switch (k) {
    case "symbol": return r.symbol;
    case "rs": return r.rs ?? -Infinity;
    case "off52": return r.off52 ?? -Infinity;
    case "price": return r.price ?? -Infinity;
    default: return r.score ?? -Infinity;
  }
}
const fmtPct = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);
const fmtPx = (v: number | null) => (v == null ? "—" : `$${v.toFixed(2)}`);
const fmtAge = (iso: string | null) => {
  if (!iso) return "never";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

/* ── Expanded per-symbol scorecard (mock's row-expand): the merged scorecard checklist,
   Street fundamentals, Tape stats, and actions. All from the boards' entries; the four
   mock fields we don't have (20d return, %days>50MA, mkt cap, analyst target) are dropped
   in favour of what the scans actually carry. ── */
const humanize = (k: string) => k.replace(/_/g, " ");

function ScoreItem({ label, status }: { label: string; status: string }) {
  const ok = status === "pass", no = status === "fail";
  return (
    <div className="flex items-center gap-1.5 text-[11px]">
      <span className={ok ? "text-bullish-text" : no ? "text-bearish-text" : "text-text-faint"}>{ok ? "✓" : no ? "✗" : "◔"}</span>
      <span className={ok ? "text-text-secondary" : "text-text-muted"}>{label}</span>
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-2"><dt className="text-text-faint">{k}</dt><dd className="font-mono text-text-secondary">{v}</dd></div>;
}

function DetailRow({ r, onChart, owned, onAdd, adding }: { r: MergedRow; onChart: (s: string) => void; owned: boolean; onAdd: () => void; adding: boolean }) {
  const scorecard = { ...(r.gr?.scorecard ?? {}), ...(r.em?.scorecard ?? {}) };
  const scItems = Object.entries(scorecard);
  const stage = r.wk?.stage_label ?? (r.gr?.stage2 ? "Stage 2 · Advancing" : r.em?.stage_turn ? "Stage turn" : "—");
  return (
    <tr className="bg-surface-1/50">
      <td colSpan={10} className="px-3.5 py-3">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">Scorecard</div>
            <div className="space-y-1">
              {scItems.length ? scItems.map(([k, v]) => <ScoreItem key={k} label={humanize(k)} status={v} />) : <span className="text-[11px] text-text-faint">—</span>}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">Street</div>
            <dl className="space-y-1 text-[11px]">
              <Kv k="Rating" v={r.gr?.consensus ?? "—"} />
              <Kv k="Rev growth" v={r.gr?.rev_growth_pct != null ? `${r.gr.rev_growth_pct >= 0 ? "+" : ""}${r.gr.rev_growth_pct}%` : "—"} />
              <Kv k="Gross margin" v={r.gr?.gross_margin_pct != null ? `${r.gr.gross_margin_pct}%` : "—"} />
              <Kv k="Stage" v={stage} />
            </dl>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">Tape</div>
            <dl className="space-y-1 text-[11px]">
              <Kv k="RS vs SPY" v={r.rs != null ? `${r.rs >= 0 ? "+" : ""}${Math.round(r.rs)}` : "—"} />
              <Kv k="Vol surge" v={r.em?.vol_surge != null ? `${r.em.vol_surge.toFixed(1)}×` : "—"} />
              <Kv k="Off 52w high" v={fmtPct(r.off52)} />
              <Kv k="Vs 30w MA" v={r.wk?.dist_vs_ma_pct != null ? `${r.wk.dist_vs_ma_pct >= 0 ? "+" : ""}${r.wk.dist_vs_ma_pct.toFixed(1)}%` : "—"} />
            </dl>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-faint">Actions</div>
            <div className="space-y-1.5">
              <button onClick={() => onChart(r.symbol)} className="block w-full rounded-lg bg-accent/15 px-3 py-1.5 text-[11px] font-semibold text-accent transition-colors hover:bg-accent/25">Open in Trading →</button>
              {owned ? (
                <div className="flex items-center gap-1.5 text-[11px] text-bullish-text"><Check className="h-3.5 w-3.5" /> On watchlist</div>
              ) : (
                <button onClick={onAdd} disabled={adding} className="block w-full rounded-lg border border-border-subtle px-3 py-1.5 text-[11px] text-text-secondary transition-colors hover:border-accent disabled:opacity-50">★ Add to watchlist</button>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function FocusListPage() {
  const nav = useNavigate();
  const goChart = (s: string) => nav(`/trading?symbol=${encodeURIComponent(s)}`);
  const { data: em, isLoading: lEm } = useEmerging();
  const { data: wk, isLoading: lWk } = useWeeklyStage();
  const { data: gr, isLoading: lGr } = useGrowth();
  const { data: ltf } = useLongTermFinders();
  const { data: watchlist } = useWatchlist();
  const addSym = useAddSymbol();
  const owned = useMemo(() => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())), [watchlist]);
  // Curate/run — the scans auto-run on the backend (weekly-stage Mon 8:00 · emerging
  // daily 8:10 · growth on demand), but let a pro force a fresh scan of all three.
  const { isPro } = useFeatureGate();
  const rEm = useRefreshEmerging();
  const rWk = useRefreshWeeklyStage();
  const rGr = useRefreshGrowth();
  const running = rEm.isPending || rWk.isPending || rGr.isPending;
  const runAll = () => { rEm.mutate(); rWk.mutate(); rGr.mutate(); };
  const scanCaps = [em?.captured_at, wk?.captured_at, gr?.captured_at].filter(Boolean) as string[];
  const oldestScan = scanCaps.length ? scanCaps.reduce((a, b) => (a < b ? a : b)) : null;
  const anyStale = !!(em?.stale || wk?.stale || gr?.stale);

  const rows = useMemo(() => buildRows(em, wk, gr), [em, wk, gr]);
  const counts = useMemo(() => ({
    all: rows.length,
    T: rows.filter((r) => r.boards.includes("T")).length,
    C: rows.filter((r) => r.boards.includes("C")).length,
    L: rows.filter((r) => r.boards.includes("L")).length,
  }), [rows]);
  const ownedInIdeas = useMemo(() => rows.filter((r) => owned.has(r.symbol)).length, [rows, owned]);

  const [lens, setLens] = useState<"all" | Board>("all");
  const [showLegend, setShowLegend] = useState(false);
  const [topTab, setTopTab] = useState<"ideas" | "finders">("ideas");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sort, setSort] = useState<{ k: SortKey; dir: "asc" | "desc" }>({ k: "score", dir: "desc" });
  const onSort = (k: SortKey) => setSort((s) => (s.k === k ? { k, dir: s.dir === "asc" ? "desc" : "asc" } : { k, dir: k === "symbol" ? "asc" : "desc" }));

  const filtered = useMemo(() => {
    const base = lens === "all" ? rows : rows.filter((r) => r.boards.includes(lens));
    const arr = [...base];
    arr.sort((a, b) => {
      const va = sortVal(a, sort.k), vb = sortVal(b, sort.k);
      const c = typeof va === "string" ? va.localeCompare(vb as string) : (va as number) - (vb as number);
      return sort.dir === "asc" ? c : -c;
    });
    return arr;
  }, [rows, lens, sort]);

  const loading = lEm || lWk || lGr;
  const LENSES: { id: "all" | Board; label: string; n: number; dot?: string }[] = [
    { id: "all", label: "All", n: counts.all },
    { id: "T", label: "Early Turn", n: counts.T, dot: BOARD_META.T.dot },
    { id: "C", label: "Conviction", n: counts.C, dot: BOARD_META.C.dot },
    { id: "L", label: "Long-term Core", n: counts.L, dot: BOARD_META.L.dot },
  ];
  const Th = ({ k, label, right }: { k: SortKey; label: string; right?: boolean }) => (
    <th className={`px-2.5 py-2 font-medium ${right ? "text-right" : "text-left"}`}>
      <button onClick={() => onSort(k)} className="inline-flex items-center gap-0.5 hover:text-text-secondary">{label}{sort.k === k ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}</button>
    </th>
  );

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4">
        {/* Header + scan freshness / run control */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Trade Ideas</h1>
              <p className="text-[11px] text-text-muted">
                Early turns, conviction leaders, and long-term core — one pipeline, ranked.{" "}
                <button onClick={() => setShowLegend((v) => !v)} className="inline-flex items-center gap-0.5 align-baseline text-accent hover:underline"><Info className="h-3 w-3" /> What these mean</button>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-text-faint">
            <span>Scanned {fmtAge(oldestScan)}{anyStale ? " · stale" : ""}</span>
            {isPro && (
              <button onClick={runAll} disabled={running} className="inline-flex items-center gap-1.5 rounded-full bg-accent/15 px-3 py-1 font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-50">
                <RefreshCw className={`h-3 w-3 ${running ? "animate-spin" : ""}`} /> {running ? "Scanning…" : "Run scans"}
              </button>
            )}
          </div>
        </div>

        {/* top tabs */}
        <div className="flex gap-1 border-b border-border-subtle">
          {([["ideas", "Trade Ideas"], ["finders", "🛰️ Long Term Finders"]] as const).map(([id, label]) => (
            <button key={id} onClick={() => setTopTab(id)}
              className={`-mb-px border-b-2 px-3 py-2 text-xs font-semibold transition-colors ${topTab === id ? "border-accent text-accent" : "border-transparent text-text-muted hover:text-text-secondary"}`}>
              {label}
            </button>
          ))}
        </div>

        {topTab === "finders" ? (
          <LongTermFindersSection data={ltf} owned={owned} onChart={goChart} onAdd={(sy) => addSym.mutate(sy)} adding={addSym.isPending} />
        ) : (
        <>
        {showLegend && <Legend />}

        <ConfluenceStrip rows={rows} onChart={goChart} />

        {/* Lens bar */}
        <div className="flex flex-wrap items-center gap-1.5">
          {LENSES.map((l) => (
            <button
              key={l.id}
              onClick={() => setLens(l.id)}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                lens === l.id ? "border-accent bg-accent/10 text-text-primary" : "border-border-subtle text-text-muted hover:text-text-secondary"
              }`}
            >
              {l.dot && <span className={`h-1.5 w-1.5 rounded-full ${l.dot}`} />}
              {l.label} <span className="text-text-faint">{l.n}</span>
            </button>
          ))}
          {ownedInIdeas > 0 && <span className="ml-auto text-[11px] text-warning-text">★ {ownedInIdeas} already on your watchlist</span>}
        </div>

        {/* Unified table */}
        {loading && rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-text-muted">Loading ideas…</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-sm text-text-muted">No ideas on this lens yet.</div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-[12px]">
              <thead className="border-b border-border text-text-faint">
                <tr>
                  <th className="px-2.5 py-2 text-left font-medium">#</th>
                  <th className="px-2.5 py-2 text-left font-medium">GR</th>
                  <Th k="symbol" label="Symbol" />
                  <th className="px-2.5 py-2 text-left font-medium">Boards</th>
                  <th className="px-2.5 py-2 text-left font-medium">Why</th>
                  <Th k="rs" label="RS" right />
                  <Th k="score" label="Score" right />
                  <Th k="price" label="Price" right />
                  <Th k="off52" label="Off 52wH" right />
                  <th className="px-2.5 py-2 text-right font-medium">Add</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((r, i) => (
                  <Fragment key={r.symbol}>
                  <tr onClick={() => setExpanded((s) => (s === r.symbol ? null : r.symbol))} className="cursor-pointer transition-colors hover:bg-surface-2/50">
                    <td className="px-2.5 py-2 text-text-faint">
                      <span className="inline-flex items-center gap-1"><ChevronRight className={`h-3 w-3 transition-transform ${expanded === r.symbol ? "rotate-90" : ""}`} /><span className="tabular-nums">{i + 1}</span></span>
                    </td>
                    <td className="px-2.5 py-2"><GradeDot g={r.grade} /></td>
                    <td className="px-2.5 py-2">
                      <div className="font-mono font-bold text-text-primary">{r.symbol}</div>
                      {r.sector && <div className="text-[10px] text-text-faint">{r.sector}</div>}
                    </td>
                    <td className="px-2.5 py-2"><Boards boards={r.boards} /></td>
                    <td className="px-2.5 py-2 max-w-[240px] whitespace-normal text-[11px] leading-snug text-text-muted">{r.why}</td>
                    <td className={`px-2.5 py-2 text-right font-mono tabular-nums ${(r.rs ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.rs == null ? "—" : `${r.rs >= 0 ? "+" : ""}${Math.round(r.rs)}`}</td>
                    <td className="px-2.5 py-2 text-right font-mono font-semibold tabular-nums text-text-secondary">{r.score ?? "—"}</td>
                    <td className="px-2.5 py-2 text-right font-mono tabular-nums text-text-secondary">{fmtPx(r.price)}</td>
                    <td className="px-2.5 py-2 text-right font-mono tabular-nums text-text-faint">{fmtPct(r.off52)}</td>
                    <td className="px-2.5 py-2 text-right">
                      {owned.has(r.symbol) ? (
                        <Check className="ml-auto h-4 w-4 text-bullish-text" />
                      ) : (
                        <button onClick={(e) => { e.stopPropagation(); addSym.mutate(r.symbol); }} disabled={addSym.isPending} className="ml-auto rounded p-1 text-accent hover:bg-accent/10 disabled:opacity-50" title={`Add ${r.symbol}`}>
                          <Plus className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded === r.symbol && <DetailRow r={r} onChart={goChart} owned={owned.has(r.symbol)} onAdd={() => addSym.mutate(r.symbol)} adding={addSym.isPending} />}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        </>
        )}
      </div>
    </div>
  );
}

function LongTermFindersSection({ data, owned, onChart, onAdd, adding }: {
  data: LongTermFinders | undefined;
  owned: Set<string>; onChart: (s: string) => void; onAdd: (s: string) => void; adding: boolean;
}) {
  const [emergingOnly, setEmergingOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  if (!data?.finders?.length) return null;
  const finders = data.finders.filter((f) => !emergingOnly || f.tier === "emerging");
  return (
    <div className="mt-6">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-bold text-text-primary">🛰️ Long Term Finders</h2>
        <span className="text-[11px] text-text-faint">the ETF technique · as of {data.as_of ?? "—"}</span>
        <button onClick={() => setEmergingOnly((v) => !v)}
          className={`ml-auto rounded-md border px-2.5 py-1 font-mono text-[11px] transition-colors ${emergingOnly ? "border-accent text-accent" : "border-border-subtle text-text-muted hover:text-text-primary"}`}>
          ★ Emerging only
        </button>
      </div>
      <p className="mb-3 max-w-2xl text-[11px] text-text-faint">
        Top-10 holdings across {data.etfs.length} ETFs, ranked by <b>overlap</b> — a name held by more ETFs (a broad ETF <i>and</i> its sector ETF) is doubly-confirmed. <span className="text-accent">★ emerging</span> = only in sector/thematic ETFs — the finders before they go mainstream. Get them on the radar, then do the deep dive.
      </p>
      <div className="overflow-x-auto rounded-lg border border-border-subtle">
        <table className="w-full min-w-[560px] text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle text-[10px] uppercase tracking-wide text-text-faint">
              <th className="px-3 py-2 text-left font-semibold">#</th>
              <th className="px-3 py-2 text-left font-semibold">Symbol</th>
              <th className="px-3 py-2 text-left font-semibold">Archetype</th>
              <th className="px-3 py-2 text-right font-semibold">Overlap</th>
              <th className="px-3 py-2 text-right font-semibold">Top weight</th>
              <th className="px-3 py-2 text-left font-semibold">In ETFs</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {finders.map((f, i) => (
              <Fragment key={f.symbol}>
                <tr onClick={() => setOpen(open === f.symbol ? null : f.symbol)} className="cursor-pointer border-b border-border-subtle hover:bg-surface-3/40">
                  <td className="px-3 py-2 font-mono text-text-faint"><span className="inline-flex items-center gap-1"><ChevronRight className={`h-3 w-3 transition-transform ${open === f.symbol ? "rotate-90" : ""}`} />{i + 1}</span></td>
                  <td className="px-3 py-2">
                    <button onClick={(e) => { e.stopPropagation(); onChart(f.symbol); }} className="font-bold text-text-primary hover:text-sky-400">{f.symbol}</button>
                    {f.tier === "emerging" && <span className="ml-1.5 text-[10px] text-accent">★</span>}
                    <div className="max-w-[180px] truncate text-[10px] text-text-faint">{f.name}</div>
                  </td>
                  <td className="px-3 py-2">{f.dossier ? <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${ARCH_CLS[f.dossier.archetype] ?? "bg-surface-3 text-text-muted"}`}>{f.dossier.archetype}</span> : <span className="text-text-faint">—</span>}</td>
                  <td className="px-3 py-2 text-right font-mono font-semibold text-text-secondary">{f.overlap}×</td>
                  <td className="px-3 py-2 text-right font-mono text-text-secondary">{f.max_weight.toFixed(1)}%</td>
                  <td className="px-3 py-2"><div className="flex flex-wrap gap-1">{f.etfs.map((e) => <span key={e} className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[10px] text-text-muted">{e}</span>)}</div></td>
                  <td className="px-3 py-2 text-right">
                    {owned.has(f.symbol)
                      ? <Check className="inline h-4 w-4 text-bullish-text" />
                      : <button onClick={(e) => { e.stopPropagation(); onAdd(f.symbol); }} disabled={adding} className="rounded p-1 text-accent hover:bg-accent/10 disabled:opacity-50" title={`Add ${f.symbol}`}><Plus className="h-4 w-4" /></button>}
                  </td>
                </tr>
                {open === f.symbol && f.dossier && <DossierRow f={f} onChart={onChart} />}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const ARCH_CLS: Record<string, string> = {
  "Moonshot": "bg-amber-500/15 text-amber-400",
  "Emerging Leader": "bg-sky-500/15 text-sky-400",
  "Compounder": "bg-bullish-subtle text-bullish-text",
  "Profitable Growth": "bg-bullish-subtle text-bullish-text",
  "Watch": "bg-surface-3 text-text-muted",
};
function fUsd(v: number | null | undefined): string {
  if (v == null) return "—";
  const a = Math.abs(v), sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(0)}M`;
  return `${sign}$${a.toFixed(0)}`;
}
function fPct(v: number | null | undefined, sign = false): string {
  if (v == null) return "—";
  const p = v * 100;
  return `${sign && p >= 0 ? "+" : ""}${p.toFixed(0)}%`;
}
function DossierRow({ f, onChart }: { f: Finder; onChart: (s: string) => void }) {
  const d = f.dossier!;
  const items: { l: string; v: string; c?: string }[] = [
    { l: "Rev growth", v: fPct(d.revenue_growth, true), c: (d.revenue_growth ?? 0) > 0 ? "text-bullish-text" : "text-bearish-text" },
    { l: "Revenue", v: fUsd(d.revenue) },
    { l: "Gross margin", v: fPct(d.gross_margin) },
    { l: "Op margin", v: fPct(d.operating_margin), c: (d.operating_margin ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text" },
    { l: "Profit margin", v: fPct(d.profit_margin), c: (d.profit_margin ?? 0) > 0 ? "text-bullish-text" : "text-bearish-text" },
    { l: "Cash", v: fUsd(d.cash) },
    { l: "Debt", v: fUsd(d.debt) },
    { l: "Runway", v: d.runway_years ? `${d.runway_years}yr` : "—" },
    { l: "Cap / Rev", v: d.cap_to_rev ? `${d.cap_to_rev}×` : "—" },
    { l: "Analyst", v: (d.rec ?? "—").replace("_", " ") },
  ];
  return (
    <tr className="bg-surface-0">
      <td colSpan={7} className="px-4 py-3">
        <div className="mb-2.5 flex flex-wrap items-center gap-2">
          <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${ARCH_CLS[d.archetype] ?? "bg-surface-3 text-text-muted"}`}>{d.archetype}</span>
          <span className="text-[12px] text-text-secondary">{d.read}</span>
          <button onClick={() => onChart(f.symbol)} className="ml-auto text-[11px] text-sky-400 hover:underline">View chart →</button>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4 lg:grid-cols-5">
          {items.map((it) => (
            <div key={it.l} className="flex items-center justify-between text-[11px]">
              <span className="text-text-faint">{it.l}</span>
              <span className={`font-mono tabular-nums ${it.c ?? "text-text-secondary"}`}>{it.v}</span>
            </div>
          ))}
        </div>
        <p className="mt-2.5 text-[10px] text-text-faint">Fundamentals via market data — a starting read for your diligence, not a recommendation.</p>
      </td>
    </tr>
  );
}
