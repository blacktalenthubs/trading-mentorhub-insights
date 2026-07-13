/** Universe / Research (spec 71) — browse the full leaders universe grouped by
 *  sector, strongest sector first, sortable within a sector by key factors.
 *  Click any name → its full research dossier (numbers + analyst recs + AI brief
 *  + earnings) in a modal. Available to ALL signed-in users (not admin-gated).
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Layers, Search, ChevronDown, ChevronRight, LineChart, Loader2, X, AlertCircle,
} from "lucide-react";
import {
  useUniverse,
  useSymbolFundamentals,
  useRefreshFundamentals,
  useGenerateAIBrief,
  useMe,
  type FundamentalsItem,
  type UniverseSector,
} from "../api/hooks";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import ResearchCard, {
  AI_ADMIN_EMAIL, consensusBadge, money, fmtMarketCap,
} from "../components/ResearchCard";

/* ── derived-metric helpers (see spec: derive from metrics{}) ────────── */
const num = (v: number | null | undefined) => (v == null ? null : v);
/** % off the 52-week high — negative = below the high. */
function offHigh(it: FundamentalsItem): number | null {
  const lp = it.metrics?.last_price, hi = it.metrics?.week52_high;
  if (lp == null || hi == null || hi <= 0) return null;
  return (lp - hi) / hi * 100;
}
/** % vs the 200-day MA — positive = above. */
function vs200(it: FundamentalsItem): number | null {
  const lp = it.metrics?.last_price, ma = it.metrics?.ma200;
  if (lp == null || ma == null || ma <= 0) return null;
  return (lp / ma - 1) * 100;
}
const signed = (v: number | null, digits = 1) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
const posNeg = (v: number | null) =>
  v == null ? "text-text-faint" : v > 0 ? "text-bullish-text" : v < 0 ? "text-bearish-text" : "text-text-muted";

