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
  vwap_slope?: number | null;
  grade?: string;
}

export interface InPlaySnapshot {
  captured_at: string | null;
  market_open: boolean;
  stale: boolean;
  top_n: number;
  entries: InPlayEntry[];
}

/* ── Swing screener (daily-bar Trend + MA defense) ── */
export interface SwingEntry {
  rank: number;
  symbol: string;
  last_price: number;
  ret_20d: number;
  rs_vs_spy: number;
  above_ema21: boolean;
  above_ema50: boolean;
  ema_stacked: boolean;
  ma_defense: boolean;
  setup: { pattern: string; entry: number; stop: number; target: number; conviction: string } | null;
  market_cap: number;
  sector?: string | null;
  vol_ratio?: number;
  close_strength?: number;
  grade?: string;
  decision?: string;
  decision_reason?: string;
}

export interface SwingSnapshot {
  id?: number | null;
  captured_at: string | null;
  stale: boolean;
  entries: SwingEntry[];
}

export interface SwingRun {
  id: number;
  captured_at: string;
  count: number;
}

/* ── Conviction screener (analyst-backed long-term uptrends) ── */
export interface ConvictionEntry {
  rank: number;
  symbol: string;
  theme: string;
  last_price: number;
  market_cap: number | null;
  sector: string | null;
  // trend
  above_ma50: boolean;
  above_ma200: boolean;
  ma_stacked: boolean;
  pct_days_above_50: number;   // 0–100
  ma50_slope_up: boolean;
  ret_20d: number;
  rs_vs_spy: number;
  // analyst
  rec_mean: number | null;     // 1=Strong Buy … 5=Sell
  rec_key: string | null;      // "strong_buy" | "buy" | "hold" | ...
  num_analysts: number | null;
  target_mean: number | null;
  target_upside_pct: number | null;
  // composite
  score: number;
  grade: string;
}

export interface ConvictionSnapshot {
  id?: number | null;
  captured_at: string | null;
  stale: boolean;
  entries: ConvictionEntry[];
}

export interface ConvictionRun {
  id: number;
  captured_at: string;
  count: number;
}

/* ── Weekly Stage screener (Weinstein 30-week-MA stage) ── */
export interface WeeklyStageEntry {
  symbol: string;
  stage: number;             // 1=Basing · 2=Advancing · 3=Topping · 4=Declining
  stage_label: string;       // e.g. "Stage 2 · Advancing"
  bucket: "own" | "add" | "watch";
  ma: number;                // 30-week MA
  slope_pct: number;         // 4-week slope of the MA, %
  price: number;             // latest weekly close
  dist_vs_ma_pct: number;    // (price - ma) / ma * 100
}

export interface WeeklyStageSnapshot {
  id?: number | null;
  captured_at: string | null;
  stale: boolean;
  entries: WeeklyStageEntry[];
}

/* ── Growth Leaders (#64-M) — the "Long Term" board ── */
export interface GrowthEntry {
  rank: number;
  symbol: string;
  sector: string | null;
  last_price: number;
  stage2: boolean;
  rs_vs_spy: number;
  pct_off_52wh: number | null;
  accumulation: number | null;
  rev_growth_pct: number | null;
  rev_accelerating: boolean | null;
  eps_growth_pct: number | null;
  gross_margin_pct: number | null;
  consensus: string | null;
  scorecard: Record<string, string>;   // criterion -> "pass" | "fail" | "pending"
  score: number;
  grade: string;
}

export interface GrowthSnapshot {
  id?: number | null;
  captured_at: string | null;
  stale: boolean;
  entries: GrowthEntry[];
}

export interface GrowthRun {
  id: number;
  captured_at: string;
  count: number;
}

// Emerging Leaders (#64-O) — the weekly themed discovery scout.
export interface EmergingEntry {
  rank: number;
  symbol: string;
  sector: string;
  last_price: number;
  stage_turn: boolean;
  fresh_cross: boolean;
  rs_vs_spy: number;
  vol_surge: number | null;
  sector_ret: number | null;
  pct_off_52wh: number | null;
  scorecard: Record<string, string>;   // criterion -> "pass" | "fail" | "pending"
  why: string;
  score: number;
  grade: string;
}

export interface EmergingSnapshot {
  id?: number | null;
  captured_at: string | null;
  stale: boolean;
  entries: EmergingEntry[];
}

export interface EmergingRun {
  id: number;
  captured_at: string;
  count: number;
}

export type InPlayPreset = "any" | "momentum_long" | "pullback" | "breakout" | "short";

export const IN_PLAY_PRESETS: { id: InPlayPreset; label: string }[] = [
  { id: "momentum_long", label: "Momentum Long" },
  { id: "pullback", label: "Pullback" },
  { id: "breakout", label: "Breakout" },
  { id: "short", label: "Short" },
  { id: "any", label: "All" },
];
