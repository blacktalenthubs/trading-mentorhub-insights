/** App shell — editorial "vault" design.
 *  Rail (nav) on left, topbar with § kicker + ticker strip, viewport below.
 *  Mobile: bottom tab bar.
 */

import { useEffect, useState, useCallback } from "react";
import { NavLink, Outlet, Link, useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useMarketStatus, useLivePrices, useAlertsToday, useScanner } from "../api/hooks";
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
  FileText,
  ChevronLeft,
  ChevronRight,
  Search,
  Bell,
  CreditCard,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badgeQuery?: "alerts" | "scanner";
}

const SIGNAL_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, badgeQuery: "alerts" },
  { to: "/trading", label: "Trading", icon: Crosshair, badgeQuery: "scanner" },
  { to: "/copilot", label: "AI Co-Pilot", icon: Brain },
  { to: "/review", label: "Review", icon: PlayCircle },
  { to: "/ai-updates", label: "AI Updates", icon: FileText },
  { to: "/track-record", label: "AI Auto-Pilot", icon: Sparkles },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
];

const ACCOUNT_NAV: NavItem[] = [
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/billing", label: "Billing", icon: CreditCard },
];

const MOBILE_TABS: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/trading", label: "Trade", icon: Crosshair },
  { to: "/copilot", label: "CoPilot", icon: Brain },
  { to: "/review", label: "Review", icon: PlayCircle },
  { to: "/trades", label: "Trades", icon: ArrowLeftRight },
  { to: "/settings", label: "Settings", icon: Settings },
];

const PAGE_TITLES: Record<string, { kicker: string; title: string }> = {
  "/dashboard": { kicker: "Dashboard · §", title: "Command center" },
  "/trading": { kicker: "Scanner + chart · §", title: "Live trading" },
  "/copilot": { kicker: "AI · §", title: "Co-Pilot" },
  "/review": { kicker: "Review · §", title: "Replay" },
  "/trades": { kicker: "Executed · §", title: "Trade book" },
  "/settings": { kicker: "Account · §", title: "Settings" },
  "/billing": { kicker: "Account · §", title: "Billing" },
  "/track-record": { kicker: "AI Auto-Pilot · §", title: "Track record" },
  "/ai-updates": { kicker: "AI Updates · §", title: "Session report" },
};

const LS_KEY = "sidebar_collapsed";
const AUTO_COLLAPSE_WIDTH = 1280;
const TICKER_SYMBOLS = ["SPY", "QQQ", "IWM", "VIX", "BTC-USD"];

function readCollapsed(): boolean {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v !== null) return v === "true";
  } catch {
    /* SSR / incognito */
  }
  return typeof window !== "undefined" && window.innerWidth < AUTO_COLLAPSE_WIDTH;
}

function getPageMeta(pathname: string): { kicker: string; title: string } {
  const match = Object.entries(PAGE_TITLES).find(([k]) => pathname.startsWith(k));
  return match?.[1] ?? { kicker: "TradeSignal · §", title: "Workspace" };
}

// ═══════════════════════ Rail (nav) ═══════════════════════

