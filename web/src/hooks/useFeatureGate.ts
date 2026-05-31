/** Feature gate hook — tier checks, trial state, usage limits. */

import { useAuthStore } from "../stores/auth";

const TIER_RANK: Record<string, number> = {
  free: 0,
  pro: 1,
  premium: 2,
  admin: 99,
};

/** Local fallback limits — kept in sync with api/app/tier.py. The backend is the
 *  source of truth (served on the user via /me); this table is only used until
 *  that payload arrives. null = unlimited. */
export const TIER_LIMITS: Record<string, Record<string, number | null | boolean | string>> = {
  free: {
    watchlist_max: 5,
    watchlist_groups_max: 1,
    best_setups_per_day: 1,
    visible_alerts: 5,
    screener_preview_rows: 3,
    alerts_min_grade: "A",
    chart_replay_per_day: 1,
    telegram_alerts: true,
    premarket_brief: false,
    performance_analytics: false,
  },
  pro: {
    watchlist_max: null,
    watchlist_groups_max: null,
    best_setups_per_day: 50,
    visible_alerts: null,
    screener_preview_rows: null,
    alerts_min_grade: null,
    chart_replay_per_day: null,
    telegram_alerts: true,
    premarket_brief: true,
    performance_analytics: true,
  },
  // premium/admin/comp resolve to "pro or better" via the rank fallback below.
};

export function useFeatureGate() {
  const user = useAuthStore((s) => s.user);
  const tier = user?.tier ?? "free";
  const rank = TIER_RANK[tier] ?? 0;
  // Prefer backend-served limits (source of truth); fall back to the local table
  // (pro for any paid/admin tier without an explicit entry).
  const fallback = TIER_LIMITS[tier] ?? (rank >= TIER_RANK.pro ? TIER_LIMITS.pro : TIER_LIMITS.free);
  const limits = (user?.limits && Object.keys(user.limits).length ? user.limits : fallback) as Record<
    string,
    number | null | boolean | string
  >;

  const isPro = rank >= TIER_RANK.pro;
  const isPremium = rank >= TIER_RANK.premium;
  const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

  return {
    tier,
    isPro,
    isPremium,
    isTrial: user?.trial_active ?? false,
    trialDaysLeft: user?.trial_days_left ?? 0,
    limits,
    /** Check if user tier >= required tier */
    hasAccess: (required: string) => rank >= (TIER_RANK[required] ?? 0),
    /** Watchlist max for current tier (Infinity = unlimited) */
    maxWatchlistSize: num(limits.watchlist_max) ?? Infinity,
    /** Visible alerts before blurring (null = unlimited) */
    visibleAlerts: num(limits.visible_alerts),
    /** Screener rows shown before the rest are blurred (null = all) */
    screenerPreviewRows: num(limits.screener_preview_rows),
    /** Minimum alert grade delivered on this tier ("A" on free, null = all) */
    alertsMinGrade:
      typeof limits.alerts_min_grade === "string" ? (limits.alerts_min_grade as string) : null,
  };
}