/* ── sector strength bar — normalized against the hottest sector ─────── */
function StrengthBar({ strength, max }: { strength: number; max: number }) {
  const pct = max > 0 ? Math.min(100, Math.abs(strength) / max * 100) : 0;
  const up = strength >= 0;
  return (
    <span className="flex items-center gap-1.5" title={`Sector strength ${strength >= 0 ? "+" : ""}${strength.toFixed(3)}`}>
      <span className="hidden sm:block h-1.5 w-16 overflow-hidden rounded-full bg-surface-3">
        <span
          className={`block h-full rounded-full ${up ? "bg-emerald-400" : "bg-bearish-text/70"}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className={`font-mono text-[10px] ${up ? "text-emerald-400" : "text-bearish-text"}`}>
        {strength >= 0 ? "+" : ""}{strength.toFixed(2)}
      </span>
    </span>
  );
}

/* ── a single collapsible sector section with its sortable table ─────── */
function SectorSection({
  group, maxStrength, onPick, onChart,
}: {
  group: UniverseSector; maxStrength: number;
  onPick: (sym: string) => void; onChart: (sym: string) => void;
}) {
  const [open, setOpen] = useState(true);

  const symbolCell = (r: FundamentalsItem) => (
    <span className="flex items-center gap-2">
      <span className="font-bold text-text-primary">{r.symbol}</span>
      {r.company_name && <span className="hidden lg:inline truncate max-w-[180px] text-[10px] text-text-faint">{r.company_name}</span>}
      <button
        onClick={(e) => { e.stopPropagation(); onChart(r.symbol); }}
        title={`Open ${r.symbol} on the Trading chart`}
        className="text-text-faint transition-colors hover:text-accent"
      >
        <LineChart className="h-3.5 w-3.5" />
      </button>
    </span>
  );

  const columns: Column<FundamentalsItem>[] = [
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: symbolCell },
    { key: "price", label: "Price", align: "right", cls: "hidden sm:table-cell", value: (r) => num(r.metrics?.last_price) ?? -1, render: (r) => <span className="font-mono text-text-primary">{money(r.metrics?.last_price)}</span> },
    { key: "eps", label: "EPS gr", align: "right", value: (r) => num(r.eps_growth_pct) ?? -9999, render: (r) => <span className={`font-mono ${posNeg(num(r.eps_growth_pct))}`}>{signed(num(r.eps_growth_pct))}</span> },
    { key: "rev", label: "Rev gr", align: "right", cls: "hidden md:table-cell", value: (r) => num(r.metrics?.revenue_growth_pct) ?? -9999, render: (r) => <span className={`font-mono ${posNeg(num(r.metrics?.revenue_growth_pct))}`}>{signed(num(r.metrics?.revenue_growth_pct))}</span> },
    { key: "pe", label: "P/E", align: "right", cls: "hidden md:table-cell", value: (r) => num(r.pe_ratio) ?? 99999, render: (r) => <span className="font-mono text-text-secondary">{r.pe_ratio != null ? r.pe_ratio.toFixed(1) : "—"}</span> },
    { key: "off52", label: "% off 52wH", align: "right", cls: "hidden lg:table-cell", value: (r) => offHigh(r) ?? -9999, render: (r) => { const v = offHigh(r); return <span className={`font-mono ${v != null && v >= -10 ? "text-bullish-text" : "text-text-secondary"}`}>{signed(v)}</span>; } },
    { key: "vs200", label: "vs 200-DMA", align: "right", cls: "hidden xl:table-cell", value: (r) => vs200(r) ?? -9999, render: (r) => <span className={`font-mono ${posNeg(vs200(r))}`}>{signed(vs200(r))}</span> },
    { key: "mktcap", label: "Mkt cap", align: "right", cls: "hidden sm:table-cell", value: (r) => num(r.market_cap) ?? -1, render: (r) => <span className="font-mono text-text-secondary">{fmtMarketCap(r.market_cap)}</span> },
    { key: "rec", label: "View", align: "right", cls: "w-16", value: (r) => r.consensus ?? "", render: (r) => r.consensus ? <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${consensusBadge(r.consensus)}`}>{r.consensus}</span> : <span className="text-text-faint">—</span> },
  ];

  const mobileRow = (r: FundamentalsItem) => (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span className="font-bold text-text-primary">{r.symbol}</span>
          {r.consensus && <span className={`rounded px-1 py-0.5 text-[9px] font-bold ${consensusBadge(r.consensus)}`}>{r.consensus}</span>}
        </span>
        <span className="font-mono text-sm text-text-primary">{money(r.metrics?.last_price)}</span>
      </div>
      {r.company_name && <div className="truncate text-[10px] text-text-faint">{r.company_name}</div>}
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-text-muted">
        <span className={posNeg(num(r.eps_growth_pct))}>EPS {signed(num(r.eps_growth_pct))}</span>
        <span>P/E {r.pe_ratio != null ? r.pe_ratio.toFixed(1) : "—"}</span>
        <span className={offHigh(r) != null && offHigh(r)! >= -10 ? "text-bullish-text" : ""}>{signed(offHigh(r))} off 52wH</span>
        <span>{fmtMarketCap(r.market_cap)}</span>
      </div>
    </div>
  );

  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 transition-colors hover:bg-surface-2/40"
      >
        <span className="flex items-center gap-2 text-text-primary">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span className="font-mono text-[12.5px] font-bold uppercase tracking-wide text-amber-400/90">{group.sector}</span>
          <span className="font-mono text-[10.5px] text-text-faint">{group.count}</span>
        </span>
        <StrengthBar strength={group.strength} max={maxStrength} />
      </button>
      {open && (
        <div className="border-t border-border-subtle p-2">
          <ScreenerTable<FundamentalsItem>
            rows={group.items}
            columns={columns}
            rowKey={(r) => r.symbol}
            onRowClick={(r) => onPick(r.symbol)}
            defaultSort={{ key: "mktcap", dir: "desc" }}
            mobileRow={mobileRow}
            empty={<div className="px-4 py-6 text-center text-sm text-text-muted">No names in this sector.</div>}
          />
        </div>
      )}
    </div>
  );
}

