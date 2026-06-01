/** In-Play Volume Screener (spec 62) — uses the shared ScreenerTable.
 *  Keeps its own status header, preset controls, RVOL bars, and market-state empty.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, Zap, Moon, RefreshCw } from "lucide-react";
import { useInPlay, useRefreshInPlay } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import ScreenerTable, { type Column } from "./ScreenerTable";
import GradeBadge, { GRADE_RANK } from "./GradeBadge";
import { IN_PLAY_PRESETS, type InPlayEntry, type InPlayPreset } from "../pages/InPlay.types";

function compact(n: number): string {
  if (!isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}
const px = (n: number) => `$${n.toFixed(2)}`;

function Pct({ v }: { v: number }) {
  const up = v >= 0;
  return <span className={`font-mono ${up ? "text-bullish-text" : "text-bearish-text"}`}>{up ? "+" : ""}{v.toFixed(2)}%</span>;
}

function SetupBadge({ e }: { e: InPlayEntry }) {
  if (!e.setup) return <span className="text-text-faint text-xs">—</span>;
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent bg-accent/10 border border-accent/20 px-2 py-0.5 rounded-md whitespace-nowrap">
      <Zap className="h-3 w-3" />{e.setup.pattern || "Setup"}
    </span>
  );
}

function RvolCell({ v, max }: { v: number; max: number }) {
  const w = Math.max(4, Math.min(100, (v / (max || 1)) * 100));
  const hot = v >= 2;
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="hidden lg:block w-16 h-1.5 rounded-full bg-surface-3 overflow-hidden">
        <div className={`h-full rounded-full ${hot ? "bg-accent" : "bg-text-faint/50"}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`font-mono ${hot ? "text-accent" : "text-text-secondary"}`}>{v.toFixed(1)}x</span>
    </div>
  );
}

/** VWAP slope — grade gate 2. Rising (≥0.05%) = buyers paying up = strength. */
function VwapSlopeCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-text-faint font-mono">—</span>;
  const strong = v >= 0.05;
  return (
    <span className={`font-mono ${strong ? "text-bullish-text" : v < 0 ? "text-bearish-text" : "text-text-muted"}`}>
      {v >= 0 ? "+" : ""}{v.toFixed(2)}%
    </span>
  );
}

/** Why this grade? A = ≥2× RVOL AND rising VWAP. Shown on hover over the badge. */
const inPlayGradeTip = (r: InPlayEntry) => {
  const slope = r.vwap_slope != null ? `${r.vwap_slope >= 0 ? "+" : ""}${r.vwap_slope.toFixed(2)}%` : "n/a";
  return `Grade ${(r.grade || "C").toUpperCase()} — A needs ≥2× RVOL AND rising VWAP (slope ≥0.05%).\nRVOL ${r.rvol.toFixed(1)}× · VWAP slope ${slope}`;
};

function EmptyState({ marketOpen, filtered }: { marketOpen: boolean; filtered: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
        {marketOpen ? <Activity className="h-6 w-6 text-text-faint" /> : <Moon className="h-6 w-6 text-text-faint" />}
      </div>
      {marketOpen ? (
        <>
          <p className="text-text-secondary font-medium">No names match this view</p>
          <p className="text-text-faint text-sm mt-1">{filtered ? "Try a different preset or clear filters." : "The market's quiet — check back shortly."}</p>
        </>
      ) : (
        <>
          <p className="text-text-secondary font-medium">The desk is closed</p>
          <p className="text-text-faint text-sm mt-1">In-play movers refresh when the bell rings — 9:30&nbsp;AM&nbsp;ET, Mon–Fri.</p>
        </>
      )}
    </div>
  );
}

