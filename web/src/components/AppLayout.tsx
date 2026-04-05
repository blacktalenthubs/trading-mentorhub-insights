/** App shell — 64px icon-only nav rail (desktop) + bottom tab bar (mobile).
 *  Maximizes workspace for the Trading page chart.
 */

import { NavLink, Outlet, Link } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useMarketStatus } from "../api/hooks";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { useFeatureGate } from "../hooks/useFeatureGate";
import {
  LayoutDashboard,
  Crosshair,
  ArrowLeftRight,
  Settings,
  LogOut,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/trading", label: "Trading", icon: Crosshair },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/settings", label: "Settings", icon: Settings },
];

const MOBILE_TABS: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/trading", label: "Trade", icon: Crosshair },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { data: market } = useMarketStatus();
  const { isTrial, trialDaysLeft, tier } = useFeatureGate();
  usePushNotifications();

  return (
    <div className="flex h-screen bg-surface-0">
      {/* Desktop: icon-only nav rail */}
      <nav className="hidden md:flex w-16 flex-col items-center justify-between border-r border-border-subtle bg-surface-0 py-5 shrink-0">
        {/* Top: brand + nav icons */}
        <div className="flex flex-col items-center gap-6 w-full">
          {/* Brand icon */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent mb-2">
            <Crosshair className="h-4 w-4 text-white" />
          </div>

          <div className="flex flex-col gap-1 w-full px-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/dashboard"}
                  className={({ isActive }) =>
                    `group relative flex items-center justify-center w-full aspect-square rounded-xl transition-colors ${
                      isActive
                        ? "bg-surface-3 text-accent"
                        : "text-text-muted hover:text-text-primary hover:bg-surface-2"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span className="absolute left-0 w-[3px] h-1/2 bg-accent rounded-r-full" />
                      )}
                      <Icon className="h-[18px] w-[18px]" />
                      {/* Tooltip */}
                      <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                        {item.label}
                      </span>
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        </div>

        {/* Bottom: market status + avatar + logout */}
        <div className="flex flex-col items-center gap-3 w-full">
          {/* Market status dot */}
          {market && (
            <div className="group relative flex items-center justify-center w-8 h-8">
              <div
                className={`w-2.5 h-2.5 rounded-full ${
                  market.is_open
                    ? "bg-bullish shadow-glow-bullish"
                    : market.is_premarket
                    ? "bg-warning"
                    : "bg-text-faint"
                }`}
              />
              <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                {market.is_open ? "Market Open" : market.is_premarket ? "Pre-Market" : "Closed"}
              </span>
            </div>
          )}

          <div className="w-8 h-px bg-border-subtle" />

          {/* User avatar */}
          <div className="group relative">
            <div className="w-8 h-8 rounded-full bg-surface-4 flex items-center justify-center text-xs font-bold text-text-secondary cursor-pointer border border-border-subtle">
              {user?.display_name?.charAt(0)?.toUpperCase() || "?"}
            </div>
            <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
              {user?.display_name}
            </span>
          </div>

          {/* Logout */}
          <button
            onClick={logout}
            className="group relative flex items-center justify-center w-8 h-8 text-text-faint hover:text-text-secondary transition-colors"
          >
            <LogOut className="h-4 w-4" />
            <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
              Logout
            </span>
          </button>
        </div>
      </nav>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Trial banner */}
        {isTrial && (
          <div className="flex items-center justify-center gap-2 px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 shrink-0">
            <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-xs text-amber-200">
              Pro trial — {trialDaysLeft} day{trialDaysLeft !== 1 ? "s" : ""} left
            </span>
            <Link
              to="/billing"
              className="text-xs font-semibold text-amber-400 hover:text-amber-300 underline underline-offset-2 ml-1"
            >
              Upgrade now
            </Link>
          </div>
        )}
        {/* Free tier nudge (post-trial) */}
        {!isTrial && tier === "free" && (
          <div className="flex items-center justify-center gap-2 px-4 py-1.5 bg-surface-2 border-b border-border-subtle shrink-0">
            <span className="text-xs text-text-muted">
              Free plan — limited features
            </span>
            <Link
              to="/billing"
              className="text-xs font-semibold text-accent hover:text-accent/80 underline underline-offset-2"
            >
              See plans
            </Link>
          </div>
        )}
        <main className="flex-1 overflow-hidden bg-surface-0 pb-14 md:pb-0">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar */}
        <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border-subtle bg-surface-0 pb-[env(safe-area-inset-bottom)] md:hidden">
          {MOBILE_TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.to === "/"}
                className={({ isActive }) =>
                  `flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium tracking-wide transition-colors ${
                    isActive ? "text-accent" : "text-text-muted"
                  }`
                }
              >
                <Icon className="h-5 w-5" />
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
