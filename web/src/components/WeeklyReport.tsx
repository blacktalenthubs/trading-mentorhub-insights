/** Weekly Report — Performance > Weekly tab.
 *
 *  Pattern leaderboard for the week (Mon-Fri) with two quality columns:
 *    - Avg Vol × — the conviction signal (≥ 2.0× = high)
 *    - Avg VWAP slope % — the trend signal (≥ +0.05% = continuation)
 *    - % above gates — share of fires that pass BOTH vol ≥2.0× AND slope ≥+0.05%
 *
 *  Plus two leaderboards of individual fires:
 *    - Top 10 by volume — the highest-conviction setups of the week
 *    - Bottom 10 by volume — noise still slipping through the gates,
 *      useful for identifying patterns/symbols to tighten
 *
 *  Sortable by every quality column. Week picker: This Week / Last Week /
 *  pick a date.
 */

import { useMemo, useState } from "react";
import { useWeeklyReport, type WeeklyPattern, type WeeklyFire } from "../api/hooks";
import Card from "./ui/Card";
import {
  BarChart3, Loader2, AlertCircle, ArrowUp, ArrowDown,
  ChevronLeft, ChevronRight, CalendarRange,
} from "lucide-react";

type SortKey = "fires" | "vol" | "slope" | "gates" | "worked" | "label";
type SortDir = "asc" | "desc";

/* ── Helpers ─────────────────────────────────────────────────────── */

function fmtDate(iso: string): string {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric",
  });
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", timeZone: "America/Chicago",
  });
}

function volColor(v: number | null): string {
  if (v == null) return "text-text-faint";
  if (v >= 2.0) return "text-bullish-text";
  if (v >= 1.5) return "text-warning-text";
  if (v >= 1.0) return "text-text-secondary";
  return "text-text-faint";
}

function slopeColor(s: number | null): string {
  if (s == null) return "text-text-faint";
  if (s >= 0.05) return "text-bullish-text";
  if (s >= 0) return "text-text-secondary";
  if (s >= -0.30) return "text-warning-text";
  return "text-bearish-text";
}

function gatesColor(pct: number): string {
  if (pct >= 60) return "text-bullish-text";
  if (pct >= 30) return "text-warning-text";
  return "text-bearish-text";
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoOffsetWeeks(iso: string, weeks: number): string {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + weeks * 7);
  return d.toISOString().slice(0, 10);
}

/* ── Sortable header button ──────────────────────────────────────── */