export default function InPlayView() {
  const [preset, setPreset] = useState<InPlayPreset>("any");
  const [hasSetup, setHasSetup] = useState(false);
  const { data, isLoading, isError } = useInPlay(preset, hasSetup);
  const { screenerPreviewRows, isPro } = useFeatureGate();
  const refresh = useRefreshInPlay();
  const navigate = useNavigate();

  const rows = data?.entries ?? [];
  const maxRvol = useMemo(() => Math.max(1, ...rows.map((r) => r.rvol)), [rows]);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const columns: Column<InPlayEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-10", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={inPlayGradeTip(r)} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span><span className="font-bold text-text-primary">{r.symbol}</span>{r.sector && <span className="text-text-faint text-[11px] ml-2 hidden xl:inline">{r.sector}</span>}</span>
    ) },
    { key: "last_price", label: "Price", align: "right", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{px(r.last_price)}</span> },
    { key: "pct_change", label: "% Chg", align: "right", value: (r) => r.pct_change, render: (r) => <Pct v={r.pct_change} /> },
    { key: "rvol", label: "RVOL", align: "right", value: (r) => r.rvol, render: (r) => <RvolCell v={r.rvol} max={maxRvol} /> },
    { key: "vwap_slope", label: "VWAP", align: "right", cls: "hidden lg:table-cell", value: (r) => r.vwap_slope ?? -999, render: (r) => <VwapSlopeCell v={r.vwap_slope} /> },
    { key: "dollar_vol", label: "$ Vol", align: "right", value: (r) => r.dollar_vol, render: (r) => <span className="font-mono text-text-secondary">{compact(r.dollar_vol)}</span> },
    { key: "market_cap", label: "Mkt Cap", align: "right", value: (r) => r.market_cap, render: (r) => <span className="font-mono text-text-secondary">{compact(r.market_cap)}</span> },
    { key: "setup", label: "Setup", align: "left", render: (r) => <SetupBadge e={r} /> },
  ];

  const mobileRow = (e: InPlayEntry) => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-text-faint w-4">{e.rank}</span>
          <GradeBadge grade={e.grade} title={inPlayGradeTip(e)} />
          <span className="font-bold text-text-primary">{e.symbol}</span>
          <Pct v={e.pct_change} />
          <SetupBadge e={e} />
        </div>
        <span className="font-mono text-sm text-text-primary">{px(e.last_price)}</span>
      </div>
      <div className="flex items-center gap-3 mt-1.5 pl-6 text-[11px] text-text-muted font-mono">
        <span className={e.rvol >= 2 ? "text-accent" : ""}>RVOL {e.rvol.toFixed(1)}x</span>
        {e.vwap_slope != null && (
          <span className={e.vwap_slope >= 0.05 ? "text-bullish-text" : e.vwap_slope < 0 ? "text-bearish-text" : ""}>
            VWAP {e.vwap_slope >= 0 ? "+" : ""}{e.vwap_slope.toFixed(2)}%
          </span>
        )}
        <span>{compact(e.dollar_vol)}</span>
        <span>{compact(e.market_cap)} cap</span>
      </div>
    </>
  );

  return (
    <div className="space-y-4">
      {/* Title + status */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" /> Top movers
            <span className="text-text-faint font-normal text-sm">· by relative volume</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">What the whole market is doing on volume right now — not just your watchlist.</p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-text-faint">
          {data?.market_open ? (
            <span className="inline-flex items-center gap-1.5 text-bullish-text"><span className="w-1.5 h-1.5 rounded-full bg-bullish animate-pulse" /> Live</span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><Moon className="h-3 w-3" /> Closed</span>
          )}
          {captured && <span>· {captured.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>}
          {rows.length > 0 && <span>· {rows.length} names</span>}
          {data?.stale && <span className="inline-flex items-center gap-1 text-amber-400"><AlertTriangle className="h-3 w-3" /> delayed</span>}
          {isPro && (
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="ml-1 inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors"
              title="Pull the latest movers now"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
              {refresh.isPending ? "Scanning…" : "Run scan"}
            </button>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-1.5">
          {IN_PLAY_PRESETS.map((p) => (
            <button key={p.id} onClick={() => setPreset(p.id)}
              className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                preset === p.id ? "bg-accent/15 text-accent border-accent/30" : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-primary hover:border-border-default"}`}>
              {p.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer select-none">
          <input type="checkbox" checked={hasSetup} onChange={(e) => setHasSetup(e.target.checked)} className="accent-accent" />
          Has setup
        </label>
      </div>

      <ScreenerTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "rank", dir: "asc" }}
        previewRows={screenerPreviewRows}
        previewLabel="movers"
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the in-play list. Retrying…"
        empty={<EmptyState marketOpen={!!data?.market_open} filtered={preset !== "any" || hasSetup} />}
      />
    </div>
  );
}
