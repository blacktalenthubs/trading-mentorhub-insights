import { useState } from "react";
import { useGamePlan } from "../api/hooks";
import type { GamePlanSetup } from "../api/hooks";
import { Target, X, ChevronDown, ChevronUp } from "lucide-react";

function ConfluenceMeter({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-0.5" title={`${score}/3 timeframes aligned`}>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={`w-1.5 h-4 rounded-sm ${
            i <= score
              ? score === 3 ? "bg-bullish" : score === 2 ? "bg-warning" : "bg-text-faint"
              : "bg-surface-3"
          }`}
        />
      ))}
    </div>
  );
}

function SetupRow({ setup, onClick }: { setup: GamePlanSetup; onClick: () => void }) {
  const dirClass = setup.direction === "BUY"
    ? "text-bullish-text bg-bullish/10 border-bullish/20"
    : "text-bearish-text bg-bearish/10 border-bearish/20";

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-3 py-2 hover:bg-surface-2/40 transition-colors rounded-lg text-left"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-text-primary">{setup.symbol}</span>
          <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${dirClass}`}>
            {setup.direction}
          </span>
          <ConfluenceMeter score={setup.confluence_score} />
        </div>
        <div className="text-[10px] text-text-muted mt-0.5 truncate">
          {setup.pattern || setup.support_status}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-xs font-mono text-text-primary">${setup.entry?.toFixed(2)}</div>
        <div className="text-[9px] text-text-faint">
          {setup.rr_ratio ? `${setup.rr_ratio}:1 R:R` : ""}
        </div>
      </div>
      <div className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
        setup.score >= 70 ? "bg-bullish/15 text-bullish-text border-bullish/25"
          : setup.score >= 40 ? "bg-warning/15 text-warning-text border-warning/25"
          : "bg-surface-3 text-text-faint border-border-subtle"
      }`}>
        {setup.score}
      </div>
    </button>
  );
}

export default function GamePlanCard({ onSelectSymbol }: { onSelectSymbol: (sym: string) => void }) {
  const { data: setups, isLoading } = useGamePlan();
  const [dismissed, setDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  if (dismissed || !setups || setups.length === 0) return null;

  return (
    <div className="mx-4 mt-2 mb-1 rounded-lg border border-accent/20 bg-accent/[0.04] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="flex items-center gap-2 text-xs font-semibold text-accent"
        >
          <Target className="h-3.5 w-3.5" />
          Today's Top {setups.length} Setups
          {collapsed ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
        </button>
        <button
          onClick={() => setDismissed(true)}
          className="text-text-faint hover:text-text-muted p-0.5"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {!collapsed && (
        <div className="pb-1">
          {isLoading ? (
            <p className="px-3 py-2 text-xs text-text-faint">Loading setups...</p>
          ) : (
            setups.map((s) => (
              <SetupRow key={s.symbol} setup={s} onClick={() => onSelectSymbol(s.symbol)} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
