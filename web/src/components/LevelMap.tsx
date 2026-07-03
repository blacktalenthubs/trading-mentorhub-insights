/** Level Map — the v4.2-inspired key-level ladder for the selected chart symbol.
 *
 *  Renders resistances (above price) → a highlighted NOW row → supports (below),
 *  each with price, signed distance %, and a distance bar. Data from
 *  GET /scanner/levels (PDH/PDL/PWH/PWL/EMA21/EMA50). Read-only.
 */

import { useSymbolLevels, type SymbolLevel } from "../api/hooks";

const SUBLABEL: Record<string, string> = {
  PWH: "Prior-week high",
  PDH: "Prior-day high",
  EMA21: "21-day EMA",
  EMA50: "50-day EMA",
  PDL: "Prior-day low",
  PWL: "Prior-week low",
};

function fmt(n: number): string {
  return n >= 1000
    ? n.toLocaleString("en-US", { maximumFractionDigits: 2 })
    : n.toFixed(2);
}

// bar width scales with |distance|, capped so a far level doesn't peg at 100%.
function barWidth(pct: number): string {
  return `${Math.min(100, Math.max(6, (Math.abs(pct) / 15) * 100))}%`;
}

const GRID = "grid grid-cols-[1fr_66px_50px_38px] gap-2 items-center";

function LevelRow({ l }: { l: SymbolLevel }) {
  const isSup = l.role === "support";
  return (
    <div className={`${GRID} px-1.5 py-1.5 rounded hover:bg-surface-2 transition-colors`}>
      <div className="flex flex-col min-w-0">
        <span className="font-mono text-[12px] font-bold text-text-primary">{l.label}</span>
        <span className="text-[9px] text-text-faint truncate">{SUBLABEL[l.label] ?? ""}</span>
      </div>
      <span className="font-mono text-[12px] font-bold text-right text-text-secondary">{fmt(l.price)}</span>
      <span className={`font-mono text-[11px] text-right ${isSup ? "text-bullish-text" : "text-bearish-text"}`}>
        {l.dist_pct > 0 ? "+" : ""}{l.dist_pct.toFixed(1)}%
      </span>
      <span className="relative h-[5px] rounded-full bg-surface-3 overflow-hidden">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${isSup ? "bg-bullish" : "bg-bearish"}`}
          style={{ width: barWidth(l.dist_pct) }}
        />
      </span>
    </div>
  );
}

export default function LevelMap({ symbol }: { symbol: string | null }) {
  const { data, isLoading, isError } = useSymbolLevels(symbol ?? "");

  const Msg = ({ children }: { children: React.ReactNode }) => (
    <div className="flex-1 flex items-center justify-center p-4">
      <p className="text-xs text-text-faint text-center">{children}</p>
    </div>
  );

  if (!symbol) return <Msg>Pick a symbol to see its levels</Msg>;
  if (isLoading) return <Msg>Loading {symbol} levels…</Msg>;
  if (isError || !data) return <Msg>No level data for {symbol}</Msg>;

  const resistances = data.levels.filter((l) => l.role === "resistance"); // above, high→low
  const supports = data.levels.filter((l) => l.role === "support");       // below, high→low
  const nowMeta = [
    data.atr != null ? `ATR ${data.atr}` : null,
    data.rsi != null ? `RSI ${data.rsi}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2">
      <div className={`${GRID} px-1.5 pb-1.5 font-mono text-[8px] uppercase tracking-wide text-text-faint`}>
        <span>Level</span>
        <span className="text-right">Price</span>
        <span className="text-right">Dist</span>
        <span>Zone</span>
      </div>

      {resistances.map((l) => <LevelRow key={l.label} l={l} />)}

      {/* NOW — the live price, between resistances and supports */}
      <div className={`${GRID} px-1.5 py-2 my-1 rounded-md bg-bullish/10 border border-bullish/30`}>
        <div className="flex flex-col min-w-0">
          <span className="font-mono text-[12px] font-bold text-text-primary">{data.symbol} NOW</span>
          {nowMeta && <span className="text-[9px] text-text-muted">{nowMeta}</span>}
        </div>
        <span className="font-mono text-[12px] font-bold text-right text-bullish-text">{fmt(data.price)}</span>
        <span className="font-mono text-[11px] text-right text-text-faint">—</span>
        <span className="h-[5px] rounded-full bg-bullish/40" />
      </div>

      {supports.map((l) => <LevelRow key={l.label} l={l} />)}

      <p className="mt-3 px-1.5 text-[10px] leading-snug text-text-faint">
        Below price = <span className="text-bullish-text">support</span> (dips buyable) · above =
        {" "}<span className="text-bearish-text">resistance</span> (a break = continuation).
      </p>
    </div>
  );
}
