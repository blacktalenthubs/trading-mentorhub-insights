/** TierGate — wraps content that requires a minimum tier.
 *
 *  If user has access: renders children normally.
 *  If not: renders children blurred with a lock overlay + upgrade CTA.
 */

import { Link } from "react-router-dom";
import { useFeatureGate } from "../hooks/useFeatureGate";
import { Lock } from "lucide-react";

interface TierGateProps {
  /** Minimum tier required: "pro" or "premium" */
  require: "pro" | "premium";
  /** Human-readable feature name shown in the CTA */
  featureName: string;
  children: React.ReactNode;
  /** Optional: skip gating for first N items (e.g. show 3 alerts, blur rest) */
  bypass?: boolean;
}

export default function TierGate({ require, featureName, children, bypass }: TierGateProps) {
  const { hasAccess } = useFeatureGate();

  if (bypass || hasAccess(require)) {
    return <>{children}</>;
  }

  return (
    <div className="relative">
      <div className="blur-sm pointer-events-none select-none opacity-40">
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-center p-5 bg-surface-2/90 backdrop-blur-sm rounded-xl border border-border-subtle max-w-xs">
          <Lock className="h-8 w-8 mx-auto mb-2 text-amber-400" />
          <p className="text-text-primary font-semibold text-sm">{featureName}</p>
          <p className="text-text-muted text-xs mt-1 mb-3">
            Available on {require === "premium" ? "Premium" : "Pro"} plan
          </p>
          <Link
            to="/billing"
            className="inline-block bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold px-4 py-2 rounded-lg transition-colors"
          >
            Upgrade Now
          </Link>
        </div>
      </div>
    </div>
  );
}


/** UpgradeCTA — inline upgrade prompt without wrapping content. */
export function UpgradeCTA({
  feature,
  requiredTier = "pro",
  compact = false,
}: {
  feature: string;
  requiredTier?: string;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <Link
        to="/billing"
        className="inline-flex items-center gap-1.5 text-amber-400 hover:text-amber-300 text-xs font-medium transition-colors"
      >
        <Lock className="h-3 w-3" />
        Upgrade to {requiredTier === "premium" ? "Premium" : "Pro"}
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
      <Lock className="h-5 w-5 text-amber-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary font-medium">{feature}</p>
        <p className="text-xs text-text-muted">
          {requiredTier === "premium" ? "Premium" : "Pro"} feature
        </p>
      </div>
      <Link
        to="/billing"
        className="shrink-0 bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold px-3 py-1.5 rounded-lg transition-colors"
      >
        Upgrade
      </Link>
    </div>
  );
}
