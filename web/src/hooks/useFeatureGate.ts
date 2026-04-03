/** Feature gate hook — checks user tier for Pro features. */

import { useAuthStore } from "../stores/auth";

export function useFeatureGate() {
  const user = useAuthStore((s) => s.user);
  const tier = user?.tier ?? "free";
  const isPro = tier === "pro" || tier === "elite";

  return {
    tier,
    isPro,
    isElite: tier === "elite",
    canAccessAlerts: isPro,
    canAccessBacktest: isPro,
    canAccessPaperTrading: isPro,
    canAccessSwing: isPro,
    canAccessAICoach: isPro,
    maxWatchlistSize: isPro ? Infinity : 5,
  };
}