function Rail({
  collapsed,
  setCollapsed,
  alertsBadge,
  scannerBadge,
}: {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  alertsBadge: number;
  scannerBadge: number;
}) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const renderLink = (item: NavItem) => {
    const Icon = item.icon;
    const badge =
      item.badgeQuery === "alerts"
        ? alertsBadge
        : item.badgeQuery === "scanner"
        ? scannerBadge
        : 0;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === "/dashboard"}
        aria-label={item.label}
        className={({ isActive }) =>
          `group relative flex items-center ${
            collapsed ? "justify-center px-0" : "gap-3 px-3"
          } py-2 rounded-md text-[13px] font-medium transition-colors ${
            isActive
              ? "bg-surface-2 text-text-primary"
              : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"
          }`
        }
      >
        {({ isActive }) => (
          <>
            {isActive && (
              <span
                className="absolute -left-2 top-1/2 -translate-y-1/2 w-[2px] h-[18px] rounded-r"
                style={{ background: "var(--color-accent)" }}
              />
            )}
            <Icon
              className="h-4 w-4 shrink-0"
              style={isActive ? { color: "var(--color-accent)" } : undefined}
            />
            {!collapsed && (
              <span className="whitespace-nowrap overflow-hidden flex-1">{item.label}</span>
            )}
            {!collapsed && badge > 0 && (
              <span
                className="font-mono text-[9.5px] font-medium px-1.5 py-px rounded-full min-w-[18px] text-center"
                style={
                  item.to === "/dashboard"
                    ? {
                        background: "var(--color-accent-muted)",
                        color: "var(--color-accent-ink)",
                      }
                    : {
                        background: "var(--color-surface-3)",
                        color: "var(--color-text-muted)",
                      }
                }
              >
                {badge}
              </span>
            )}
            {collapsed && (
              <span className="absolute left-full ml-3 px-2 py-1 bg-surface-4 text-xs font-medium text-text-primary rounded border border-border-subtle opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                {item.label}
              </span>
            )}
          </>
        )}
      </NavLink>
    );
  };

  return (
    <aside
      className={`hidden md:flex flex-col bg-surface-1 border-r border-border-subtle shrink-0 transition-[width] duration-200 relative ${
        collapsed ? "w-[60px]" : "w-[212px]"
      }`}
    >
      {/* Brand */}
      <div
        className={`flex items-baseline gap-1.5 border-b border-border-subtle ${
          collapsed ? "justify-center py-4 px-0" : "px-5 py-4"
        }`}
      >
        {!collapsed ? (
          <>
            <span
              className="font-display italic text-[22px] font-medium text-text-primary leading-none"
              style={{ letterSpacing: "-0.02em" }}
            >
              t
            </span>
            <span
              className="w-[5px] h-[5px] rounded-full self-center mb-[3px]"
              style={{ background: "var(--color-accent)" }}
            />
            <span
              className="font-display italic text-[22px] font-medium text-text-primary leading-none -ml-1"
              style={{ letterSpacing: "-0.02em" }}
            >
              ai
            </span>
            <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-text-muted ml-auto">
              /ai
            </span>
          </>
        ) : (
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: "var(--color-accent)" }}
          />
        )}
      </div>

      {/* Collapse toggle — circular, floating on rail edge */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="absolute -right-2.5 top-[68px] w-5 h-5 rounded-full bg-surface-2 border border-border-default flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-3 transition-colors z-20"
      >
        {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
      </button>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3.5 px-2.5 no-scrollbar">
        {!collapsed && (
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-text-faint px-2.5 pb-1.5 pt-3.5">
            Signals
          </div>
        )}
        <div className="flex flex-col gap-0.5">{SIGNAL_NAV.map(renderLink)}</div>
        {!collapsed && (
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-text-faint px-2.5 pb-1.5 pt-3.5">
            Account
          </div>
        )}
        <div className="flex flex-col gap-0.5">{ACCOUNT_NAV.map(renderLink)}</div>
      </nav>

      {/* Foot: user block + logout */}
      <div className="border-t border-border-subtle p-2.5">
        <div
          className={`flex items-center gap-2.5 p-2 rounded-md hover:bg-surface-2 ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center font-mono text-[11px] font-semibold shrink-0"
            style={{
              background: `linear-gradient(135deg, var(--color-accent) 0%, var(--color-purple) 100%)`,
              color: "var(--color-surface-0)",
            }}
          >
            {user?.display_name?.charAt(0)?.toUpperCase() ?? "?"}
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-text-primary truncate">
                  {user?.display_name ?? "—"}
                </div>
                <div
                  className="font-mono text-[9px] uppercase tracking-[0.1em] mt-0.5"
                  style={{ color: "var(--color-accent-ink)" }}
                >
                  {user?.tier ?? "free"}
                </div>
              </div>
              <button
                onClick={logout}
                aria-label="Logout"
                className="text-text-faint hover:text-text-secondary transition-colors p-1"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

// ═══════════════════════ Topbar ═══════════════════════

function MarketStatusText() {
  const { data: market } = useMarketStatus();
  if (!market) {
    return <span className="font-mono text-[10.5px] text-text-secondary">LOADING…</span>;
  }
  const label = market.is_open
    ? "MKT OPEN"
    : market.is_premarket
    ? "PRE-MARKET"
    : "MKT CLOSED";
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  return (
    <span className="font-mono text-[10.5px] text-text-secondary uppercase tracking-wider">
      {label} · {hh}:{mm} ET
    </span>
  );
}

function Topbar({ kicker, title }: { kicker: string; title: string }) {
  const { data: market } = useMarketStatus();
  const { data: pricesResp } = useLivePrices();
  const prices = pricesResp?.prices ?? {};
  const dotClass = market?.is_open
    ? "market-dot"
    : market?.is_premarket
    ? "market-dot pre"
    : "market-dot closed";

  return (
    <div className="h-12 border-b border-border-subtle bg-surface-1 flex items-stretch shrink-0">
      {/* Title block */}
      <div className="flex items-center gap-3 px-4 border-r border-border-subtle min-w-[240px]">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted">
            {kicker}
          </div>
          <div
            className="font-display italic text-[18px] leading-none text-text-primary"
            style={{ letterSpacing: "-0.01em" }}
          >
            {title}
          </div>
        </div>
      </div>

      {/* Ticker strip */}
      <div className="flex-1 min-w-0 border-r border-border-subtle overflow-hidden">
        <div className="flex items-center gap-[18px] h-full px-4 overflow-x-auto no-scrollbar font-mono text-[11px] whitespace-nowrap">
          {TICKER_SYMBOLS.map((sym) => {
            const p = prices[sym];
            const chg = p?.change_pct ?? 0;
            const isUp = chg >= 0;
            return (
              <div key={sym} className="flex items-center gap-1.5 shrink-0">
                <span className="text-text-muted text-[10px] uppercase tracking-[0.08em]">
                  {sym}
                </span>
                <span className="text-text-primary font-medium">
                  {p?.price !== undefined ? p.price.toFixed(2) : "—"}
                </span>
                <span
                  className="font-medium"
                  style={{
                    color: isUp
                      ? "var(--color-bullish-text)"
                      : "var(--color-bearish-text)",
                  }}
                >
                  {isUp ? "+" : ""}
                  {chg.toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Market status */}
      <div className="hidden lg:flex items-center gap-2 px-4 border-r border-border-subtle">
        <span className={dotClass} />
        <MarketStatusText />
      </div>

      {/* Icon buttons */}
      <button
        aria-label="Search"
        className="w-10 border-l border-border-subtle flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
      >
        <Search className="h-4 w-4" />
      </button>
      <button
        aria-label="Notifications"
        className="w-10 border-l border-border-subtle flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors relative"
      >
        <Bell className="h-4 w-4" />
        <span
          className="absolute top-2.5 right-2 w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--color-accent)" }}
        />
      </button>
    </div>
  );
}

// ═══════════════════════ Main layout ═══════════════════════

export default function AppLayout() {
  const { isTrial, trialDaysLeft, tier } = useFeatureGate();
  const location = useLocation();
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

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${AUTO_COLLAPSE_WIDTH - 1}px)`);
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) persistCollapse(true);
    };
    handler(mq);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [persistCollapse]);

  // Badges: today's active alerts count and scanner results count
  const { data: alerts } = useAlertsToday();
  const { data: scanResults } = useScanner();
  const alertsBadge = alerts?.filter((a) => !a.user_action)?.length ?? 0;
  const scannerBadge = scanResults?.length ?? 0;

  const meta = getPageMeta(location.pathname);

  return (
    <div className="flex h-screen bg-surface-0 overflow-hidden">
      <Rail
        collapsed={collapsed}
        setCollapsed={persistCollapse}
        alertsBadge={alertsBadge}
        scannerBadge={scannerBadge}
      />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <Topbar kicker={meta.kicker} title={meta.title} />

        {/* Trial banner */}
        {isTrial && (
          <div
            className="flex items-center justify-center gap-2 px-4 py-1.5 border-b border-border-subtle shrink-0"
            style={{ background: "var(--color-accent-subtle)" }}
          >
            <Sparkles className="h-3.5 w-3.5" style={{ color: "var(--color-accent)" }} />
            <span className="text-xs" style={{ color: "var(--color-accent-ink)" }}>
              Pro trial — {trialDaysLeft} day{trialDaysLeft !== 1 ? "s" : ""} left
            </span>
            <Link
              to="/billing"
              className="text-xs font-semibold underline underline-offset-2 ml-1"
              style={{ color: "var(--color-accent-ink)" }}
            >
              Upgrade now
            </Link>
          </div>
        )}
        {!isTrial && tier === "free" && (
          <div className="flex items-center justify-center gap-2 px-4 py-1.5 bg-surface-2 border-b border-border-subtle shrink-0">
            <span className="text-xs text-text-muted">Free plan — limited features</span>
            <Link
              to="/billing"
              className="text-xs font-semibold underline underline-offset-2"
              style={{ color: "var(--color-accent-ink)" }}
            >
              See plans
            </Link>
          </div>
        )}

        <main className="flex-1 overflow-hidden bg-surface-0 pb-14 md:pb-0 relative">
          <Outlet />
        </main>

        {/* Mobile bottom tab bar */}
        <nav
          role="navigation"
          aria-label="Mobile navigation"
          className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border-subtle bg-surface-1 pb-[env(safe-area-inset-bottom)] md:hidden"
        >
          {MOBILE_TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.to === "/dashboard"}
                className={({ isActive }) =>
                  `flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium tracking-wide transition-colors ${
                    isActive ? "" : "text-text-muted"
                  }`
                }
                style={({ isActive }) =>
                  isActive ? { color: "var(--color-accent-ink)" } : undefined
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
