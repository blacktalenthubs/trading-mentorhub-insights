/** In-Play Volume Screener view (spec 62).
 *  Shows the market-wide, RVOL-ranked, setup-aware shortlist. Lives as a tab
 *  inside Trade Ideas. Reuses the dark terminal tokens from the rest of the app.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, AlertTriangle, Zap, ChevronRight } from "lucide-react";
import { useInPlay } from "../api/hooks";
import { IN_PLAY_PRESETS, type InPlayEntry, type InPlayPreset } from "../pages/InPlay.types";

function compact(n: number): string {
  if (!isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

function Row({ e, onOpen }: { e: InPlayEntry; onOpen: (s: string) => void }) {
  const up = e.pct_change >= 0;
  return (
    <button
      onClick={() => onOpen(e.symbol)}
      className="w-full text-left bg-surface-1 border border-border-subtle rounded-xl px-4 py-3 hover:border-border-default transition-colors"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs text-text-faint w-5 shrink-0">{e.rank}</span>
          <span className="font-bold text-text-primary">{e.symbol}</span>
          <span className={`font-mono text-sm ${up ? "text-bullish-text" : "text-bearish-text"}`}>
            {up ? "+" : ""}{e.pct_change.toFixed(1)}%
          </span>
          {e.setup ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">
              <Zap className="h-3 w-3" />{e.setup.pattern || "Setup"}
            </span>
          ) : (
            <span className="text-[10px] text-text-faint">no setup</span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="font-mono text-sm text-text-primary">${e.last_price.toFixed(2)}</span>
          <ChevronRight className="h-4 w-4 text-text-faint" />
        </div>
      </div>
      <div className="flex items-center gap-3 mt-1.5 pl-7 text-[11px] text-text-muted font-mono">
        <span className="inline-flex items-center gap-1 text-accent">
          <Activity className="h-3 w-3" />RVOL {e.rvol.toFixed(1)}x
        </span>
        <span>{compact(e.dollar_vol)}</span>
        <span>{compact(e.market_cap)} cap</span>
        {e.sector && <span className="text-text-faint truncate">{e.sector}</span>}
      </div>
    </button>
  );
}

export default function InPlayView() {
  // Default to "All" (full ranked list). Momentum Long requires rs_vs_spy, which the
  // live service doesn't compute yet — defaulting to it would show an empty list.
  const [preset, setPreset] = useState<InPlayPreset>("any");
  const [hasSetup, setHasSetup] = useState(false);
  const { data, isLoading, isError } = useInPlay(preset, hasSetup);
  const navigate = useNavigate();

  const openChart = (symbol: string) => navigate(`/trading?symbol=${encodeURIComponent(symbol)}`);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  return (
    <div className="space-y-3">
      {/* Controls + status */}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-1.5">
          {IN_PLAY_PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPreset(p.id)}
              className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                preset === p.id
                  ? "bg-accent/15 text-accent border-accent/30"
                  : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-primary"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-text-muted">
          <input type="checkbox" checked={hasSetup} onChange={(e) => setHasSetup(e.target.checked)} />
          Has setup
        </label>
      </div>

      {/* Market state / staleness */}
      <div className="flex items-center gap-2 text-[11px] text-text-faint">
        {data?.market_open ? (
          <span className="inline-flex items-center gap-1 text-bullish-text">
            <span className="w-1.5 h-1.5 rounded-full bg-bullish animate-pulse" />Live
          </span>
        ) : (
          <span>Market closed — last snapshot</span>
        )}
        {captured && <span>· {captured.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>}
        {data?.stale && (
          <span className="inline-flex items-center gap-1 text-amber-400">
            <AlertTriangle className="h-3 w-3" />data may be delayed
          </span>
        )}
      </div>

      {/* List */}
      {isLoading && <p className="text-sm text-text-muted py-8 text-center">Loading movers…</p>}
      {isError && <p className="text-sm text-bearish-text py-8 text-center">Couldn't load the in-play list.</p>}
      {data && data.entries.length === 0 && (
        <p className="text-sm text-text-muted py-8 text-center">
          No names match right now{preset !== "any" ? " for this preset" : ""}.
        </p>
      )}
      <div className="space-y-2">
        {data?.entries.map((e) => <Row key={e.symbol} e={e} onOpen={openChart} />)}
      </div>
    </div>
  );
}
