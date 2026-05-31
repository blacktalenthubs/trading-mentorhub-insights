/** Swing screener (spec 62 follow-up) — market-wide DAILY-bar setups.
 *  Trend + 21/50 EMA defense, ranked by relative strength. Not market-gated:
 *  daily bars are valid all week (incl. weekends). Uses the shared ScreenerTable.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { TrendingUp, RefreshCw, Zap, Moon, History } from "lucide-react";
import { useSwingScreener, useRefreshSwing, useSwingHistory } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import ScreenerTable, { type Column } from "./ScreenerTable";
import GradeBadge, { GRADE_RANK } from "./GradeBadge";
import type { SwingEntry } from "../pages/InPlay.types";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

/** Why this grade? A = heavy volume AND a strong close (buyers defended into the
 *  close). B = one of the two. C = neither. Shown on hover over the badge. */
const gradeTip = (r: SwingEntry) => {
  const vol = r.vol_ratio != null ? `${r.vol_ratio.toFixed(1)}× volume` : "volume n/a";
  const cs = r.close_strength;
  const close =
    cs != null
      ? `close ${cs >= 0.66 ? "strong" : cs <= 0.33 ? "weak" : "mid"} (${(cs * 100).toFixed(0)}% of range)`
      : "close n/a";
  return `Grade ${(r.grade || "C").toUpperCase()} — A needs ≥2× volume AND a strong close.\n${vol} · ${close}`;
};

function Pct({ v }: { v: number }) {
  const up = v >= 0;
  return <span className={`font-mono ${up ? "text-bullish-text" : "text-bearish-text"}`}>{up ? "+" : ""}{v.toFixed(1)}%</span>;
}

/** Structure quality of the pullback (NOT a confidence score — that's Grade/Action).
 *  "High" = shallow dip to the 20 EMA in a stacked uptrend → shown as "Prime". */
function Conv({ c }: { c: string }) {
  const high = c === "High";
  const cls = high ? "text-bullish-text bg-bullish/10" : "text-amber-400 bg-amber-400/10";
  const label = high ? "Prime" : "Solid";
  const tip = high
    ? "Prime structure — shallow pullback to the 20 EMA in a stacked uptrend (20 > 50 > 200)"
    : "Solid structure — holding a deeper MA (50/200) or trend not fully stacked";
  return <span title={tip} className={`text-[10px] font-bold px-1.5 py-0.5 rounded cursor-help ${cls}`}>{label}</span>;
}

/** One-glance action distilled from Close / Vol / RS. Hover for the reason. */
const DECISION_RANK: Record<string, number> = { Buy: 3, Watch: 2, Avoid: 1 };
function DecisionCell({ d, reason }: { d?: string; reason?: string }) {
  const v = d || "Watch";
  const cls =
    v === "Buy"
      ? "text-bullish-text bg-bullish/10 border-bullish/30"
      : v === "Avoid"
      ? "text-bearish-text bg-bearish/10 border-bearish/30"
      : "text-amber-400 bg-amber-400/10 border-amber-400/30";
  return (
    <span title={reason} className={`text-[10px] font-bold px-2 py-0.5 rounded border ${cls} ${reason ? "cursor-help" : ""}`}>
      {v}
    </span>
  );
}

/** Volume ratio — grade gate 1. ≥2× avg = heavy participation. */
function VolCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-text-faint font-mono">—</span>;
  return <span className={`font-mono ${v >= 2 ? "text-accent" : "text-text-secondary"}`}>{v.toFixed(1)}×</span>;
}

/** Close strength (CLV) — grade gate 2. Where the close sits in today's range:
 *  ≥66% (top third) = buyers defended into the close; ≤33% = closed on the lows. */
function CloseCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-text-faint font-mono">—</span>;
  const pct = Math.round(v * 100);
  const cls = v >= 0.66 ? "text-bullish-text" : v <= 0.33 ? "text-bearish-text" : "text-text-muted";
  return <span className={`font-mono ${cls}`} title={v >= 0.66 ? "strong close" : v <= 0.33 ? "weak close" : "mid"}>{pct}%</span>;
}

