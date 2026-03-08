/** Feature gate hook — checks user tier for Pro features. */

import { useAuthStore } from "../stores/auth";

export function useFeatureGate() {
  const user = useAuthStore((s) => s.user);
  const tier = user?.tier ?? "free";

  return {
    tier,
    isPro: tier === "pro",
    canAccessAlerts: tier === "pro",
    canAccessBacktest: tier === "pro",
    canAccessPaperTrading: tier === "pro",
    maxWatchlistSize: tier === "pro" ? Infinity : 5,
  };
}
