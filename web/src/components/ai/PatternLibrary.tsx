/** Pattern Library — grid of all trading patterns with difficulty badges. */

const PATTERNS = [
  { key: "pdl_bounce", name: "PDL Bounce", category: "Support", difficulty: "Beginner", desc: "Price tests yesterday's low and holds", icon: "🟢" },
  { key: "pdl_reclaim", name: "PDL Reclaim", category: "Support", difficulty: "Beginner", desc: "Price dips below PDL then recovers", icon: "🟢" },
  { key: "vwap_hold", name: "VWAP Hold", category: "Support", difficulty: "Beginner", desc: "Pullback to VWAP that holds", icon: "🟢" },
  { key: "vwap_reclaim", name: "VWAP Reclaim", category: "Reversal", difficulty: "Intermediate", desc: "Crosses above VWAP — momentum shift", icon: "🔄" },
  { key: "session_low_double_bottom", name: "Double Bottom", category: "Support", difficulty: "Beginner", desc: "Two tests of same low, holds", icon: "🟢" },
  { key: "ma_bounce", name: "MA Bounce", category: "Support", difficulty: "Intermediate", desc: "Bounces off 50/100/200 MA", icon: "🟢" },
  { key: "pdh_breakout", name: "PDH Breakout", category: "Breakout", difficulty: "Intermediate", desc: "Breaks above yesterday's high", icon: "🔵" },
  { key: "pdh_rejection", name: "PDH Rejection", category: "Resistance", difficulty: "Beginner", desc: "Fails at yesterday's high", icon: "🔴" },
  { key: "session_high_double_top", name: "Double Top", category: "Resistance", difficulty: "Intermediate", desc: "Tests session high twice, fails", icon: "🔴" },
  { key: "vwap_loss", name: "VWAP Loss", category: "Reversal", difficulty: "Beginner", desc: "Drops below VWAP — bearish", icon: "🔴" },
  { key: "inside_day_breakout", name: "Inside Day", category: "Breakout", difficulty: "Advanced", desc: "Tight range → expansion", icon: "🔵" },
  { key: "fib_bounce", name: "Fib Bounce", category: "Support", difficulty: "Advanced", desc: "Bounce at 50%/61.8% level", icon: "🟢" },
  { key: "gap_and_go", name: "Gap & Go", category: "Momentum", difficulty: "Advanced", desc: "Gap up + holds VWAP", icon: "🔵" },
  { key: "ema_rejection", name: "EMA Rejection", category: "Resistance", difficulty: "Intermediate", desc: "Rejected at falling EMA", icon: "🔴" },
];

const DIFFICULTY_COLORS: Record<string, string> = {
  Beginner: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  Intermediate: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  Advanced: "bg-purple-500/10 text-purple-400 border-purple-500/20",
};

const CATEGORY_COLORS: Record<string, string> = {
  Support: "text-emerald-400",
  Resistance: "text-red-400",
  Breakout: "text-blue-400",
  Reversal: "text-yellow-400",
  Momentum: "text-purple-400",
};

interface Props {
  onSelect?: (patternKey: string) => void;
}

export default function PatternLibrary({ onSelect }: Props) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-5">
      <h3 className="text-sm font-bold text-text-primary mb-3">Pattern Library</h3>
      <p className="text-xs text-text-muted mb-4">
        Learn to recognize these setups. Click any pattern for a detailed explanation.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {PATTERNS.map((p) => (
          <button
            key={p.key}
            onClick={() => onSelect?.(p.key)}
            className="text-left bg-surface-2/40 border border-border-subtle/60 rounded-lg p-3 hover:border-accent/20 transition-colors"
          >
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-sm">{p.icon}</span>
              <span className="text-[11px] font-bold text-text-primary truncate">{p.name}</span>
            </div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className={`text-[9px] ${CATEGORY_COLORS[p.category] || "text-text-muted"}`}>
                {p.category}
              </span>
              <span className={`text-[8px] font-semibold px-1.5 py-0.5 rounded border ${DIFFICULTY_COLORS[p.difficulty]}`}>
                {p.difficulty}
              </span>
            </div>
            <p className="text-[10px] text-text-muted leading-tight line-clamp-2">{p.desc}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
