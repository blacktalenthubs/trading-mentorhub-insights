/** Shared TypeScript interfaces matching API schemas. */

export interface User {
  id: number;
  email: string;
  display_name: string;
  tier: "free" | "pro" | "premium" | "admin";
  trial_active?: boolean;
  trial_days_left?: number;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
  user: User;
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
  direction: string;
  price: number;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  confidence: string;
  message: string;
  created_at: string;
  session_date: string;
  user_action?: string | null;
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
  regime_bullish: boolean;
  spy_close: number | null;
  spy_ema20: number | null;
  spy_rsi: number | null;
}

export interface SwingCategory {
  symbol: string;
  category: string;
  rsi: number | null;
  session_date: string;
}

export interface SwingTrade {
  id: number;
  symbol: string;
  direction: string;
  alert_type?: string;
  entry_price: number;
  stop_price: number | null;
  target_price: number | null;
  current_price: number | null;
  current_rsi: number | null;
  entry_rsi: number | null;
  stop_type?: string;
  target_type?: string;
  status: string;
  opened_date: string;
  closed_date: string | null;
  exit_price: number | null;
  pnl: number | null;
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
