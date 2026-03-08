/** Main app shell — sidebar nav + header + content area.
 *  Mobile: sidebar collapsed behind hamburger menu.
 *  Desktop: sidebar always visible.
 */

import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useMarketStatus } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import {
  LayoutDashboard,
  Crosshair,
  BarChart3,
  ArrowLeftRight,
  Trophy,
  History,
  Upload,
  Gem,
  RotateCcw,
  Menu,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import Badge from "./ui/Badge";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/scanner", label: "Scanner", icon: Crosshair },
  { to: "/charts", label: "Charts", icon: BarChart3 },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/scorecard", label: "Scorecard", icon: Trophy },
  { to: "/history", label: "History", icon: History },
  { to: "/import", label: "Import", icon: Upload },
];

const PRO_ITEMS: NavItem[] = [
  { to: "/paper-trading", label: "Paper Trading", icon: Gem },
  { to: "/backtest", label: "Backtest", icon: RotateCcw },
];

function MarketBadge({ market }: { market: { is_open: boolean; is_premarket: boolean } }) {
  if (market.is_open) {
    return (
      <Badge variant="bullish">
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-bullish" />
        MARKET OPEN
      </Badge>
    );
  }
  if (market.is_premarket) {
    return <Badge variant="warning">PRE-MARKET</Badge>;
  }
  return <Badge variant="neutral">CLOSED</Badge>;
}

export default function AppLayout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { data: market } = useMarketStatus();
  const { isPro } = useFeatureGate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function closeSidebar() {
    setSidebarOpen(false);
  }

  function renderNavItem(item: NavItem) {
    const Icon = item.icon;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === "/"}
        onClick={closeSidebar}
        className={({ isActive }) =>
          `group relative flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
            isActive
              ? "bg-surface-3 text-text-primary font-medium"
              : "text-text-muted hover:bg-surface-3/50 hover:text-text-secondary"
          }`
        }
      >
        {({ isActive }) => (
          <>
            {isActive && (
              <span className="absolute inset-y-1 left-0 w-[3px] rounded-r-full bg-accent" />
            )}
            <Icon className="h-4 w-4 shrink-0" />
            {item.label}
          </>
        )}
      </NavLink>
    );
  }

  return (
    <div className="flex h-screen">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={closeSidebar}
        />
      )}

      {/* Sidebar */}
      <nav
        className={`fixed inset-y-0 left-0 z-40 flex w-52 flex-col border-r border-border-subtle bg-surface-2 transition-transform duration-200 md:static md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand header */}
        <div className="border-b border-border-subtle p-4">
          <h1 className="font-display text-lg font-bold tracking-tight text-text-primary">
            <span className="text-accent">Trade</span>Signal
          </h1>
          {market && (
            <div className="mt-2">
              <MarketBadge market={market} />
            </div>
          )}
        </div>

        {/* Nav items */}
        <div className="flex-1 overflow-y-auto py-3">
          {NAV_ITEMS.map(renderNavItem)}

          {isPro && (
            <>
              <div className="mx-4 my-3 border-t border-border-subtle" />
              <p className="px-4 py-1 font-display text-[10px] font-semibold uppercase tracking-widest text-text-faint">
                Pro
              </p>
              {PRO_ITEMS.map(renderNavItem)}
            </>
          )}
        </div>

        {/* User footer */}
        <div className="border-t border-border-subtle p-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-4 font-display text-xs font-semibold text-text-secondary">
              {user?.display_name?.charAt(0)?.toUpperCase() || "?"}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-text-primary">{user?.display_name}</p>
              <p className="truncate text-xs text-text-muted">{user?.email}</p>
            </div>
          </div>
          <div className="mt-2.5 flex items-center justify-between">
            <Badge variant={isPro ? "pro" : "neutral"}>
              {isPro ? "PRO" : "FREE"}
            </Badge>
            <button
              onClick={logout}
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
            >
              <LogOut className="h-3 w-3" />
              Logout
            </button>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="flex items-center gap-3 border-b border-border-subtle bg-surface-2 px-4 py-2.5 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="text-text-muted hover:text-text-primary transition-colors"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-display text-sm font-bold tracking-tight">
            <span className="text-accent">Trade</span>Signal
          </span>
          {market && <MarketBadge market={market} />}
        </header>

        <main className="flex-1 overflow-y-auto bg-surface-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
