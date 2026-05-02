/** App shell — collapsible nav rail (desktop) + bottom tab bar (mobile).
 *  Collapsed: 48px icon-only. Expanded: icon + text labels.
 *  Auto-collapses below 1280px. State persisted in localStorage.
 */

import { useState, useEffect, useCallback } from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useMarketStatus } from "../api/hooks";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { useFeatureGate } from "../hooks/useFeatureGate";
import {
  LayoutDashboard,
  Crosshair,
  Brain,
  ArrowLeftRight,
  Settings,
  LogOut,
  Sparkles,
  PlayCircle,
  PanelLeftClose,
  PanelLeftOpen,
  FileText,
  Star,
  Activity,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/trading", label: "Trading", icon: Crosshair },
  { to: "/watchlist", label: "Watchlist", icon: Star },
  { to: "/premarket", label: "Premarket", icon: Activity },
  { to: "/copilot", label: "AI CoPilot", icon: Brain },
  { to: "/review", label: "Review", icon: PlayCircle },
  { to: "/track-record", label: "AI Auto-Pilot", icon: Sparkles },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight, badge: "0" },
  { to: "/ai-updates", label: "AI Updates", icon: FileText },
  { to: "/settings", label: "Settings", icon: Settings },
];

const MOBILE_TABS: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/trading", label: "Trade", icon: Crosshair },
  { to: "/copilot", label: "CoPilot", icon: Brain },
  { to: "/review", label: "Review", icon: PlayCircle },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/settings", label: "Settings", icon: Settings },
];

const LS_KEY = "sidebar_collapsed";
const AUTO_COLLAPSE_WIDTH = 1280;

function readCollapsed(): boolean {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v !== null) return v === "true";
  } catch {
    /* SSR / incognito */
  }
  // Default: collapsed if narrow window
  return typeof window !== "undefined" && window.innerWidth < AUTO_COLLAPSE_WIDTH;
}

export default function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { data: market } = useMarketStatus();
  const { isTrial, trialDaysLeft, tier } = useFeatureGate();
  usePushNotifications();

  const [collapsed, setCollapsed] = useState(readCollapsed);

  const persistCollapse = useCallback((val: boolean) => {
    setCollapsed(val);
    try {
      localStorage.setItem(LS_KEY, String(val));
    } catch {
      /* ignore */
    }
  }, []);

  // Auto-collapse on narrow viewports
  useEffect(() => {
    let raf: number;
    const mq = window.matchMedia(`(max-width: ${AUTO_COLLAPSE_WIDTH - 1}px)`);

    function handler(e: MediaQueryListEvent | MediaQueryList) {
      raf = requestAnimationFrame(() => {
        if (e.matches) {
          persistCollapse(true);
        }
      });
    }
    // Check on mount
    handler(mq);

    mq.addEventListener("change", handler);
    return () => {
      mq.removeEventListener("change", handler);
      cancelAnimationFrame(raf);
    };
  }, [persistCollapse]);

  return (
    <div className="flex h-screen bg-surface-0">
      {/* Desktop: collapsible nav rail */}
      <nav
        role="navigation"
        aria-label="Main navigation"
        className={`hidden md:flex flex-col items-center justify-between border-r border-border-subtle bg-surface-0 py-5 shrink-0 transition-all duration-200 ease-in-out ${
          collapsed ? "w-12" : "w-48"
        }`}
      >
        {/* Top: brand + nav icons */}
        <div className={`flex flex-col items-center gap-6 w-full ${collapsed ? "" : ""}`}>
          {/* Brand icon */}
          <div className={`flex items-center gap-2.5 mb-2 ${collapsed ? "justify-center" : "px-4"}`}>
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-glow-accent shrink-0">
              <Crosshair className="h-4 w-4 text-white" />
            </div>
            {!collapsed && (
              <span className="font-display text-sm font-bold text-text-primary whitespace-nowrap overflow-hidden">
                <span className="text-accent">Trade</span>CoPilot
              </span>
            )}
          </div>

          <div className="flex flex-col gap-1 w-full px-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/dashboard"}
                  aria-label={item.label}
                  tabIndex={0}
                  className={({ isActive }) =>
                    `group relative flex items-center ${
                      collapsed ? "justify-center" : "gap-3 px-3"
                    } w-full ${
                      collapsed ? "aspect-square" : "py-2.5"
                    } rounded-xl transition-colors ${
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
                      <span className="relative shrink-0">
                        <Icon className="h-[18px] w-[18px]" />
                        {/* Badge */}
                        {item.badge !== undefined && (
                          <span className="absolute -top-1.5 -right-1.5 min-w-[14px] h-[14px] flex items-center justify-center rounded-full bg-accent text-[9px] font-bold text-white px-0.5 leading-none">
                            {item.badge}
                          </span>
                        )}
                      </span>
                      {!collapsed && (
                        <span className="text-sm font-medium whitespace-nowrap overflow-hidden">
                          {item.label}
                        </span>
                      )}
                      {/* Tooltip (only when collapsed) */}
                      {collapsed && (
                        <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                          {item.label}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              );
            })}
          </div>
        </div>

        {/* Bottom: market status + avatar + logout + collapse toggle */}
        <div className="flex flex-col items-center gap-3 w-full">
          {/* Market status dot */}
          {market && (
            <div className="group relative flex flex-col items-center justify-center gap-0.5">
              <div
                className={`w-2.5 h-2.5 rounded-full ${
                  market.is_open
                    ? "bg-bullish shadow-glow-bullish"
                    : market.is_premarket
                    ? "bg-warning"
                    : "bg-text-faint"
                }`}
              />
              <span className={`text-[8px] font-bold uppercase tracking-wider ${
                market.is_open
                  ? "text-bullish-text"
                  : market.is_premarket
                  ? "text-warning-text"
                  : "text-text-faint"
              }`}>
                {market.is_open ? "Open" : market.is_premarket ? "Pre" : "Off"}
              </span>
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

          <div className="w-8 h-px bg-border-subtle" />

          {/* Collapse / expand toggle */}
          <button
            onClick={() => persistCollapse(!collapsed)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="group relative flex items-center justify-center w-8 h-8 text-text-faint hover:text-text-secondary transition-colors"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
            <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
              {collapsed ? "Expand" : "Collapse"}
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
        <nav role="navigation" aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border-subtle bg-surface-0 pb-[env(safe-area-inset-bottom)] md:hidden">
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
