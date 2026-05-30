/** In-Play Volume Screener types (spec 62) — mirrors api/app/schemas/screener.py */

export interface InPlaySetup {
  pattern: string;
  entry?: number | null;
  stop?: number | null;
  target?: number | null;
  conviction?: string;
  score?: number;
  bias?: string;
}

export interface InPlayRefine {
  above_ema50?: boolean | null;
  above_vwap?: boolean | null;
  rsi?: number | null;
  rs_vs_spy?: number | null;
  atr_pct?: number | null;
  near_20d_high?: boolean | null;
}

export interface InPlayEntry {
  rank: number;
  symbol: string;
  last_price: number;
  pct_change: number;
  rvol: number;
  dollar_vol: number;
  market_cap: number;
  sector?: string | null;
  direction: "long" | "short" | "neutral";
  setup?: InPlaySetup | null;
  refine: InPlayRefine;
}

export interface InPlaySnapshot {
  captured_at: string | null;
  market_open: boolean;
  stale: boolean;
  top_n: number;
  entries: InPlayEntry[];
}

export type InPlayPreset = "any" | "momentum_long" | "pullback" | "breakout" | "short";

export const IN_PLAY_PRESETS: { id: InPlayPreset; label: string }[] = [
  { id: "momentum_long", label: "Momentum Long" },
  { id: "pullback", label: "Pullback" },
  { id: "breakout", label: "Breakout" },
  { id: "short", label: "Short" },
  { id: "any", label: "All" },
];