export default function SwingScreenerView() {
  const [cap, setCap] = useState<"mega" | "small">("mega");
  const [runId, setRunId] = useState<number | null>(null);  // null = latest live run
  const { data, isLoading, isError } = useSwingScreener(cap, runId);
  const history = useSwingHistory(cap);
  const refresh = useRefreshSwing(cap);
  const { screenerPreviewRows, isPro } = useFeatureGate();
  const navigate = useNavigate();

  const rows = data?.entries ?? [];
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const columns: Column<SwingEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-10", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "decision", label: "Action", align: "left", cls: "w-20", value: (r) => DECISION_RANK[r.decision || "Watch"] ?? 2, render: (r) => <DecisionCell d={r.decision} reason={r.decision_reason} /> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={gradeTip(r)} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span>
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded"><Zap className="h-3 w-3" />{r.setup?.pattern ?? "EMA Defense"}</span></span>
    ) },
    { key: "price", label: "Price", align: "right", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "ret_20d", label: "20d", align: "right", cls: "hidden lg:table-cell", value: (r) => r.ret_20d, render: (r) => <Pct v={r.ret_20d} /> },
    { key: "rs", label: "RS vs SPY", align: "right", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "vol", label: "Vol", align: "right", cls: "hidden lg:table-cell", value: (r) => r.vol_ratio ?? 0, render: (r) => <VolCell v={r.vol_ratio} /> },
    { key: "close", label: "Close", align: "right", cls: "hidden lg:table-cell", value: (r) => r.close_strength ?? 0, render: (r) => <CloseCell v={r.close_strength} /> },
    { key: "entry", label: "Entry", align: "right", render: (r) => <span className="font-mono text-text-primary">{money(r.setup?.entry)}</span> },
    { key: "stop", label: "Stop", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bearish-text">{money(r.setup?.stop)}</span> },
    { key: "target", label: "Target", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bullish-text">{money(r.setup?.target)}</span> },
    { key: "setup_quality", label: "Setup", align: "left", value: (r) => (r.setup?.conviction === "High" ? 2 : r.setup ? 1 : 0), render: (r) => (r.setup ? <Conv c={r.setup.conviction} /> : null) },
  ];

  const mobileRow = (r: SwingEntry) => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><DecisionCell d={r.decision} reason={r.decision_reason} /><GradeBadge grade={r.grade} title={gradeTip(r)} /><span className="font-bold text-text-primary">{r.symbol}</span>{r.setup && <Conv c={r.setup.conviction} />}</div>
        <span className="font-mono text-sm text-text-primary">{money(r.setup?.entry)}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] text-text-muted font-mono">
        <span>20d <Pct v={r.ret_20d} /></span><span>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
        {r.vol_ratio != null && <span className={r.vol_ratio >= 2 ? "text-accent" : ""}>Vol {r.vol_ratio.toFixed(1)}×</span>}
        {r.close_strength != null && <span className={r.close_strength >= 0.66 ? "text-bullish-text" : r.close_strength <= 0.33 ? "text-bearish-text" : ""}>Close {Math.round(r.close_strength * 100)}%</span>}
        <span>S {money(r.setup?.stop)}</span><span>T {money(r.setup?.target)}</span>
      </div>
    </>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-accent" /> Swing setups
            <span className="text-text-faint font-normal text-sm">· closing at a key MA</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">
            {cap === "mega"
              ? "Mega-caps pulling back to and holding the 20 / 50 / 200 EMA — valid all week."
              : "Active small-caps & recent IPOs holding the 20 / 50 EMA (≥ $2, real volume) — higher risk."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-surface-2 rounded-lg p-0.5">
            {([["mega", "Mega Cap"], ["small", "Small Cap"]] as const).map(([id, label]) => (
              <button
                key={id}
                onClick={() => { setCap(id); setRunId(null); }}
                className={`text-xs px-2.5 py-1 rounded-md font-semibold transition-colors ${
                  cap === id ? "bg-surface-4 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {history.data && history.data.runs.length > 1 && (
            <div className="flex items-center gap-1.5">
              <History className="h-3.5 w-3.5 text-text-muted" />
              <select
                value={runId ?? ""}
                onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)}
                className="bg-surface-1 border border-border-subtle rounded px-2 py-1 text-xs text-text-secondary"
              >
                <option value="">Latest run</option>
                {history.data.runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {new Date(`${r.captured_at}Z`).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {r.count} setups
                  </option>
                ))}
              </select>
            </div>
          )}
          <span className="text-[11px] text-text-faint inline-flex items-center gap-1.5">
            {runId ? <>saved run</> : captured ? <>live · {captured.toLocaleDateString([], { month: "short", day: "numeric" })}</> : <><Moon className="h-3 w-3" /> not scanned yet</>}
            {rows.length > 0 && <span>· {rows.length} setups</span>}
          </span>
          {/* On-demand scan is a Pro action; free users get the scheduled snapshot. */}
          {isPro && (
            <button
              onClick={() => { setRunId(null); refresh.mutate(); }}
              disabled={refresh.isPending}
              className="text-xs px-3 py-1.5 rounded-lg bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
              {refresh.isPending ? "Scanning…" : "Run scan"}
            </button>
          )}
        </div>
      </div>

      <ScreenerTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "decision", dir: "desc" }}
        previewRows={screenerPreviewRows}
        previewLabel="swing setups"
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load swing setups."
        empty={
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
              <TrendingUp className="h-6 w-6 text-text-faint" />
            </div>
            <p className="text-text-secondary font-medium">No swing setups qualify right now</p>
            <p className="text-text-faint text-sm mt-1">Run a scan to check the market for trend + EMA-defense setups.</p>
          </div>
        }
      />
    </div>
  );
}
