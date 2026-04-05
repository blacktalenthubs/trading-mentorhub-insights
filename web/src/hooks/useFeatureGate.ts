/** Feature gate hook — tier checks, trial state, usage limits. */

import { useAuthStore } from "../stores/auth";

const TIER_RANK: Record<string, number> = {
  free: 0,
  pro: 1,
  premium: 2,
  admin: 99,
};

/** Limits per tier — null = unlimited */
export const TIER_LIMITS: Record<string, Record<string, number | null | boolean>> = {
  free: {
    watchlist_max: 3,
    ai_queries_per_day: 2,
    visible_alerts: 3,
    chart_replay_per_day: 1,
    telegram_alerts: false,
    performance_analytics: false,
    pre_trade_check: false,
    paper_trading: false,
    backtesting: false,
  },
  pro: {
    watchlist_max: 10,
    ai_queries_per_day: 20,
    visible_alerts: null,
    chart_replay_per_day: null,
    telegram_alerts: true,
    performance_analytics: true,
    pre_trade_check: true,
    paper_trading: false,
    backtesting: false,
  },
  premium: {
    watchlist_max: 25,
    ai_queries_per_day: null,
    visible_alerts: null,
    chart_replay_per_day: null,
    telegram_alerts: true,
    performance_analytics: true,
    pre_trade_check: true,
    paper_trading: true,
    backtesting: true,
  },
};

export function useFeatureGate() {
  const user = useAuthStore((s) => s.user);
  const tier = user?.tier ?? "free";
  const rank = TIER_RANK[tier] ?? 0;
  const limits = TIER_LIMITS[tier] ?? TIER_LIMITS.free;

  const isPro = rank >= TIER_RANK.pro;
  const isPremium = rank >= TIER_RANK.premium;

  return {
    tier,
    isPro,
    isPremium,
    isTrial: user?.trial_active ?? false,
    trialDaysLeft: user?.trial_days_left ?? 0,
    limits,
    /** Check if user tier >= required tier */
    hasAccess: (required: string) => rank >= (TIER_RANK[required] ?? 0),
    /** Watchlist max for current tier */
    maxWatchlistSize: (limits.watchlist_max as number) ?? Infinity,
    /** Visible alerts before blurring (null = unlimited) */
    visibleAlerts: limits.visible_alerts as number | null,
  };
}
