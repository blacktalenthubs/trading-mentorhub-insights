/** Dashboard — command center, vault aesthetic.
 *  Main: DateHero → KpiRow → §01 PrioritySignals → §02 SignalFeed → §03 Positions
 *  Sidebar: Regime · AI briefing · Game plan · Watchlist
 */

import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  useMarketStatus,
  useLivePrices,
  useAlertsToday,
  useActiveEntries,
  useSectorRotation,
  useSessionSummary,
  useMonthlyStats,
  useOpenTrades,
  useRealTradeStats,
  useWatchlist,
  useAckAlert,
} from "../api/hooks";
import { useAuthStore } from "../stores/auth";
import Spark, { seededSpark } from "../components/ui/Spark";
import type { Alert } from "../types";

// ────────────────────────────────────────────────────────────────
// helpers
// ────────────────────────────────────────────────────────────────

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "morning";
  if (h < 17) return "afternoon";
  return "evening";
}

function firstName(displayName?: string | null): string {
  if (!displayName) return "trader";
  const n = displayName.trim().split(/\s+/)[0];
  return n.charAt(0).toUpperCase() + n.slice(1).toLowerCase();
}

function formatDateToday(): string {
  return new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, "0")}:${String(
      d.getMinutes(),
    ).padStart(2, "0")}`;
  } catch {
    return "—";
  }
}

function alertDirection(a: Alert): "long" | "short" | "exit" {
  const d = (a.direction || "").toLowerCase();
  if (d.includes("short") || d.includes("sell")) return "short";
  if (
    d.includes("exit") ||
    d.includes("trim") ||
    a.alert_type?.toLowerCase().includes("target")
  )
    return "exit";
  return "long";
}

function setupTitle(a: Alert): string {
  return (
    a.alert_type?.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) ??
    "Signal"
  );
}

function convictionFromScore(score: number): number {
  if (score >= 85) return 4;
  if (score >= 70) return 3;
  if (score >= 55) return 2;
  if (score > 0) return 1;
  return 0;
}

// ────────────────────────────────────────────────────────────────
// Date hero
// ────────────────────────────────────────────────────────────────

function DateHero() {
  const user = useAuthStore((s) => s.user);
  const { data: summary } = useSessionSummary();
  const { data: stats } = useRealTradeStats();
  const { data: sectors } = useSectorRotation();

  const tradingDay = 412; // TODO: derive from first session date

  const marketLine = useMemo(() => {
    if (!sectors || sectors.length === 0) {
      return "Market scanning… Favor setups you trust; protect the day's baseline.";
    }
    const inflow = sectors.filter((s) => s.flow === "INFLOW").length;
    const pct = inflow / sectors.length;
    if (pct >= 0.6) {
      return "Market is constructive — trend intact, breadth thickening. Favor continuation setups; avoid chasing late entries.";
    }
    if (pct <= 0.35) {
      return "Market is under distribution — breadth thinning, risk compressed. Trim into strength; wait for cleaner bases.";
    }
    return "Market is mixed — rotation active, no clear leader. Be selective; trust only highest-conviction setups.";
  }, [sectors]);

  const sessionPnl = summary
    ? summary.target_1_hits * 100 +
      summary.target_2_hits * 200 -
      summary.stopped_out * 150
    : 0;
  const equity = (stats?.total_pnl ?? 0) + 100000; // TODO: real equity endpoint

  return (
    <div className="px-8 pt-7 pb-6 border-b border-border-subtle relative">
      <div className="kicker mb-2.5">
        Session · Trading day {tradingDay} · {formatDateToday()}
      </div>
      <h1
        className="serif-display text-text-primary leading-none mb-1.5"
        style={{ fontSize: "44px" }}
      >
        Good {greeting()}, <em>{firstName(user?.display_name)}.</em>
      </h1>
      <p
        className="font-serif italic text-text-secondary"
        style={{
          fontSize: "15px",
          maxWidth: "56ch",
          textWrap: "pretty" as never,
        }}
      >
        {marketLine}
      </p>

      {/* Absolute-positioned meta, top-right */}
      <div className="absolute top-7 right-8 flex gap-6 text-right">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-text-muted mb-1">
            Session P&amp;L
          </div>
          <div
            className="font-mono text-[15px] font-medium"
            style={{
              color:
                sessionPnl >= 0
                  ? "var(--color-bullish-text)"
                  : "var(--color-bearish-text)",
            }}
          >
            {sessionPnl >= 0 ? "+" : "−"}${Math.abs(sessionPnl).toFixed(0)}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-text-muted mb-1">
            Equity
          </div>
          <div className="font-mono text-[15px] font-medium text-text-primary">
            ${equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// KPI row
// ────────────────────────────────────────────────────────────────

function Kpi({
  label,
  value,
  foot,
  spark,
  tone,
}: {
  label: string;
  value: string;
  foot: React.ReactNode;
  spark: number[];
  tone?: "up" | "down";
}) {
  const valueColor =
    tone === "up"
      ? "var(--color-bullish-text)"
      : tone === "down"
      ? "var(--color-bearish-text)"
      : "var(--color-text-primary)";

  return (
    <div className="px-5 py-4 border-r border-border-subtle relative last:border-r-0">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted mb-2">
        {label}
      </div>
      <div
        className="font-mono font-medium leading-none"
        style={{
          fontSize: "22px",
          color: valueColor,
          letterSpacing: "-0.01em",
        }}
      >
        {value}
      </div>
      <div className="font-mono text-[10px] text-text-muted mt-1.5 flex items-center gap-1.5">
        {foot}
      </div>
      <div className="absolute right-3 bottom-3 opacity-60">
        <Spark data={spark} up={tone !== "down"} width={52} height={18} />
      </div>
    </div>
  );
}

function KpiRow() {
  const { data: summary } = useSessionSummary();
  const { data: stats } = useRealTradeStats();
  const { data: monthly } = useMonthlyStats();
  const { data: trades } = useOpenTrades();
  const { data: sectors } = useSectorRotation();

  const signalsToday = summary?.total_alerts ?? 0;
  const winRate = stats?.win_rate ? Math.round(stats.win_rate * 100) : 0;
  const openPnl = (trades ?? []).reduce((acc, t) => acc + (t.pnl ?? 0), 0);
  const realized30 =
    (monthly ?? []).slice(0, 1).reduce((acc, m) => acc + m.total_pnl, 0) || 0;
  const conviction = sectors
    ? Math.round(
        (sectors.filter((s) => s.flow === "INFLOW").length /
          Math.max(sectors.length, 1)) *
          100,
      )
    : 0;

  return (
    <div
      className="grid border-b border-border-subtle"
      style={{ gridTemplateColumns: "repeat(5, 1fr)" }}
    >
      <Kpi
        label="Signals today"
        value={String(signalsToday)}
        foot={<span style={{ color: "var(--color-bullish)" }}>▲ live</span>}
        spark={seededSpark("signals", 20, 1)}
      />
      <Kpi
        label="Win rate (all time)"
        value={`${winRate}%`}
        tone={winRate >= 55 ? "up" : undefined}
        foot={<>{stats?.total_trades ?? 0} trades</>}
        spark={seededSpark("winrate", 20, winRate >= 55 ? 1 : -1)}
      />
      <Kpi
        label="Open P&L"
        value={`${openPnl >= 0 ? "+" : "−"}$${Math.abs(openPnl).toFixed(0)}`}
        tone={openPnl >= 0 ? "up" : "down"}
        foot={<>{trades?.length ?? 0} open</>}
        spark={seededSpark("openpnl", 20, openPnl >= 0 ? 1 : -1)}
      />
      <Kpi
        label="Realized (30d)"
        value={`${realized30 >= 0 ? "+" : "−"}$${Math.abs(realized30).toFixed(0)}`}
        tone={realized30 >= 0 ? "up" : "down"}
        foot={<>this month</>}
        spark={seededSpark("realized", 20, realized30 >= 0 ? 1 : -1)}
      />
      <Kpi
        label="Conviction idx"
        value={String(conviction)}
        tone={conviction >= 55 ? "up" : undefined}
        foot={
          <>
            {conviction >= 60
              ? "Elevated · favor size"
              : conviction >= 40
              ? "Neutral"
              : "Defensive"}
          </>
        }
        spark={seededSpark("conviction", 20, 0)}
      />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// §01 Priority signals
// ────────────────────────────────────────────────────────────────

function LevelBox({
  label,
  value,
  tone,
  literal = false,
}: {
  label: string;
  value: number | string | null;
  tone?: "stop" | "target" | "rr";
  literal?: boolean;
}) {
  const color =
    tone === "stop"
      ? "var(--color-bearish-text)"
      : tone === "target"
      ? "var(--color-bullish-text)"
      : tone === "rr"
      ? "var(--color-accent-ink)"
      : "var(--color-text-primary)";
  const display =
    value === null || value === undefined
      ? "—"
      : literal
      ? `${value}R`
      : `$${Number(value).toFixed(2)}`;
  return (
    <div
      className="rounded border border-border-subtle px-2.5 py-2"
      style={{ background: "var(--color-surface-0)" }}
    >
      <div className="font-mono text-[8.5px] uppercase tracking-[0.12em] text-text-muted mb-1">
        {label}
      </div>
      <div
        className="font-mono font-medium"
        style={{ fontSize: "13px", color, letterSpacing: "-0.01em" }}
      >
        {display}
      </div>
    </div>
  );
}

function PrioritySignalCard({
  alert,
  onOpenChart,
  onTakeAction,
}: {
  alert: Alert;
  onOpenChart: (sym: string) => void;
  onTakeAction: (id: number, action: "took" | "skipped") => void;
}) {
  const dir = alertDirection(alert);
  const isBuy = dir === "long";
  const conv = convictionFromScore(alert.score);
  const rr =
    alert.entry && alert.stop && alert.target_1
      ? ((alert.target_1 - alert.entry) /
          Math.abs(alert.entry - alert.stop)).toFixed(1)
      : "—";
  const stripe = isBuy
    ? "var(--color-bullish)"
    : dir === "short"
    ? "var(--color-bearish)"
    : "var(--color-warning)";
  const quote =
    alert.entry_guidance ??
    alert.message ??
    `${alert.symbol} — ${setupTitle(alert)} setup triggered. Watch the level.`;

  return (
    <div
      className="relative rounded-lg overflow-hidden border border-border-subtle bg-surface-1 transition-all hover:border-border-default"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <span
        className="absolute left-0 top-0 bottom-0 w-[2px]"
        style={{ background: stripe }}
      />
      <div className="flex items-center gap-2.5 pl-4 pr-4 pt-3.5 pb-2.5 flex-wrap">
        <span
          className="font-mono font-semibold text-text-primary"
          style={{ fontSize: "16px", letterSpacing: "-0.01em" }}
        >
          {alert.symbol}
        </span>
        <span className={`dir-pill ${dir}`}>
          {dir === "long" ? "LONG" : dir === "short" ? "SHORT" : "EXIT"}
        </span>
        <span
          className="font-serif italic text-text-secondary flex-1"
          style={{ fontSize: "12px" }}
        >
          {setupTitle(alert)}
        </span>
        <span className="font-mono text-[10px] text-text-muted">
          {formatTime(alert.created_at)}
        </span>
        <span
          className="flex items-center gap-1 px-2 py-0.5 rounded font-mono text-[10px] font-semibold"
          style={{
            background: "var(--color-accent-muted)",
            color: "var(--color-accent-ink)",
          }}
        >
          {Array.from({ length: 4 }).map((_, i) => (
            <span
              key={i}
              className={`conv-dot ${i < conv ? "filled" : "empty"}`}
            />
          ))}
          <span className="ml-1">{conv}/4</span>
        </span>
      </div>

      <div className="px-4 pb-3.5">
        <div
          className="font-serif italic text-text-secondary rounded-md p-3 mb-3"
          style={{
            fontSize: "13.5px",
            lineHeight: 1.5,
            background: "var(--color-surface-0)",
            borderLeft: "2px solid var(--color-accent)",
            textWrap: "pretty" as never,
          }}
        >
          "{quote}"
        </div>

        <div className="grid grid-cols-4 gap-2 mb-3">
          <LevelBox label="Entry" value={alert.entry} />
          <LevelBox label="Stop" value={alert.stop} tone="stop" />
          <LevelBox label="Target" value={alert.target_1} tone="target" />
          <LevelBox
            label="R / R"
            value={rr === "—" ? null : rr}
            tone="rr"
            literal
          />
        </div>

        <div className="flex gap-2 items-center">
          <button
            onClick={() => onTakeAction(alert.id, "took")}
            disabled={alert.user_action === "took"}
            className="px-3.5 py-2 rounded-md font-medium text-[12px] transition-colors disabled:opacity-60"
            style={{
              background: "var(--color-accent)",
              color: "var(--color-surface-0)",
            }}
          >
            {alert.user_action === "took" ? "Taken ✓" : "Took it"}
          </button>
          <button
            onClick={() => onTakeAction(alert.id, "skipped")}
            disabled={alert.user_action === "skipped"}
            className="px-3.5 py-2 rounded-md font-medium text-[12px] text-text-secondary border border-border-subtle hover:bg-surface-2 hover:text-text-primary transition-colors disabled:opacity-60"
          >
            {alert.user_action === "skipped" ? "Skipped" : "Skip"}
          </button>
          <button
            onClick={() => onOpenChart(alert.symbol)}
            className="ml-auto text-[11px] px-2.5 py-1.5 rounded text-text-secondary border border-border-subtle hover:bg-surface-2 hover:text-text-primary"
          >
            Open chart →
          </button>
        </div>
      </div>
    </div>
  );
}

function PrioritySignals({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: alerts } = useAlertsToday();
  const { mutate: ack } = useAckAlert();

  const top = useMemo(() => {
    if (!alerts || alerts.length === 0) return [] as Alert[];
    return [...alerts]
      .filter((a) => !a.user_action)
      .sort((a, b) => b.score - a.score)
      .slice(0, 2);
  }, [alerts]);

  return (
    <div className="px-8 py-6 border-b border-border-subtle">
      <div className="flex items-baseline gap-3.5 mb-4">
        <span className="sect-no">§ 01</span>
        <h2
          className="serif-display italic text-text-primary"
          style={{ fontSize: "22px" }}
        >
          Priority signals
        </h2>
        <div className="flex-1 h-px bg-border-subtle" />
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          {top.length > 0 ? `${top.length} live` : "nothing live"}
        </span>
      </div>

      {top.length === 0 ? (
        <div className="rounded-lg border border-border-subtle bg-surface-1 py-12 text-center">
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
            waiting for signals · market quiet
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {top.map((a) => (
            <PrioritySignalCard
              key={a.id}
              alert={a}
              onOpenChart={onOpenChart}
              onTakeAction={(id, action) => ack({ id, action })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// §02 Signal feed table
// ────────────────────────────────────────────────────────────────

function SignalFeed({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: alerts } = useAlertsToday();
  const rows = (alerts ?? []).slice(0, 10);

  return (
    <div className="px-8 py-6 border-b border-border-subtle">
      <div className="flex items-baseline gap-3.5 mb-4">
        <span className="sect-no">§ 02</span>
        <h2
          className="serif-display italic text-text-primary"
          style={{ fontSize: "22px" }}
        >
          Today's feed
        </h2>
        <div className="flex-1 h-px bg-border-subtle" />
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          {rows.length} of {alerts?.length ?? 0}
        </span>
      </div>
      <div
        className="rounded-lg overflow-hidden border border-border-subtle"
        style={{ background: "var(--color-surface-1)" }}
      >
        <table
          className="w-full font-mono"
          style={{ fontSize: "12px", borderCollapse: "collapse" }}
        >
          <thead>
            <tr>
              {[
                "Time",
                "Symbol",
                "Dir",
                "Pattern",
                "Price",
                "Chg%",
                "Trend",
                "R:R",
                "Conv",
                "",
              ].map((h, i) => (
                <th
                  key={i}
                  className="px-3.5 py-2.5 font-medium font-mono uppercase tracking-[0.14em] text-text-muted border-b border-border-subtle"
                  style={{
                    fontSize: "9px",
                    textAlign: ["Price", "Chg%", "R:R"].includes(h)
                      ? "right"
                      : "left",
                    background: "var(--color-surface-1)",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={10}
                  className="text-center py-8 text-text-muted font-mono text-[11px] uppercase tracking-[0.14em]"
                >
                  no signals yet today
                </td>
              </tr>
            )}
            {rows.map((a, i) => {
              const dir = alertDirection(a);
              const conv = convictionFromScore(a.score);
              const chg =
                a.entry && a.price
                  ? ((a.price - a.entry) / a.entry) * 100
                  : 0;
              const rr =
                a.entry && a.stop && a.target_1
                  ? ((a.target_1 - a.entry) /
                      Math.abs(a.entry - a.stop)).toFixed(1)
                  : null;
              const pulse = i < 2;
              return (
                <tr
                  key={a.id}
                  onClick={() => onOpenChart(a.symbol)}
                  className="cursor-pointer transition-colors hover:bg-surface-2"
                >
                  <td className="px-3.5 py-3 border-b border-border-subtle text-text-secondary">
                    <span className={pulse ? "feed-pulse" : ""}>
                      {formatTime(a.created_at)}
                    </span>
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle font-semibold text-text-primary">
                    {a.symbol}
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle">
                    <span className={`dir-pill ${dir}`}>
                      {dir === "long"
                        ? "LONG"
                        : dir === "short"
                        ? "SHORT"
                        : "EXIT"}
                    </span>
                  </td>
                  <td
                    className="px-3.5 py-3 border-b border-border-subtle text-text-secondary"
                    style={{
                      fontFamily: "var(--font-serif)",
                      fontStyle: "italic",
                      fontSize: "12.5px",
                    }}
                  >
                    {setupTitle(a)}
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle text-right text-text-primary font-medium">
                    ${a.price.toFixed(2)}
                  </td>
                  <td
                    className="px-3.5 py-3 border-b border-border-subtle text-right font-medium"
                    style={{
                      color:
                        chg >= 0
                          ? "var(--color-bullish-text)"
                          : "var(--color-bearish-text)",
                    }}
                  >
                    {chg >= 0 ? "+" : ""}
                    {chg.toFixed(2)}%
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle">
                    <Spark
                      data={seededSpark(
                        `${a.symbol}-${a.id}`,
                        20,
                        chg >= 0 ? 1 : -1,
                      )}
                      up={chg >= 0}
                    />
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle text-right text-text-primary">
                    {rr ? `${rr}R` : "—"}
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle">
                    {conv > 0 && (
                      <span className="inline-flex gap-0.5">
                        {Array.from({ length: 4 }).map((_, k) => (
                          <span
                            key={k}
                            className="w-[5px] h-[5px] rounded-full inline-block"
                            style={{
                              background:
                                k < conv
                                  ? "var(--color-accent-ink)"
                                  : "var(--color-border-default)",
                            }}
                          />
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="px-3.5 py-3 border-b border-border-subtle">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenChart(a.symbol);
                      }}
                      className="font-mono text-[10px] px-2 py-0.5 rounded text-text-muted bg-surface-2 border border-border-subtle hover:text-text-primary hover:bg-surface-3 transition-colors"
                    >
                      Chart →
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// §03 Open positions
// ────────────────────────────────────────────────────────────────

function Positions({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: trades } = useOpenTrades();
  const { data: prices } = useLivePrices();
  const rows = trades ?? [];
  const unrealized = rows.reduce((acc, t) => acc + (t.pnl ?? 0), 0);

  return (
    <div className="px-8 py-6">
      <div className="flex items-baseline gap-3.5 mb-4">
        <span className="sect-no">§ 03</span>
        <h2
          className="serif-display italic text-text-primary"
          style={{ fontSize: "22px" }}
        >
          Open positions
        </h2>
        <div className="flex-1 h-px bg-border-subtle" />
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          {rows.length} open · ${unrealized >= 0 ? "+" : "−"}
          {Math.abs(unrealized).toFixed(0)} unrealized
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-border-subtle bg-surface-1 py-10 text-center">
          <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
            no open positions
          </div>
        </div>
      ) : (
        <div
          className="rounded-lg border border-border-subtle overflow-hidden"
          style={{ background: "var(--color-surface-1)" }}
        >
          {rows.map((t) => {
            const isLong = t.direction.toLowerCase().startsWith("l");
            const last =
              prices?.prices?.[t.symbol]?.price ?? t.entry_price;
            const stop =
              t.stop_price ?? t.entry_price * (isLong ? 0.98 : 1.02);
            const target =
              t.target_price ?? t.entry_price * (isLong ? 1.04 : 0.96);
            const lo = Math.min(stop, target);
            const hi = Math.max(stop, target);
            const range = hi - lo || 1;
            const pctFromLo = Math.max(
              0,
              Math.min(100, ((last - lo) / range) * 100),
            );
            const entryPct = ((t.entry_price - lo) / range) * 100;
            const pnl = t.pnl ?? 0;
            const pnlPct = (pnl / (t.entry_price * t.shares)) * 100;

            return (
              <div
                key={t.id}
                className="grid items-center py-3.5 px-4 border-b border-border-subtle last:border-b-0 gap-3 hover:bg-surface-2 transition-colors cursor-pointer"
                style={{ gridTemplateColumns: "140px 1fr 100px 110px 80px" }}
                onClick={() => onOpenChart(t.symbol)}
              >
                <div className="flex items-center gap-2.5">
                  <span className={`dir-pill ${isLong ? "long" : "short"}`}>
                    {isLong ? "L" : "S"}
                  </span>
                  <div>
                    <div className="font-mono text-[14px] font-semibold text-text-primary">
                      {t.symbol}
                    </div>
                    <div className="font-mono text-[10px] text-text-muted">
                      {t.shares} sh · ${t.entry_price.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div
                  className="relative h-8 rounded border border-border-subtle overflow-hidden"
                  style={{ background: "var(--color-surface-0)" }}
                >
                  <div
                    className="absolute top-0 bottom-0 left-0 opacity-50"
                    style={{
                      width: `${pctFromLo}%`,
                      background: `linear-gradient(90deg, transparent, var(--color-bullish-muted), var(--color-bullish))`,
                    }}
                  />
                  <div
                    className="absolute top-[-2px] bottom-[-2px] w-[2px] z-10"
                    style={{
                      left: `${Math.max(0, Math.min(100, entryPct))}%`,
                      background: "var(--color-text-primary)",
                    }}
                    title="Entry"
                  />
                  <div className="absolute inset-0 flex items-center justify-between px-2 font-mono text-[9.5px] text-text-muted pointer-events-none">
                    <span>
                      ${(isLong ? stop : target).toFixed(2)}{" "}
                      <span
                        style={{
                          color: isLong
                            ? "var(--color-bearish)"
                            : "var(--color-bullish)",
                        }}
                      >
                        {isLong ? "STOP" : "TGT"}
                      </span>
                    </span>
                    <span>
                      {isLong ? "TGT" : "STOP"}{" "}
                      <span
                        style={{
                          color: isLong
                            ? "var(--color-bullish)"
                            : "var(--color-bearish)",
                        }}
                      >
                        ${(isLong ? target : stop).toFixed(2)}
                      </span>
                    </span>
                  </div>
                </div>

                <div className="text-right font-mono">
                  <div className="text-[12px] text-text-primary">
                    ${last.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-text-muted">last</div>
                </div>
                <div className="text-right font-mono">
                  <div
                    className="text-[14px] font-semibold"
                    style={{
                      color:
                        pnl >= 0
                          ? "var(--color-bullish-text)"
                          : "var(--color-bearish-text)",
                    }}
                  >
                    {pnl >= 0 ? "+" : "−"}${Math.abs(pnl).toFixed(0)}
                  </div>
                  <div
                    className="text-[10px] opacity-75 mt-px"
                    style={{
                      color:
                        pnl >= 0
                          ? "var(--color-bullish-text)"
                          : "var(--color-bearish-text)",
                    }}
                  >
                    {pnlPct >= 0 ? "+" : ""}
                    {pnlPct.toFixed(2)}%
                  </div>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenChart(t.symbol);
                    }}
                    className="text-[11px] px-2.5 py-1.5 rounded text-text-secondary border border-border-subtle hover:bg-surface-3 hover:text-text-primary"
                  >
                    Manage
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// Side panel: Regime · AI briefing · Game plan · Watchlist
// ────────────────────────────────────────────────────────────────

function SideSect({ children }: { children: React.ReactNode }) {
  return <div className="px-5 py-5 border-b border-border-subtle">{children}</div>;
}

function SideHead({
  title,
  em,
  right,
}: {
  title: string;
  em: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-3.5">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted font-semibold">
        {title} <span style={{ color: "var(--color-accent-ink)" }}>{em}</span>
      </div>
      {right}
    </div>
  );
}

function RegimePanel() {
  const { data: sectors } = useSectorRotation();
  const { data: prices } = useLivePrices();

  const inflow = sectors?.filter((s) => s.flow === "INFLOW").length ?? 0;
  const total = sectors?.length ?? 0;
  const riskOn = total > 0 && inflow / total >= 0.55;
  const desc = riskOn
    ? "Trend constructive across majors. Breadth expanding, VIX compressed. Continuation setups preferred."
    : "Defensive tone. Trim winners, tighten stops; wait for clearer structure before adding size.";

  const bars = [
    { n: "SPY", key: "SPY" },
    { n: "QQQ", key: "QQQ" },
    { n: "IWM", key: "IWM" },
    { n: "VIX", key: "VIX" },
  ].map((b) => {
    const p = prices?.prices?.[b.key];
    const chg = p?.change_pct ?? 0;
    return {
      n: b.n,
      v: `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`,
      pct: Math.min(Math.abs(chg) * 30 + 15, 90),
      up: chg >= 0,
    };
  });

  return (
    <SideSect>
      <SideHead
        title="Market"
        em="regime"
        right={
          <span className="font-mono text-[9.5px] text-text-muted">QQQ-led</span>
        }
      />
      <div
        className="rounded-lg border border-border-subtle p-4"
        style={{ background: "var(--color-surface-0)" }}
      >
        <div
          className="font-display italic text-text-primary leading-none mb-1"
          style={{ fontSize: "26px" }}
        >
          Risk{" "}
          <em
            style={{
              color: riskOn
                ? "var(--color-bullish-text)"
                : "var(--color-bearish-text)",
              fontStyle: "italic",
            }}
          >
            {riskOn ? "on" : "off"}
          </em>
        </div>
        <div
          className="font-serif italic text-text-secondary mb-3"
          style={{
            fontSize: "12.5px",
            lineHeight: 1.5,
            textWrap: "pretty" as never,
          }}
        >
          {desc}
        </div>
        <div className="flex flex-col gap-2">
          {bars.map((b) => (
            <div
              key={b.n}
              className="grid items-center gap-2.5 font-mono text-[10px]"
              style={{ gridTemplateColumns: "40px 1fr 48px" }}
            >
              <span className="text-text-muted uppercase tracking-[0.1em]">
                {b.n}
              </span>
              <div
                className="h-[4px] rounded relative overflow-hidden"
                style={{ background: "var(--color-surface-3)" }}
              >
                <div
                  className="absolute top-0 bottom-0 rounded"
                  style={{
                    width: `${b.pct}%`,
                    left: b.up ? "50%" : undefined,
                    right: b.up ? undefined : "50%",
                    background: b.up
                      ? "var(--color-bullish)"
                      : "var(--color-bearish)",
                  }}
                />
              </div>
              <span
                className="text-right font-medium"
                style={{
                  color: b.up
                    ? "var(--color-bullish-text)"
                    : "var(--color-bearish-text)",
                }}
              >
                {b.v}
              </span>
            </div>
          ))}
        </div>
      </div>
    </SideSect>
  );
}

function AiBriefing() {
  const { data: summary } = useSessionSummary();

  // TODO: wire to /coach/briefing endpoint; for now, derive a deterministic summary.
  const briefing =
    summary && summary.total_alerts > 0
      ? `Session is building constructively. ${summary.total_alerts} signals fired today, with ${summary.target_1_hits} hitting Target 1. I'd let existing trades work rather than chasing late entries.`
      : "No new A-grade setups in the last 12 minutes. Market quiet — respect the pause. The best edge right now is patience.";

  return (
    <SideSect>
      <SideHead title="AI" em="briefing" />
      <div
        className="rounded-lg p-3.5 border border-border-subtle"
        style={{
          background: "var(--color-surface-0)",
          borderLeft: "2px solid var(--color-accent)",
        }}
      >
        <div className="flex items-center gap-2 mb-2.5">
          <span className="ai-dot" />
          <span
            className="font-mono text-[9.5px] uppercase tracking-[0.14em]"
            style={{ color: "var(--color-accent-ink)" }}
          >
            Co-Pilot · afternoon update
          </span>
        </div>
        <p
          className="font-serif italic text-text-primary"
          style={{
            fontSize: "13.5px",
            lineHeight: 1.55,
            textWrap: "pretty" as never,
          }}
        >
          {briefing}
        </p>
        <div className="flex justify-between items-center mt-3 pt-2.5 border-t border-border-subtle">
          <span className="font-mono text-[9.5px] text-text-muted">
            {new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            · Claude
          </span>
          <a
            href="/copilot"
            className="text-[11px] px-2.5 py-1 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-2"
          >
            Ask follow-up
          </a>
        </div>
      </div>
    </SideSect>
  );
}

