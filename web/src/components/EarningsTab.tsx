/** Earnings tab inside the Watchlist page — spec 61 Phase 2.
 *
 *  Pulls the user's watchlist symbols and surfaces an at-a-glance
 *  earnings calendar:
 *   - Sortable columns (Days · Symbol · EPS Est · Last Surprise) with
 *     ↑/↓ direction toggles. Default sort: Days ASC.
 *   - Click any row → navigates to /trading?symbol=X so the user can
 *     chart it without two clicks.
 *   - Mobile: stacked card list instead of the dense 12-col grid.
 *   - Outlier surprises (|%| > 100) flagged with "(big beat/miss)" so
 *     INTC-style $0.01-estimate explosions don't dominate the column.
 *   - "Symbols with no calendar data" collapsed at the bottom as a
 *     summary footer rather than a wall of "—" rows.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUpcomingEarnings, type UpcomingEarningsItem } from "../api/hooks";
import Card from "./ui/Card";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import { CalendarDays, AlertCircle, ArrowUp, ArrowDown } from "lucide-react";

type SortKey = "days" | "symbol" | "eps" | "surprise";
type SortDir = "asc" | "desc";

function fmtRelativeAge(iso: string | null): string {
  if (!iso) return "never";
  const diffH = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

interface SurpriseInfo {
  display: string;
  color: string;
  outlierTag: string | null;
}

function surpriseInfo(s: number | null): SurpriseInfo {
  if (s == null) return { display: "—", color: "text-text-faint", outlierTag: null };
  const sign = s > 0 ? "+" : "";
  const display = `${sign}${s.toFixed(1)}%`;
  const color = s > 0 ? "text-bullish-text" : s < 0 ? "text-bearish-text" : "text-text-muted";
  // Outliers — when the estimate is near zero, surprise % explodes. Flag them
  // so a +1971% INTC doesn't look like a stronger signal than a +15% PLTR.
  let outlierTag: string | null = null;
  if (Math.abs(s) > 100) outlierTag = s > 0 ? "(big beat)" : "(big miss)";
  return { display, color, outlierTag };
}

function daysColor(daysUntil: number | null): string {
  if (daysUntil == null) return "text-text-faint";
  if (daysUntil < 0) return "text-text-faint";
  if (daysUntil <= 7) return "text-warning-text font-semibold";
  if (daysUntil <= 14) return "text-text-primary";
  return "text-text-muted";
}

function rowTintClass(daysUntil: number | null): string {
  if (daysUntil != null && daysUntil >= 0 && daysUntil <= 7) return "bg-warning/8";
  if (daysUntil != null && daysUntil < 0) return "opacity-50";
  return "";
}

/* ── Sortable header button ──────────────────────────────────────── */

function SortBtn({
  label, active, dir, onClick, align = "left",
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
      {active && (dir === "asc" ? (
        <ArrowUp className="h-3 w-3" />
      ) : (
        <ArrowDown className="h-3 w-3" />
      ))}
    </button>
  );
}

/* ── Single row (desktop grid) ───────────────────────────────────── */

function DesktopRow({ it, onClick }: { it: UpcomingEarningsItem; onClick: () => void }) {
  const daysCol = daysColor(it.days_until);
  const tint = rowTintClass(it.days_until);
  const surprise = surpriseInfo(it.last_surprise_pct);
  return (
    <button
      onClick={onClick}
      className={`grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border-subtle/30 last:border-b-0 items-center text-xs text-left w-full hover:bg-surface-3/40 transition-colors ${tint}`}
    >
      <span className="col-span-2 font-semibold text-text-primary">{it.symbol}</span>
      <span className={`col-span-1 text-right font-mono ${daysCol}`}>
        {it.days_until == null ? "—" : it.days_until < 0 ? "past" : it.days_until}
      </span>
      <span className="col-span-2 text-text-secondary">{fmtDate(it.next_earnings_date)}</span>
      <span className="col-span-1 text-center text-[10px] font-mono text-text-muted">
        {it.time_of_day || "—"}
      </span>
      <span className="col-span-2 text-right font-mono text-text-secondary">
        {it.eps_estimate != null ? `$${it.eps_estimate.toFixed(2)}` : "—"}
      </span>
      <span className="col-span-2 text-right font-mono">
        <span className={`font-semibold ${surprise.color}`}>{surprise.display}</span>
        {it.last_quarter_label && it.last_surprise_pct != null && (
          <span className="text-[10px] font-normal text-text-faint ml-1">{it.last_quarter_label}</span>
        )}
        {surprise.outlierTag && (
          <span className="text-[9px] font-normal text-text-faint ml-1 italic">{surprise.outlierTag}</span>
        )}
      </span>
      <span className="col-span-2 text-right">
        {it.confirmed ? (
          <span className="text-[10px] font-semibold text-bullish-text">CONFIRMED</span>
        ) : (
          <span className="text-[10px] text-text-faint">estimate</span>
        )}
      </span>
    </button>
  );
}

