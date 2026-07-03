/** Trade Ideas — ONE unified pipeline (the mock merges the old 3 tabs into a single
 *  lens-filtered table). Three scan boards feed it: Early Turn (Emerging), Conviction
 *  (Weekly Stage), Long-term Core (Growth). Each symbol becomes one row carrying the
 *  union of the boards' data; a name on ≥2 boards floats up in the Confluence strip.
 *
 *  AI Scans + Social Buzz were REMOVED (retired features). All computed frontend-side
 *  from the existing board snapshots — no new backend. (Work 3b will add the expandable
 *  per-symbol scorecard.)
 */

import { Fragment, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Target, Plus, Check, ChevronRight, RefreshCw } from "lucide-react";
import { useEmerging, useWeeklyStage, useGrowth, useWatchlist, useAddSymbol, useRefreshEmerging, useRefreshWeeklyStage, useRefreshGrowth } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import type { EmergingEntry, WeeklyStageEntry, GrowthEntry, EmergingSnapshot, WeeklyStageSnapshot, GrowthSnapshot } from "./InPlay.types";

/* ── Boards. T = Early Turn (Emerging) · C = Conviction (Weekly Stage) · L = Long-term
   Core (Growth). One row per symbol carries whichever boards flagged it. ── */
type Board = "T" | "C" | "L";
const BOARD_ORDER: Board[] = ["T", "C", "L"];
const BOARD_META: Record<Board, { label: string; cls: string; dot: string }> = {
  T: { label: "Early Turn", cls: "border-warning/40 bg-warning/10 text-warning-text", dot: "bg-warning" },
  C: { label: "Conviction", cls: "border-accent/40 bg-accent/10 text-accent", dot: "bg-accent" },
  L: { label: "Long-term Core", cls: "border-violet-400/40 bg-violet-400/10 text-violet-400", dot: "bg-violet-400" },
};

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
        <span key={b} title={BOARD_META[b].label} className={`rounded border px-1 py-0.5 text-[8.5px] font-bold uppercase ${BOARD_META[b].cls}`}>{b}</span>
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
              <p className="text-[11px] text-text-muted">Early turns, conviction leaders, and long-term core — one pipeline, ranked.</p>
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
      </div>
    </div>
  );
}