function SortBtn({
  label, active, dir, onClick, align = "right",
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right" | "center";
}) {
  const alignCls = align === "right" ? "justify-end"
    : align === "center" ? "justify-center" : "justify-start";
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 w-full ${alignCls} text-[10px] uppercase tracking-wider font-medium transition-colors ${
        active ? "text-accent" : "text-text-faint hover:text-text-muted"
      }`}
    >
      <span>{label}</span>
      {active && (dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
    </button>
  );
}

/* ── Top/Bottom fires row ───────────────────────────────────────── */

function FireRow({ f, rank }: { f: WeeklyFire; rank: number }) {
  return (
    <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/30 last:border-b-0 items-center text-xs">
      <span className="col-span-1 text-text-faint font-mono">{rank}</span>
      <span className="col-span-2 font-semibold text-text-primary">{f.symbol}</span>
      <span
        className="col-span-3 text-text-secondary truncate cursor-help"
        title={f.description || f.label}
      >
        {f.label}
      </span>
      <span className="col-span-2 font-mono text-text-faint">
        {fmtTime(f.created_at)}
        <span className="text-text-faint/70 ml-1.5">
          {f.created_at && new Date(f.created_at).toLocaleDateString("en-US", { weekday: "short" })}
        </span>
      </span>
      <span className={`col-span-2 text-right font-mono font-semibold ${volColor(f.volume_ratio)}`}>
        {f.volume_ratio != null ? `${f.volume_ratio.toFixed(2)}×` : "—"}
      </span>
      <span className={`col-span-2 text-right font-mono ${slopeColor(f.vwap_slope_pct)}`}>
        {f.vwap_slope_pct != null
          ? `${f.vwap_slope_pct > 0 ? "+" : ""}${f.vwap_slope_pct.toFixed(2)}%`
          : "—"}
      </span>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────────── */

export default function WeeklyReport() {
  const [weekAnchor, setWeekAnchor] = useState<string>(isoToday());
  const { data, isLoading, error } = useWeeklyReport(weekAnchor);
  const [sortKey, setSortKey] = useState<SortKey>("fires");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(k);
      setSortDir(k === "label" ? "asc" : "desc");
    }
  }

  const sortedPatterns = useMemo<WeeklyPattern[]>(() => {
    const items = data?.patterns ?? [];
    const flip = sortDir === "desc" ? -1 : 1;
    const cmp = (a: WeeklyPattern, b: WeeklyPattern): number => {
      switch (sortKey) {
        case "fires":  return ((a.fires) - (b.fires)) * flip;
        case "vol":    return ((a.avg_vol_ratio ?? -Infinity) - (b.avg_vol_ratio ?? -Infinity)) * flip;
        case "slope":  return ((a.avg_vwap_slope_pct ?? -Infinity) - (b.avg_vwap_slope_pct ?? -Infinity)) * flip;
        case "gates":  return ((a.pct_above_gates) - (b.pct_above_gates)) * flip;
        case "worked": return ((a.real_worked_pct ?? -1) - (b.real_worked_pct ?? -1)) * flip;
        case "label":  return a.label.localeCompare(b.label) * flip;
      }
    };
    return [...items].sort(cmp);
  }, [data, sortKey, sortDir]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-12 justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
        <span className="text-sm text-text-muted">Loading weekly report…</span>
      </div>
    );
  }
  if (error) {
    return (
      <Card padding="md">
        <div className="flex items-center gap-2 text-bearish-text">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">Failed to load weekly report.</span>
        </div>
      </Card>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* Week navigator + summary */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setWeekAnchor(isoOffsetWeeks(weekAnchor, -1))}
            className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted transition-colors"
            title="Previous week"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-2 text-sm">
            <CalendarRange className="h-4 w-4 text-accent" />
            <span className="font-semibold text-text-primary">
              {fmtDate(data.week_start)} – {fmtDate(data.week_end)}
            </span>
          </div>
          <button
            onClick={() => setWeekAnchor(isoOffsetWeeks(weekAnchor, 1))}
            className="rounded-md bg-surface-3 hover:bg-surface-4 px-2 py-1.5 text-text-muted transition-colors"
            title="Next week"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          {weekAnchor !== isoToday() && (
            <button
              onClick={() => setWeekAnchor(isoToday())}
              className="text-[11px] text-accent hover:underline ml-2"
            >
              this week
            </button>
          )}
        </div>
        <div className="text-xs text-text-faint">
          {data.total_fires} fires · {data.unique_symbols} symbols
        </div>
      </div>

      {/* Pattern leaderboard */}
      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2 flex items-center gap-2">
          <BarChart3 className="h-3.5 w-3.5 text-accent" />
          Pattern Leaderboard
        </h3>
        <p className="text-xs text-text-faint mb-3">
          Click any column header to sort. "Above gates %" = share of fires that pass both
          volume ≥ 2.0× AND VWAP slope ≥ +0.05% — your v2 quality filter.
        </p>
        {sortedPatterns.length === 0 ? (
          <Card padding="md">
            <p className="text-sm text-text-faint text-center">No alerts fired this week.</p>
          </Card>
        ) : (
          <Card padding="none">
            <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/50 bg-surface-2/30">
              <div className="col-span-3">
                <SortBtn label="Pattern" active={sortKey === "label"} dir={sortDir} onClick={() => toggleSort("label")} align="left" />
              </div>
              <div className="col-span-1">
                <SortBtn label="Fires" active={sortKey === "fires"} dir={sortDir} onClick={() => toggleSort("fires")} />
              </div>
              <div className="col-span-2">
                <SortBtn label="Avg Vol ×" active={sortKey === "vol"} dir={sortDir} onClick={() => toggleSort("vol")} />
              </div>
              <div className="col-span-2">
                <SortBtn label="Avg Slope %" active={sortKey === "slope"} dir={sortDir} onClick={() => toggleSort("slope")} />
              </div>
              <div className="col-span-2">
                <SortBtn label="Above Gates %" active={sortKey === "gates"} dir={sortDir} onClick={() => toggleSort("gates")} />
              </div>
              <div className="col-span-2">
                <SortBtn label="Real Worked %" active={sortKey === "worked"} dir={sortDir} onClick={() => toggleSort("worked")} />
              </div>
            </div>
            {sortedPatterns.map(p => {
              const wp = p.real_worked_pct;
              const wpColor = wp == null ? "text-text-faint"
                : wp >= 60 ? "text-bullish-text"
                : wp >= 40 ? "text-warning-text"
                : "text-bearish-text";
              const wpStr = wp == null
                ? (p.graded === 0 ? "no data" : "—")
                : `${wp.toFixed(0)}%`;
              return (
              <div
                key={p.alert_type}
                className="grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border-subtle/30 last:border-b-0 items-center text-xs"
              >
                <span
                  className="col-span-3 text-text-primary truncate cursor-help"
                  title={p.description || p.label}
                >
                  {p.label}
                </span>
                <span className="col-span-1 text-right font-mono text-text-secondary">{p.fires}</span>
                <span className={`col-span-2 text-right font-mono font-semibold ${volColor(p.avg_vol_ratio)}`}>
                  {p.avg_vol_ratio != null ? `${p.avg_vol_ratio.toFixed(2)}×` : "—"}
                </span>
                <span className={`col-span-2 text-right font-mono font-semibold ${slopeColor(p.avg_vwap_slope_pct)}`}>
                  {p.avg_vwap_slope_pct != null
                    ? `${p.avg_vwap_slope_pct > 0 ? "+" : ""}${p.avg_vwap_slope_pct.toFixed(2)}%`
                    : "—"}
                </span>
                <span className={`col-span-2 text-right font-mono font-semibold ${gatesColor(p.pct_above_gates)}`}>
                  {p.pct_above_gates.toFixed(0)}%
                </span>
                <span
                  className={`col-span-2 text-right font-mono font-semibold ${wpColor}`}
                  title={p.graded ? `${p.graded} fires graded · avg MFE ${p.avg_mfe_r ?? "—"}R` : "No real-outcome data yet — backfill runs after market close"}
                >
                  {wpStr}
                  {p.graded != null && p.graded > 0 && (
                    <span className="text-[9px] font-normal text-text-faint ml-1">n={p.graded}</span>
                  )}
                </span>
              </div>
              );
            })}
          </Card>
        )}
      </div>

      {/* Top / Bottom fires side by side on desktop, stacked on mobile */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h3 className="text-xs font-semibold text-bullish-text uppercase tracking-wider mb-2">
            🔥 Top 10 by Volume
          </h3>
          {data.top_volume.length === 0 ? (
            <Card padding="md"><p className="text-xs text-text-faint">No data.</p></Card>
          ) : (
            <Card padding="none">
              {data.top_volume.map((f, i) => <FireRow key={f.id} f={f} rank={i + 1} />)}
            </Card>
          )}
        </div>
        <div>
          <h3 className="text-xs font-semibold text-warning-text uppercase tracking-wider mb-2">
            ⚠️ Bottom 10 by Volume — noise candidates
          </h3>
          {data.bottom_volume.length === 0 ? (
            <Card padding="md"><p className="text-xs text-text-faint">No data.</p></Card>
          ) : (
            <Card padding="none">
              {data.bottom_volume.map((f, i) => <FireRow key={f.id} f={f} rank={i + 1} />)}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