/* ── research modal — reuses the shared ResearchCard, fetched on-demand ── */
function ResearchModal({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const { data, isLoading, isError } = useSymbolFundamentals(symbol);
  const refresh = useRefreshFundamentals();
  const aiGen = useGenerateAIBrief();
  const { data: me } = useMe();
  const isAdmin = (me?.email ?? "").trim().toLowerCase() === AI_ADMIN_EMAIL;
  const navigate = useNavigate();

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto overflow-x-hidden bg-black/60 p-3 sm:p-6" onClick={onClose}>
      <div
        className="my-auto w-full max-w-3xl rounded-2xl border border-border-subtle bg-surface-0 shadow-elevated"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2.5">
          <span className="font-mono text-[12px] uppercase tracking-wide text-text-muted">Research · {symbol}</span>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-text-faint transition-colors hover:text-text-secondary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[82vh] overflow-y-auto overflow-x-hidden p-4">
          {isLoading || !data ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-text-muted">
              {isError ? (
                <span className="flex items-center gap-2 text-bearish-text"><AlertCircle className="h-4 w-4" /> Couldn't load {symbol}.</span>
              ) : (
                <><Loader2 className="h-4 w-4 animate-spin" /> Loading {symbol}…</>
              )}
            </div>
          ) : (
            <ResearchCard
              it={data}
              isAdmin={isAdmin}
              onOpen={() => navigate(`/trading?symbol=${encodeURIComponent(symbol)}`)}
              onRefresh={() => refresh.mutate(symbol)}
              refreshing={refresh.isPending}
              onGenerate={() => aiGen.mutate(symbol)}
              generating={aiGen.isPending}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/* ── the page ────────────────────────────────────────────────────────── */
export default function UniverseResearchPage() {
  const { data, isLoading, isError } = useUniverse();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const navigate = useNavigate();

  const q = search.trim().toLowerCase();

  // Filter items across every sector by symbol / company name. Sectors keep the
  // server's strongest-first order; empty sectors drop out.
  const sectors = useMemo(() => {
    const src = data?.sectors ?? [];
    if (!q) return src;
    return src
      .map((s) => ({
        ...s,
        items: s.items.filter(
          (it) => it.symbol.toLowerCase().includes(q) || (it.company_name || "").toLowerCase().includes(q),
        ),
      }))
      .filter((s) => s.items.length > 0);
  }, [data, q]);

  const maxStrength = useMemo(
    () => Math.max(0, ...(data?.sectors ?? []).map((s) => Math.abs(s.strength))),
    [data],
  );
  const totalNames = useMemo(
    () => (data?.sectors ?? []).reduce((n, s) => n + s.count, 0),
    [data],
  );
  const refreshed = data?.last_refreshed_at ? new Date(data.last_refreshed_at) : null;

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-4 sm:p-6 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-emerald-400" />
          <div>
            <h1 className="font-display text-lg font-bold text-text-primary">Research · Universe</h1>
            <p className="text-[11px] text-text-muted">
              The full leaders universe grouped by sector, strongest sector first. Sort within a sector, then click any name for its full research.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-faint">
          {totalNames > 0 && <span>{totalNames} names</span>}
          {refreshed && <span>Updated {refreshed.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-faint" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search any name — symbol or company…"
          className="w-full rounded-lg border border-border-subtle bg-surface-2 py-2.5 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-faint outline-none focus:border-accent"
        />
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-xl border border-border-subtle bg-surface-1/60" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-1 p-4 text-bearish-text">
          <AlertCircle className="h-4 w-4" /> <span className="text-sm">Couldn't load the research universe.</span>
        </div>
      ) : sectors.length === 0 ? (
        <div className="rounded-xl border border-border-subtle bg-surface-1 px-4 py-12 text-center text-sm text-text-muted">
          {q ? `No name matches "${search}".` : "No names in the research universe yet — it fills as the nightly refresh runs."}
        </div>
      ) : (
        <div className="space-y-3">
          {sectors.map((group) => (
            <SectorSection
              key={group.sector}
              group={group}
              maxStrength={maxStrength}
              onPick={setSelected}
              onChart={(sym) => navigate(`/trading?symbol=${encodeURIComponent(sym)}`)}
            />
          ))}
        </div>
      )}

      {selected && <ResearchModal symbol={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
