/** Conviction screener — analyst-backed long-term uptrends.
 *  Finds mid-cap AI / chips / disruptive-tech names that pair a STRONG analyst
 *  rating with a persistent uptrend above the 50-day MA (the ZETA/NBIS profile).
 *  Output is readable by any user; running a fresh scan is Pro-gated.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gem, RefreshCw, History } from "lucide-react";
import { useConviction, useConvictionHistory, useRefreshConviction } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";
import type { ConvictionEntry } from "./InPlay.types";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

function fmtCap(n: number | null): string {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

/** Analyst consensus → label + color. recommendationMean: 1=Strong Buy … 5=Sell. */
function ratingMeta(rec: number | null) {
  if (rec == null) return { label: "—", cls: "text-text-faint" };
  if (rec <= 1.5) return { label: "Strong Buy", cls: "text-bullish-text" };
  if (rec <= 2.0) return { label: "Buy", cls: "text-bullish-text" };
  if (rec <= 2.5) return { label: "Buy/Hold", cls: "text-amber-400" };
  return { label: "Hold", cls: "text-text-muted" };
}

function AnalystCell({ r }: { r: ConvictionEntry }) {
  const m = ratingMeta(r.rec_mean);
  return (
    <span className="flex flex-col leading-tight" title={r.rec_mean != null ? `Consensus ${r.rec_mean.toFixed(2)} (1=Strong Buy…5=Sell) from ${r.num_analysts ?? "?"} analysts` : "No analyst coverage"}>
      <span className={`text-xs font-semibold ${m.cls}`}>{m.label}</span>
      {r.num_analysts != null && <span className="text-[10px] text-text-faint">{r.num_analysts} analysts</span>}
    </span>
  );
}

/** How persistently price has held above its 50-day MA + the trend structure. */
function TrendCell({ r }: { r: ConvictionEntry }) {
  const strong = r.pct_days_above_50 >= 80;
  return (
    <span className="flex flex-col leading-tight" title="% of the last 60 sessions the close held above the 50-day MA">
      <span className={`text-xs font-mono ${strong ? "text-bullish-text" : "text-text-secondary"}`}>{r.pct_days_above_50.toFixed(0)}%</span>
      {r.ma_stacked && <span className="text-[10px] text-accent">50&gt;200 ↑</span>}
    </span>
  );
}

const THEME_ORDER = ["AI Chips", "Semicap", "AI Software", "AI Infra", "AI Optics", "Disruptive"];

