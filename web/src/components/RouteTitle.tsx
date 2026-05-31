/** RouteTitle — keeps document.title in sync with the current route so
 *  users with multiple tabs open can tell them apart. Mounted once inside
 *  the BrowserRouter; no per-page wiring required.
 */

import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const BRAND = "BusyTradersDesk";

const STATIC: Record<string, string> = {
  "/": "Spot the setup before it moves",
  "/pricing": "Pricing",
  "/learn": "Learn",
  "/login": "Sign in",
  "/register": "Create account",
  "/reset-password": "Reset password",
  "/onboarding": "Get started",
  "/trading": "Live Charts & Alerts",
  "/trade-ideas": "Trade Ideas",
  "/watchlist": "Watchlist",
  "/premarket": "Pre-market Brief",
  "/performance": "Performance",
  "/settings": "Settings",
  "/billing": "Billing",
  "/admin": "Admin",
  "/track-record": "Track Record",
};

const PREFIX: Array<[RegExp, string]> = [
  [/^\/learn\/patterns\//, "Pattern"],
  [/^\/learn\//, "Learn"],
  [/^\/replay\//, "Alert Replay"],
  [/^\/public\/eod-report/, "Public EOD Report"],
  [/^\/track-record\//, "Track Record"],
];

function titleFor(pathname: string): string {
  const exact = STATIC[pathname];
  if (exact) return exact;
  for (const [re, label] of PREFIX) {
    if (re.test(pathname)) return label;
  }
  return "";
}

export default function RouteTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    const page = titleFor(pathname);
    document.title = page ? `${page} · ${BRAND}` : BRAND;
  }, [pathname]);
  return null;
}