function GamePlan() {
  const { data: active } = useActiveEntries();
  const { data: trades } = useOpenTrades();

  const items = useMemo(() => {
    const plan: { title: string; tags: string[] }[] = [];
    (active ?? []).slice(0, 2).forEach((e) => {
      if (e.entry_price) {
        plan.push({
          title: `${e.symbol} — add on pullback to ${e.entry_price.toFixed(2)}`,
          tags: ["key", "entry"],
        });
      }
    });
    (trades ?? []).slice(0, 2).forEach((t) => {
      const isLong = t.direction.toLowerCase().startsWith("l");
      plan.push({
        title: `${isLong ? "Trim" : "Cover"} ${t.symbol} into ${(t.target_price ?? t.entry_price).toFixed(2)} (T1)`,
        tags: ["exit"],
      });
    });
    if (plan.length < 4) {
      plan.push({
        title: "Watch SPY 548 / 551 breakout for continuation",
        tags: ["macro"],
      });
    }
    if (plan.length < 5) {
      plan.push({
        title: "Avoid late entries — wait for next-day base",
        tags: ["risk"],
      });
    }
    return plan.slice(0, 5);
  }, [active, trades]);

  return (
    <SideSect>
      <SideHead
        title="Game"
        em="plan"
        right={
          <span className="font-mono text-[9.5px] text-text-muted">
            {items.length} items
          </span>
        }
      />
      <div>
        {items.map((p, i) => (
          <div
            key={i}
            className="flex gap-3 py-2.5 border-b border-border-subtle last:border-b-0"
          >
            <span className="font-mono text-[10px] text-text-faint min-w-5 pt-0.5">
              {String(i + 1).padStart(2, "0")}
            </span>
            <div className="flex-1">
              <div className="text-[12px] text-text-primary">{p.title}</div>
              <div className="mt-1 flex gap-1.5 flex-wrap">
                {p.tags.map((t) => (
                  <span
                    key={t}
                    className="font-mono text-[9px] px-1.5 py-px rounded tracking-[0.06em] uppercase"
                    style={{
                      background:
                        t === "key" || t === "entry"
                          ? "var(--color-accent-muted)"
                          : t === "exit"
                          ? "var(--color-bullish-muted)"
                          : t === "risk"
                          ? "var(--color-bearish-muted)"
                          : "var(--color-surface-3)",
                      color:
                        t === "key" || t === "entry"
                          ? "var(--color-accent-ink)"
                          : t === "exit"
                          ? "var(--color-bullish-text)"
                          : t === "risk"
                          ? "var(--color-bearish-text)"
                          : "var(--color-text-secondary)",
                    }}
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </SideSect>
  );
}

function Watchlist({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: watchlist } = useWatchlist();
  const { data: prices } = useLivePrices();

  return (
    <SideSect>
      <SideHead
        title="Watch"
        em="list"
        right={
          <a
            href="/settings"
            className="font-mono text-[9.5px]"
            style={{ color: "var(--color-accent-ink)" }}
          >
            + add
          </a>
        }
      />
      <div>
        {(watchlist ?? []).length === 0 && (
          <div className="text-[11px] text-text-muted py-2 font-mono">
            No symbols yet —{" "}
            <a href="/settings" style={{ color: "var(--color-accent-ink)" }}>
              add some
            </a>
            .
          </div>
        )}
        {(watchlist ?? []).slice(0, 8).map((w) => {
          const p = prices?.prices?.[w.symbol];
          const chg = p?.change_pct ?? 0;
          const up = chg >= 0;
          return (
            <div
              key={w.id}
              className="grid items-center py-2 border-b border-border-subtle last:border-b-0 gap-2.5 font-mono cursor-pointer hover:opacity-80"
              style={{ gridTemplateColumns: "60px 1fr 60px", fontSize: "11.5px" }}
              onClick={() => onOpenChart(w.symbol)}
            >
              <span className="text-text-primary font-semibold">{w.symbol}</span>
              <Spark
                data={seededSpark(w.symbol, 20, up ? 1 : -1)}
                up={up}
                width={80}
                height={22}
              />
              <span
                className="text-right font-medium"
                style={{
                  fontSize: "11px",
                  color: up
                    ? "var(--color-bullish-text)"
                    : "var(--color-bearish-text)",
                }}
              >
                {up ? "+" : ""}
                {chg.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </SideSect>
  );
}

function SidePanel({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  return (
    <div
      className="hidden xl:block bg-surface-1 border-l border-border-subtle overflow-y-auto"
      style={{ width: 340 }}
    >
      <RegimePanel />
      <AiBriefing />
      <GamePlan />
      <Watchlist onOpenChart={onOpenChart} />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────
// Page root
// ────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();
  useMarketStatus(); // prefetch
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, []);

  const onOpenChart = (sym: string) => {
    navigate(`/trading?symbol=${encodeURIComponent(sym)}`);
  };

  return (
    <div
      className="h-full grid overflow-hidden"
      style={{ gridTemplateColumns: "1fr auto" }}
    >
      <div className="overflow-y-auto min-w-0">
        <DateHero />
        <KpiRow />
        <PrioritySignals onOpenChart={onOpenChart} />
        <SignalFeed onOpenChart={onOpenChart} />
        <Positions onOpenChart={onOpenChart} />
      </div>
      <SidePanel onOpenChart={onOpenChart} />
    </div>
  );
}