export default function ConvictionPage() {
  const navigate = useNavigate();
  const [runId, setRunId] = useState<number | null>(null);
  const [theme, setTheme] = useState<string>("All");

  const { data, isLoading, isError } = useConviction(runId);
  const history = useConvictionHistory();
  const refresh = useRefreshConviction();
  const { isPro } = useFeatureGate();

  const allRows = data?.entries ?? [];
  const rows = theme === "All" ? allRows : allRows.filter((r) => r.theme === theme);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const themes = useMemo(() => {
    const present = new Set(allRows.map((r) => r.theme));
    return THEME_ORDER.filter((t) => present.has(t));
  }, [allRows]);

  const columns: Column<ConvictionEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-10", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={`Conviction ${r.grade} — score ${r.score}/100 (analyst rating + trend persistence + RS + target upside)`} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2">
        <span className="font-bold text-text-primary">{r.symbol}</span>
        <span className="text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">{r.theme}</span>
      </span>
    ) },
    { key: "price", label: "Price", align: "right", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "cap", label: "Mkt Cap", align: "right", cls: "hidden lg:table-cell", value: (r) => r.market_cap ?? 0, render: (r) => <span className="font-mono text-text-secondary">{fmtCap(r.market_cap)}</span> },
    { key: "analyst", label: "Analyst", align: "left", value: (r) => -(r.rec_mean ?? 9), render: (r) => <AnalystCell r={r} /> },
    { key: "upside", label: "Target ↑", align: "right", cls: "hidden md:table-cell", value: (r) => r.target_upside_pct ?? -999, render: (r) => (
      r.target_upside_pct == null ? <span className="text-text-faint">—</span>
        : <span className={`font-mono ${r.target_upside_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.target_upside_pct >= 0 ? "+" : ""}{r.target_upside_pct.toFixed(0)}%</span>
    ) },
    { key: "trend", label: "Above 50MA", align: "left", cls: "hidden sm:table-cell", value: (r) => r.pct_days_above_50, render: (r) => <TrendCell r={r} /> },
    { key: "rs", label: "RS vs SPY", align: "right", cls: "hidden lg:table-cell", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "ret20", label: "20d", align: "right", cls: "hidden xl:table-cell", value: (r) => r.ret_20d, render: (r) => <span className={`font-mono ${r.ret_20d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.ret_20d >= 0 ? "+" : ""}{r.ret_20d.toFixed(1)}%</span> },
    { key: "score", label: "Score", align: "right", cls: "w-14", value: (r) => r.score, render: (r) => <span className="font-mono font-bold text-text-primary">{r.score}</span> },
  ];

  const mobileRow = (r: ConvictionEntry) => {
    const m = ratingMeta(r.rec_mean);
    return (
      <>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GradeBadge grade={r.grade} />
            <span className="font-bold text-text-primary">{r.symbol}</span>
            <span className="text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">{r.theme}</span>
          </div>
          <span className="font-mono text-sm text-text-primary">{money(r.last_price)}</span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] text-text-muted font-mono">
          <span className={m.cls}>{m.label}{r.num_analysts != null ? ` (${r.num_analysts})` : ""}</span>
          {r.target_upside_pct != null && <span className="text-bullish-text">↑{r.target_upside_pct.toFixed(0)}%</span>}
          <span>{r.pct_days_above_50.toFixed(0)}% &gt;50MA</span>
          <span>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
          <span className="text-text-secondary">score {r.score}</span>
        </div>
      </>
    );
  };

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-2">
            <Gem className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Conviction</h1>
              <p className="text-[11px] text-text-muted">
                Mid-cap AI · chips · disruptive names with strong analyst ratings that trend above the 50-day MA.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs">
            {history.data && history.data.runs.length > 0 && (
              <div className="flex items-center gap-1.5">
                <History className="h-3.5 w-3.5 text-text-muted" />
                <select
                  value={runId ?? ""}
                  onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)}
                  className="bg-surface-1 border border-border-subtle rounded px-2 py-1 text-text-secondary"
                >
                  <option value="">Latest run</option>
                  {history.data.runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {new Date(`${r.captured_at}Z`).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {r.count}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {captured && <span className="text-text-faint">Updated {captured.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
            {isPro && (
              <button
                onClick={() => refresh.mutate()}
                disabled={refresh.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
                {refresh.isPending ? "Scanning…" : "Run scan"}
              </button>
            )}
          </div>
        </div>

        {/* Theme filter */}
        {themes.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {["All", ...themes].map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
                  theme === t
                    ? "bg-accent/15 text-accent border-accent/40"
                    : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-secondary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        )}

        <ScreenerTable<ConvictionEntry>
          rows={rows}
          columns={columns}
          rowKey={(r) => r.symbol}
          onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
          defaultSort={{ key: "score", dir: "desc" }}
          mobileRow={mobileRow}
          isLoading={isLoading}
          isError={isError}
          errorText="Couldn't load the conviction screen."
          empty={
            <div className="px-4 py-10 text-center text-sm text-text-muted">
              No conviction picks in the latest run.
              {isPro && " Tap Run scan to refresh — analyst ratings + 50MA trend over the AI/chips/disruptive universe."}
            </div>
          }
        />

        <p className="text-[11px] text-text-faint leading-relaxed">
          <strong>Score (0–100)</strong> blends analyst rating, mean-target upside, how persistently price holds above the 50-day MA, the 50&gt;200 stack, and relative strength vs SPY. Strong analyst rating + above-50MA are required to appear. Research only — not financial advice; verify the live thesis before acting.
        </p>
      </div>
    </div>
  );
}
