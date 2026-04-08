/** Analysis history list — shows recent AI analyses with outcome tracking. */

import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import {
  TrendingUp, TrendingDown, Minus, Trophy, XCircle, MinusCircle,
  ChevronDown, Loader2,
} from "lucide-react";

interface AnalysisRecord {
  id: number;
  symbol: string;
  timeframe: string;
  direction: string | null;
  confluence_score: number | null;
  outcome: string | null;
  created_at: string;
}

function useAnalysisHistory() {
  return useQuery({
    queryKey: ["analysis-history"],
    queryFn: async () => {
      const res = await api.get<{ analyses: AnalysisRecord[] }>("/intel/analysis-history");
      return res.analyses ?? [];
    },
    staleTime: 30_000,
  });
}

function useRecordOutcome() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: string }) =>
      api.put(`/intel/analysis/${id}/outcome`, { outcome }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis-history"] }),
  });
}

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

function DirectionIcon({ direction }: { direction: string | null }) {
  if (!direction) return <Minus className="h-3.5 w-3.5 text-text-faint" />;
  const d = direction.toUpperCase();
  if (d === "LONG") return <TrendingUp className="h-3.5 w-3.5 text-bullish-text" />;
  if (d === "SHORT") return <TrendingDown className="h-3.5 w-3.5 text-bearish-text" />;
  return <Minus className="h-3.5 w-3.5 text-text-faint" />;
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const o = outcome.toUpperCase();
  if (o === "WIN") {
    return (
      <span className="inline-flex items-center gap-1 bg-bullish/10 border border-bullish/20 text-bullish-text text-[10px] font-bold px-1.5 py-0.5 rounded">
        <Trophy className="h-2.5 w-2.5" />
        WIN
      </span>
    );
  }
  if (o === "LOSS") {
    return (
      <span className="inline-flex items-center gap-1 bg-bearish/10 border border-bearish/20 text-bearish-text text-[10px] font-bold px-1.5 py-0.5 rounded">
        <XCircle className="h-2.5 w-2.5" />
        LOSS
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 bg-surface-3 border border-border-subtle text-text-faint text-[10px] font-bold px-1.5 py-0.5 rounded">
      <MinusCircle className="h-2.5 w-2.5" />
      SCRATCH
    </span>
  );
}

function OutcomePopover({ analysisId, onClose }: { analysisId: number; onClose: () => void }) {
  const recordOutcome = useRecordOutcome();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  function handleSelect(outcome: string) {
    recordOutcome.mutate({ id: analysisId, outcome }, {
      onSuccess: () => onClose(),
    });
  }

  return (
    <div ref={ref} className="absolute right-0 top-full mt-1 z-20 bg-surface-2 border border-border-subtle rounded-lg shadow-lg p-1.5 flex gap-1">
      {recordOutcome.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin text-text-muted mx-4 my-1" />
      ) : (
        <>
          <button
            onClick={() => handleSelect("WIN")}
            className="text-[10px] font-bold text-bullish-text bg-bullish/10 hover:bg-bullish/20 border border-bullish/20 px-2.5 py-1 rounded transition-colors"
          >
            WIN
          </button>
          <button
            onClick={() => handleSelect("LOSS")}
            className="text-[10px] font-bold text-bearish-text bg-bearish/10 hover:bg-bearish/20 border border-bearish/20 px-2.5 py-1 rounded transition-colors"
          >
            LOSS
          </button>
          <button
            onClick={() => handleSelect("SCRATCH")}
            className="text-[10px] font-bold text-text-faint bg-surface-3 hover:bg-surface-4 border border-border-subtle px-2.5 py-1 rounded transition-colors"
          >
            SCRATCH
          </button>
        </>
      )}
    </div>
  );
}

export default function AnalysisHistory() {
  const { data: history, isLoading } = useAnalysisHistory();
  const [openPopover, setOpenPopover] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Analysis History</h3>
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
        </div>
      </div>
    );
  }

  if (!history || history.length === 0) {
    return (
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Analysis History</h3>
        <p className="text-xs text-text-faint text-center py-4">
          No analyses yet. Select a symbol and timeframe above, then click Analyze Chart.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Analysis History</h3>
      <div className="space-y-1.5">
        {history.map((item) => (
          <div
            key={item.id}
            className="flex items-center gap-3 py-2 px-2.5 rounded-lg hover:bg-surface-2/50 transition-colors"
          >
            {/* Symbol + direction */}
            <DirectionIcon direction={item.direction} />
            <span className="text-xs font-bold text-text-primary w-12 shrink-0">
              {item.symbol}
            </span>
            <span className="text-[10px] text-text-faint w-8 shrink-0">{item.timeframe}</span>

            {/* Direction label */}
            <span className={`text-[10px] font-semibold w-12 shrink-0 ${
              item.direction?.toUpperCase() === "LONG"
                ? "text-bullish-text"
                : item.direction?.toUpperCase() === "SHORT"
                ? "text-bearish-text"
                : "text-text-faint"
            }`}>
              {item.direction?.toUpperCase() || "--"}
            </span>

            {/* Confluence */}
            {item.confluence_score != null && (
              <span className="text-[10px] font-mono text-text-muted w-10 shrink-0">
                {item.confluence_score}/10
              </span>
            )}

            {/* Time */}
            <span className="text-[10px] text-text-faint flex-1 text-right">
              {relativeTime(item.created_at)}
            </span>

            {/* Outcome */}
            <div className="relative w-20 flex justify-end shrink-0">
              {item.outcome ? (
                <OutcomeBadge outcome={item.outcome} />
              ) : (
                <button
                  onClick={() => setOpenPopover(openPopover === item.id ? null : item.id)}
                  className="text-[10px] text-accent hover:text-accent-hover flex items-center gap-0.5 transition-colors"
                >
                  Record
                  <ChevronDown className="h-2.5 w-2.5" />
                </button>
              )}
              {openPopover === item.id && (
                <OutcomePopover
                  analysisId={item.id}
                  onClose={() => setOpenPopover(null)}
                />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
