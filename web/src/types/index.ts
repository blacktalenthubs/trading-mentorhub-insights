/** Shared TypeScript interfaces matching API schemas. */

export interface User {
  id: number;
  email: string;
  display_name: string;
  tier: "free" | "pro";
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
}
