/** Shared TypeScript interfaces matching API schemas. */

export type TierLimits = Record<string, number | null | boolean | string>;

export interface User {
  id: number;
  email: string;
  display_name: string;
  tier: "free" | "pro" | "premium" | "admin";
  trial_active?: boolean;
  trial_days_left?: number;
  /** Effective per-tier feature limits, served by the backend (source of truth). */
  limits?: TierLimits;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  user: User;
  refresh_token?: string;
}

export interface SignalResult {
  symbol: string;
  score: number;
  grade: string;
  action_label: string;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  target_kind?: string | null;   // level | rsi | eod (Sub-spec A)
  trade_type?: string | null;    // day | swing (Sub-spec L)
  swing_eligible?: boolean | null;
  rr_ratio: number | null;
  support_status: string;
  pattern: string;
  direction: string;
  near_support: boolean;
  close: number | null;
  prior_day_low: number | null;
  ma20: number | null;
  ma50: number | null;
  prior_high: number | null;
  prior_low: number | null;
  nearest_support: number | null;
  support_label: string;
  distance_to_support: number | null;
  distance_pct: number | null;
  reentry_stop: number | null;
  risk_per_share: number | null;
  bias: string;
  day_range: number | null;
  volume_ratio: number | null;
  ref_day_high: number | null;
  ref_day_low: number | null;
}

export interface Alert {
  id: number;
  symbol: string;
  alert_type: string;
  description?: string | null;       // plain-English explanation per spec 61 follow-up
  direction: string;
  price: number;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  confidence: string;
  score: number;
  confluence_score: number;
  confluence_label: string | null;
  entry_guidance: string | null;
  trade_type?: string | null;        // day | swing | long | gap → the style badge
  message: string;
  narrative?: string | null;         // the AI agent's read — surfaced in Today > Briefing
  created_at: string;
  session_date: string;
  user_action?: string | null;
  outcome?: string | null;          // manual grade — "worked" | "failed" | null
  volume_ratio?: number | null;
  vwap_slope_pct?: number | null;
  grade?: string | null;             // A / B / C — setup conviction badge
  cvd_delta?: number | null;
  cvd_diverging?: number | null;
  suppressed_reason?: string | null;
  exit_price?: number | null;       // user-entered actual close price (Trades page)
  r_multiple?: number | null;       // derived: (exit - entry) / (entry - stop)
}

export interface ScorecardItem {
  alert_type: string;
  worked: number;
  failed: number;
  graded: number;
  win_rate: number;
  group: string;                    // "day" | "swing"
}

// --- Options Trade ---

export interface OptionsTrade {
  id: number;
  symbol: string;
  option_type: string;
  strike: number;
  expiration: string;
  contracts: number;
  premium_per_contract: number;
  exit_premium: number | null;
  pnl: number | null;
  status: string;
  notes: string;
  session_date: string;
}

export interface OptionsTradeStats {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  expectancy: number;
  avg_win: number;
  avg_loss: number;
}

// --- Equity Curve ---

export interface EquityPoint {
  date: string;
  pnl: number;
}

// --- Options Flow ---

export interface OptionsFlowItem {
  symbol: string;
  type: "CALL" | "PUT";
  strike: number;
  expiry: string;
  volume: number;
  open_interest: number;
  volume_oi_ratio: number;
  last_price: number | null;
  implied_vol: number | null;
  sentiment: "BULLISH" | "BEARISH";
}

// --- Swing Trades ---

export interface SpyRegime {
  regime: string;              // "bounce" | "rsi"
  bounce_mode: boolean;        // true when SPY is at/above its 21 EMA
  spy_close: number | null;
  spy_ema21: number | null;
}

export interface SwingTrade {
  id: number;
  symbol: string;
  alert_type: string;          // swing_bounce_ema50 / swing_rsi_30
  setup: string;               // human label, e.g. "EMA 50 bounce"
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  conviction: string | null;
  opened_date: string;
  status: string;              // "active" | "closed"
  closed_date: string | null;
  exit_price: number | null;
  pnl_pct: number | null;
}

// --- Intel / AI ---

export interface WinRateData {
  overall: Record<string, unknown>;
  by_symbol: Record<string, unknown>;
  by_type: Record<string, unknown>;
  by_hour: Record<string, unknown>;
}

export interface SetupAnalysis {
  symbol: string;
  timeframe: string;
  analysis: Record<string, unknown>;
}

export interface MTFContext {
  symbol: string;
  daily: Record<string, unknown>;
  weekly: Record<string, unknown>;
  intraday: Record<string, unknown>;
}

// --- Performance Breakdown ---

export interface PatternBreakdown {
  pattern: string;
  label: string;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
  total_pnl: number;
}

export interface HourBreakdown {
  hour: string;
  label: string;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pnl: number;
}

export interface SymbolBreakdown {
  symbol: string;
  trades: number;
  wins: number;
  win_rate: number;
  total_pnl: number;
}

export interface DayBreakdown {
  day: string;
  trades: number;
  wins: number;
  win_rate: number;
}

export interface PerformanceBreakdown {
  by_pattern: PatternBreakdown[];
  by_hour: HourBreakdown[];
  by_symbol: SymbolBreakdown[];
  by_day: DayBreakdown[];
}

// --- Watchlist Ranking ---

export interface WatchlistRankFactors {
  volume: number;
  level_proximity: number;
  rsi: number;
  trend: number;
}

export interface WatchlistRankItem {
  symbol: string;
  score: number;
  rank: number;
  price: number;
  factors: WatchlistRankFactors;
  nearest_level: string;
  rsi: number | null;
  signal: string;
}

// --- Settings ---

export interface NotificationPrefs {
  telegram_enabled: boolean;
  email_enabled: boolean;
  push_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  // Spec 36 — AI alert filters (optional on PUT; always present on GET)
  min_conviction?: "low" | "medium" | "high";
  wait_alerts_enabled?: boolean;
  alert_directions?: string;  // comma-separated: LONG,SHORT,RESISTANCE,EXIT
  default_portfolio_size?: number;
  default_risk_pct?: number;
  // Spec 61 follow-up — setup grade filter (A/B/C; C = no filter)
  min_alert_grade?: "A" | "B" | "C";
}

// Per-alert-type channel routing.
export type AlertChannel = "telegram" | "email" | "both" | "off";

export interface NotificationRouting {
  ai_update: AlertChannel;
  ai_resistance: AlertChannel;
  ai_long: AlertChannel;
  ai_short: AlertChannel;
  ai_exit: AlertChannel;
  telegram_update_symbols: string;
}

export interface AlertCategoryItem {
  category_id: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface AlertPrefs {
  categories: AlertCategoryItem[];
  min_score: number;
}