/* ── Single card (mobile stacked) ────────────────────────────────── */

function MobileCard({ it, onClick }: { it: UpcomingEarningsItem; onClick: () => void }) {
  const daysCol = daysColor(it.days_until);
  const tint = rowTintClass(it.days_until);
  const surprise = surpriseInfo(it.last_surprise_pct);
  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-1.5 p-3 border-b border-border-subtle/30 last:border-b-0 text-left w-full active:bg-surface-3/40 transition-colors ${tint}`}
    >
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-text-primary">{it.symbol}</span>
          {it.confirmed ? (
            <span className="text-[9px] font-semibold text-bullish-text">CONFIRMED</span>
          ) : (
            <span className="text-[9px] text-text-faint">estimate</span>
          )}
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className={`text-base font-mono font-semibold ${daysCol}`}>
            {it.days_until == null ? "—" : it.days_until < 0 ? "past" : `${it.days_until}d`}
          </span>
        </div>
      </div>
      <div className="flex items-center justify-between text-[11px] text-text-muted">
        <span>{fmtDate(it.next_earnings_date)} <span className="text-text-faint">· {it.time_of_day || "TBD"}</span></span>
        <span className="font-mono">
          EPS est {it.eps_estimate != null ? `$${it.eps_estimate.toFixed(2)}` : "—"}
        </span>
      </div>
      {it.last_surprise_pct != null && (
        <div className="text-[11px] font-mono">
          Last Q <span className={`font-semibold ${surprise.color}`}>{surprise.display}</span>
          {it.last_quarter_label && (
            <span className="text-text-faint ml-1">{it.last_quarter_label}</span>
          )}
          {surprise.outlierTag && (
            <span className="text-text-faint ml-1 italic">{surprise.outlierTag}</span>
          )}
        </div>
      )}
    </button>
  );
}

/* ── Main tab ────────────────────────────────────────────────────── */

export default function EarningsTab() {
  const { data, isLoading, error } = useUpcomingEarnings();
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>("days");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [showNoData, setShowNoData] = useState(false);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      // Smart default direction per column: descending makes sense for
      // surprise (biggest beats first) + EPS, ascending for days/symbol.
      setSortDir(key === "surprise" || key === "eps" ? "desc" : "asc");
    }
  }

  function openSymbol(symbol: string) {
    navigate(`/trading?symbol=${encodeURIComponent(symbol)}`);
  }

  const { withDate, noDate, sorted } = useMemo(() => {
    const items = data?.items ?? [];
    const withDate = items.filter(i => i.next_earnings_date);
    const noDate = items.filter(i => !i.next_earnings_date);

    // Sort the with-date set per current sortKey + sortDir.
    const cmp = (a: UpcomingEarningsItem, b: UpcomingEarningsItem): number => {
      const flip = sortDir === "desc" ? -1 : 1;
      const nullsLast = (av: number | null | undefined, bv: number | null | undefined) => {
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return 0;
      };
      switch (sortKey) {
        case "days":     return (nullsLast(a.days_until, b.days_until) || ((a.days_until ?? 0) - (b.days_until ?? 0))) * flip;
        case "eps":      return (nullsLast(a.eps_estimate, b.eps_estimate) || ((a.eps_estimate ?? 0) - (b.eps_estimate ?? 0))) * flip;
        case "surprise": return (nullsLast(a.last_surprise_pct, b.last_surprise_pct) || ((a.last_surprise_pct ?? 0) - (b.last_surprise_pct ?? 0))) * flip;
        case "symbol":   return a.symbol.localeCompare(b.symbol) * flip;
      }
    };
    const sorted = [...withDate].sort(cmp);
    return { withDate, noDate, sorted };
  }, [data, sortKey, sortDir]);

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <div className="flex items-center justify-between">
          <Skeleton w={180} h={12} />
          <Skeleton w={120} h={12} />
        </div>
        <Card padding="none">
          <SkeletonRow count={8} h={42} gap={0} />
        </Card>
      </div>
    );
  }
  if (error) {
    return (
      <Card padding="md">
        <div className="flex items-center gap-2 text-bearish-text">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">Failed to load earnings.</span>
        </div>
      </Card>
    );
  }
  const items = data?.items ?? [];
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <CalendarDays className="h-10 w-10 text-text-faint" />
        <p className="text-text-muted">No watchlist symbols yet</p>
        <p className="text-sm text-text-faint">Add symbols on the Symbols tab to start tracking earnings.</p>
      </div>
    );
  }

  const refreshedIso = data?.last_refreshed_at ?? null;
  const stale = refreshedIso
    ? (Date.now() - new Date(refreshedIso).getTime()) / 3_600_000 > 36
    : false;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-text-faint">
        <span>{withDate.length} upcoming · {noDate.length} no data</span>
        <span className={stale ? "text-warning-text" : ""}>
          Refreshed {fmtRelativeAge(refreshedIso)}{stale && " · may be stale"}
        </span>
      </div>

      {/* Desktop grid table */}
      <Card padding="none" className="hidden md:block">
        <div className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/50 bg-surface-2/30">
          <div className="col-span-2">
            <SortBtn label="Symbol" active={sortKey === "symbol"} dir={sortDir} onClick={() => toggleSort("symbol")} />
          </div>
          <div className="col-span-1">
            <SortBtn label="Days" active={sortKey === "days"} dir={sortDir} onClick={() => toggleSort("days")} align="right" />
          </div>
          <div className="col-span-2 flex items-center text-[10px] uppercase tracking-wider text-text-faint">Date</div>
          <div className="col-span-1 text-center text-[10px] uppercase tracking-wider text-text-faint">When</div>
          <div className="col-span-2">
            <SortBtn label="EPS Est" active={sortKey === "eps"} dir={sortDir} onClick={() => toggleSort("eps")} align="right" />
          </div>
          <div className="col-span-2">
            <SortBtn label="Last Q Surprise" active={sortKey === "surprise"} dir={sortDir} onClick={() => toggleSort("surprise")} align="right" />
          </div>
          <div className="col-span-2 text-right text-[10px] uppercase tracking-wider text-text-faint">Confirmed</div>
        </div>
        {sorted.map(it => (
          <DesktopRow key={it.symbol} it={it} onClick={() => openSymbol(it.symbol)} />
        ))}
      </Card>

      {/* Mobile stacked cards */}
      <Card padding="none" className="md:hidden">
        {/* Compact sort selector */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle/50 bg-surface-2/30 text-[10px]">
          <span className="text-text-faint uppercase tracking-wider">Sort:</span>
          {(["days", "symbol", "eps", "surprise"] as SortKey[]).map(k => (
            <button
              key={k}
              onClick={() => toggleSort(k)}
              className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded transition-colors ${
                sortKey === k ? "bg-accent/15 text-accent" : "text-text-muted"
              }`}
            >
              <span className="capitalize">{k === "eps" ? "EPS" : k}</span>
              {sortKey === k && (sortDir === "asc" ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />)}
            </button>
          ))}
        </div>
        {sorted.map(it => (
          <MobileCard key={it.symbol} it={it} onClick={() => openSymbol(it.symbol)} />
        ))}
      </Card>

      {/* No-data symbols collapsed footer */}
      {noDate.length > 0 && (
        <Card padding="none">
          <button
            onClick={() => setShowNoData(v => !v)}
            className="w-full px-4 py-2 text-[11px] text-left text-text-faint hover:text-text-muted transition-colors"
          >
            {showNoData ? "▾" : "▸"} {noDate.length} symbol{noDate.length === 1 ? "" : "s"} without calendar data
            <span className="text-text-faint/70 ml-1">— typically ETFs, crypto, or symbols outside Finnhub coverage</span>
          </button>
          {showNoData && (
            <div className="px-4 pb-3 flex flex-wrap gap-1.5">
              {noDate.map(it => (
                <button
                  key={it.symbol}
                  onClick={() => openSymbol(it.symbol)}
                  className="text-[11px] font-mono text-text-muted hover:text-text-primary bg-surface-3 hover:bg-surface-4 px-2 py-0.5 rounded transition-colors"
                >
                  {it.symbol}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
