/** AI Co-Pilot — tabbed hub.
 *  Tabs: Best setup · AI signals · AI updates · Win rates · Coach chat
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useActiveEntries,
  useAlertsToday,
  useScanner,
  usePerformanceBreakdown,
} from "../api/hooks";
import { useCoachStream } from "../hooks/useCoachStream";
import { Send, Sparkles } from "lucide-react";
import type { Alert, SignalResult } from "../types";

type TabId = "best" | "signals" | "updates" | "winrates" | "chat";

const TABS: { id: TabId; label: string }[] = [
  { id: "best", label: "Best setup" },
  { id: "signals", label: "AI signals" },
  { id: "updates", label: "AI updates" },
  { id: "winrates", label: "Win rates" },
  { id: "chat", label: "Coach chat" },
];

const TAB_KEY = "twai_coach_tab";

function gradeFromScore(score: number): "a" | "b" | "c" {
  if (score >= 80) return "a";
  if (score >= 60) return "b";
  return "c";
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

// ──────────────────────────────────────────────────────────────
// Best setup
// ──────────────────────────────────────────────────────────────

function CoachBestSetup({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: scan } = useScanner();
  const ranked = useMemo(
    () => (scan ?? []).slice().sort((a, b) => b.score - a.score).slice(0, 10),
    [scan],
  );
  const [selIdx, setSelIdx] = useState(0);
  const sel = ranked[selIdx] as SignalResult | undefined;

  return (
    <div
      className="h-full grid overflow-hidden"
      style={{ gridTemplateColumns: "320px 1fr" }}
    >
      {/* List */}
      <div className="border-r border-border-subtle bg-surface-1 overflow-y-auto">
        <div className="flex justify-between items-baseline px-5 py-4 border-b border-border-subtle">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-secondary">
            Ranked setups
          </span>
          <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-text-muted">
            live · scored by AI
          </span>
        </div>
        {ranked.length === 0 && (
          <div className="font-mono text-[11px] text-text-muted px-5 py-8 text-center uppercase tracking-[0.14em]">
            no setups yet
          </div>
        )}
        {ranked.map((b, i) => {
          const tier = gradeFromScore(b.score);
          const active = i === selIdx;
          return (
            <div
              key={b.symbol}
              onClick={() => setSelIdx(i)}
              className="grid items-center gap-3 px-5 py-3.5 border-b border-border-subtle cursor-pointer transition-colors"
              style={{
                gridTemplateColumns: "44px 1fr auto",
                background: active ? "var(--color-surface-2)" : "transparent",
                boxShadow: active ? "inset 3px 0 0 var(--color-accent)" : "none",
              }}
            >
              <div
                className="font-mono font-semibold text-center py-1.5 rounded border"
                style={{
                  fontSize: 14,
                  background:
                    tier === "a"
                      ? "var(--color-bullish-muted)"
                      : tier === "b"
                      ? "var(--color-accent-muted)"
                      : "var(--color-surface-3)",
                  color:
                    tier === "a"
                      ? "var(--color-bullish-text)"
                      : tier === "b"
                      ? "var(--color-accent-ink)"
                      : "var(--color-text-secondary)",
                  borderColor:
                    tier === "a"
                      ? "var(--color-bullish)"
                      : tier === "b"
                      ? "var(--color-accent)"
                      : "var(--color-border-default)",
                }}
              >
                {b.score}
              </div>
              <div>
                <div className="font-mono text-[13px] font-semibold text-text-primary">
                  {b.symbol}
                </div>
                <div className="text-[11px] text-text-muted mt-0.5">
                  {b.pattern || b.action_label || "Pattern"}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-[11px] text-text-secondary">5m</div>
                <div className="font-mono text-[11px] text-text-muted mt-0.5">
                  {b.rr_ratio ? `${b.rr_ratio.toFixed(1)}R` : "—"}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Detail */}
      <div className="overflow-y-auto px-10 py-8">
        {!sel ? (
          <div className="font-mono text-[11px] text-text-muted uppercase tracking-[0.14em]">
            select a setup
          </div>
        ) : (
          <>
            <div className="flex justify-between items-start mb-7 gap-6">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted mb-1.5">
                  Best setup · now
                </div>
                <h2
                  className="serif-display text-text-primary"
                  style={{ fontSize: 40, lineHeight: 1.05 }}
                >
                  <em>{sel.symbol}</em> — {sel.pattern || "Setup"}
                </h2>
              </div>
              <div
                className="text-center rounded-lg p-4 min-w-[120px] border"
                style={{
                  background:
                    gradeFromScore(sel.score) === "a"
                      ? "var(--color-bullish-muted)"
                      : gradeFromScore(sel.score) === "b"
                      ? "var(--color-accent-muted)"
                      : "var(--color-surface-1)",
                  borderColor:
                    gradeFromScore(sel.score) === "a"
                      ? "var(--color-bullish)"
                      : gradeFromScore(sel.score) === "b"
                      ? "var(--color-accent)"
                      : "var(--color-border-default)",
                }}
              >
                <div
                  className="font-mono font-semibold text-text-primary"
                  style={{ fontSize: 32, lineHeight: 1 }}
                >
                  {sel.score}
                </div>
                <div className="font-mono text-[9px] text-text-muted tracking-[0.16em] mt-1.5">
                  AI SCORE
                </div>
              </div>
            </div>

            <div
              className="grid rounded border border-border-subtle mb-6"
              style={{
                gridTemplateColumns: "repeat(4, 1fr)",
                background: "var(--color-surface-1)",
              }}
            >
              {[
                { label: "Grade", value: sel.grade || "—" },
                {
                  label: "Risk/Reward",
                  value: sel.rr_ratio ? `${sel.rr_ratio.toFixed(1)}R` : "—",
                },
                {
                  label: "Entry",
                  value: sel.entry ? `$${sel.entry.toFixed(2)}` : "—",
                },
                {
                  label: "Stop",
                  value: sel.stop ? `$${sel.stop.toFixed(2)}` : "—",
                },
              ].map((m, i) => (
                <div
                  key={i}
                  className="px-4 py-3.5 border-r border-border-subtle last:border-r-0"
                >
                  <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-muted mb-1.5">
                    {m.label}
                  </div>
                  <b
                    className="font-mono font-semibold text-text-primary"
                    style={{ fontSize: 16 }}
                  >
                    {m.value}
                  </b>
                </div>
              ))}
            </div>

            <div className="mb-5">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted mb-2">
                Trigger
              </div>
              <div
                className="px-4 py-3.5 font-mono text-text-primary text-[13px]"
                style={{
                  background: "var(--color-surface-1)",
                  borderLeft: "2px solid var(--color-accent)",
                  lineHeight: 1.6,
                }}
              >
                {sel.action_label || "Waiting for confirmation"}
              </div>
            </div>

            <div className="mb-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted mb-2">
                Why this setup
              </div>
              <div
                className="px-4 py-3.5 text-text-secondary text-[13px]"
                style={{
                  background: "var(--color-surface-1)",
                  borderLeft: "2px solid var(--color-accent)",
                  lineHeight: 1.6,
                  textWrap: "pretty" as never,
                }}
              >
                {sel.pattern
                  ? `${sel.symbol} is showing a ${sel.pattern.toLowerCase()} with score ${sel.score}. ${
                      sel.near_support ? "Near support — entry setup clean." : ""
                    } Confluence score ${(sel.score).toFixed(0)}.`
                  : "Setup forming. Wait for confirmation before adding size."}
              </div>
            </div>

            <div className="flex gap-2.5">
              <button
                onClick={() => onOpenChart(sel.symbol)}
                className="px-3.5 py-2 rounded-md font-medium text-[12px]"
                style={{
                  background: "var(--color-accent)",
                  color: "var(--color-surface-0)",
                }}
              >
                Open {sel.symbol} chart →
              </button>
              <button className="px-3.5 py-2 rounded-md font-medium text-[12px] text-text-secondary border border-border-subtle hover:bg-surface-2 hover:text-text-primary transition-colors">
                Set alert on trigger
              </button>
              <button className="px-3.5 py-2 rounded-md font-medium text-[12px] text-text-secondary border border-border-subtle hover:bg-surface-2 hover:text-text-primary transition-colors">
                Ask Co-Pilot
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// AI signals feed
// ──────────────────────────────────────────────────────────────

function kindFromAlert(a: Alert): "entry" | "alert" | "exit" | "warn" {
  const t = (a.alert_type || "").toLowerCase();
  if (t.includes("target") || t.includes("exit") || t.includes("trim")) return "exit";
  if (t.includes("stop") || t.includes("warn")) return "warn";
  if (t.includes("approach") || t.includes("near")) return "alert";
  return "entry";
}

function CoachSignals({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { data: alerts } = useAlertsToday();
  const rows = alerts ?? [];

  return (
    <div className="p-7 max-w-[1100px] overflow-y-auto h-full">
      <div className="flex justify-between items-center font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted mb-3 px-1">
        <span>AI signals · live feed</span>
        <span className="text-[10px] text-text-muted normal-case tracking-normal">
          click row → open chart
        </span>
      </div>
      {rows.length === 0 && (
        <div className="rounded-lg border border-border-subtle bg-surface-1 py-12 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
          waiting for signals
        </div>
      )}
      {rows.map((s) => {
        const kind = kindFromAlert(s);
        const colorMap = {
          entry: { bg: "var(--color-bullish-muted)", fg: "var(--color-bullish-text)" },
          alert: { bg: "var(--color-accent-muted)", fg: "var(--color-accent-ink)" },
          exit: { bg: "var(--color-info-muted)", fg: "var(--color-info)" },
          warn: { bg: "var(--color-bearish-muted)", fg: "var(--color-bearish-text)" },
        }[kind];
        const conf = Math.round(s.score);
        return (
          <div
            key={s.id}
            onClick={() => onOpenChart(s.symbol)}
            className="grid items-center gap-4 py-3.5 px-4 border-b border-border-subtle bg-surface-1 cursor-pointer transition-colors hover:bg-surface-2"
            style={{
              gridTemplateColumns: "60px 90px 80px 1fr 140px",
            }}
          >
            <div className="font-mono text-[11px] text-text-muted">
              {formatTime(s.created_at)}
            </div>
            <div
              className="font-mono text-[9px] uppercase tracking-[0.14em] px-2 py-1 rounded text-center font-semibold"
              style={{ background: colorMap.bg, color: colorMap.fg }}
            >
              {kind}
            </div>
            <div className="font-mono text-[13px] font-semibold text-text-primary">
              {s.symbol}
            </div>
            <div className="text-[13px] text-text-secondary">
              {s.message || s.alert_type || `${s.symbol} alert triggered`}
            </div>
            <div className="flex items-center gap-2">
              <div
                className="flex-1 h-1 rounded overflow-hidden"
                style={{ background: "var(--color-surface-3)" }}
              >
                <div
                  className="h-full rounded"
                  style={{
                    width: `${conf}%`,
                    background: "var(--color-accent)",
                  }}
                />
              </div>
              <span className="font-mono text-[11px] text-text-secondary min-w-6 text-right">
                {conf}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenChart(s.symbol);
                }}
                className="font-mono text-[10px] px-2 py-1 rounded border"
                style={{
                  background: "var(--color-accent-muted)",
                  color: "var(--color-accent-ink)",
                  borderColor: "var(--color-accent)",
                }}
              >
                Chart →
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// AI updates timeline
// ──────────────────────────────────────────────────────────────

function CoachUpdates({ onOpenChart }: { onOpenChart: (sym: string) => void }) {
  const { messages } = useCoachStream();
  const { data: alerts } = useAlertsToday();

  // Group: the Coach's own responses + a synthetic pre-open plan item.
  const updates = useMemo(() => {
    const out: {
      time: string;
      heading: string;
      body: string;
      tags: string[];
    }[] = [];

    if (alerts && alerts.length > 0) {
      const symbols = Array.from(new Set(alerts.map((a) => a.symbol))).slice(0, 5);
      const top = alerts[0];
      out.push({
        time: formatTime(top.created_at),
        heading: "Session check-in",
        body: `${alerts.length} signals fired so far today. Top score: ${top.symbol} at ${top.score}. Breadth is ${
          alerts.filter((a) => a.direction.toLowerCase() !== "short").length >
          alerts.length / 2
            ? "upward-biased"
            : "defensive"
        }.`,
        tags: symbols,
      });
    }

    messages
      .filter((m) => m.role === "assistant" && m.content.length > 20)
      .slice(-4)
      .reverse()
      .forEach((m, i) => {
        const firstLine = m.content.split("\n").find((l) => l.trim());
        out.push({
          time: `—${i + 1}`,
          heading: firstLine?.slice(0, 80) || "AI note",
          body: m.content.slice(0, 360),
          tags: [],
        });
      });

    if (out.length === 0) {
      out.push({
        time: "09:45",
        heading: "Pre-open game plan",
        body: "Overnight levels and key sectors have been checked. No major shifts. Watch for open-range breakouts in names on your watchlist. Avoid chasing gaps.",
        tags: ["SPY", "QQQ"],
      });
    }
    return out;
  }, [messages, alerts]);

  return (
    <div className="px-10 py-7 max-w-[820px] mx-auto overflow-y-auto h-full">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted px-1 pb-4">
        AI updates · what changed today
      </div>
      <div className="relative">
        <div
          className="absolute left-[55px] top-2 bottom-5 w-px"
          style={{ background: "var(--color-border-subtle)" }}
        />
        {updates.map((u, i) => (
          <div
            key={i}
            className="grid gap-5 pb-7 relative"
            style={{ gridTemplateColumns: "80px 1fr" }}
          >
            <div className="text-right relative pt-1">
              <div
                className="absolute -right-4 top-[7px] w-2.5 h-2.5 rounded-full"
                style={{
                  background: "var(--color-accent)",
                  boxShadow: "0 0 0 4px var(--color-surface-0)",
                }}
              />
              <div className="font-mono text-[11px] text-text-muted">
                {u.time}
              </div>
            </div>
            <div>
              <h3
                className="font-display text-text-primary mb-2"
                style={{
                  fontSize: "22px",
                  fontWeight: 400,
                  lineHeight: 1.2,
                  letterSpacing: "-0.005em",
                }}
              >
                {u.heading}
              </h3>
              <p
                className="text-[14px] text-text-secondary"
                style={{ lineHeight: 1.65, textWrap: "pretty" as never }}
              >
                {u.body}
              </p>
              {u.tags.length > 0 && (
                <div className="flex gap-1.5 mt-3 flex-wrap">
                  {u.tags.map((t) => (
                    <button
                      key={t}
                      onClick={() => onOpenChart(t)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded border border-border-subtle bg-surface-1 text-[11px] text-text-secondary transition-colors hover:bg-accent-muted"
                      style={{ background: "var(--color-surface-1)" }}
                    >
                      <span className="font-mono font-semibold">{t}</span>
                      <span className="opacity-50">↗</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Win rates
// ──────────────────────────────────────────────────────────────

function CoachWinRates() {
  const { data } = usePerformanceBreakdown();
  const rows = useMemo(() => {
    if (!data?.by_pattern) return [];
    const sorted = [...data.by_pattern].sort((a, b) => b.trades - a.trades);
    if (sorted.length === 0) return [];
    const best = sorted.reduce((a, b) => (a.win_rate > b.win_rate ? a : b));
    const worst = sorted.reduce((a, b) => (a.win_rate < b.win_rate ? a : b));
    return sorted.map((r) => ({
      ...r,
      best: r.pattern === best.pattern && sorted.length > 1,
      worst: r.pattern === worst.pattern && sorted.length > 1,
    }));
  }, [data]);

  return (
    <div className="px-10 py-7 max-w-[960px] overflow-y-auto h-full">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted px-1 pb-4">
        Your win rates by setup · trailing 90 days
      </div>
      {rows.length === 0 ? (
        <div className="rounded border border-border-subtle bg-surface-1 py-10 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
          not enough trades yet to break down by setup
        </div>
      ) : (
        <div
          className="rounded border border-border-subtle overflow-hidden"
          style={{ background: "var(--color-surface-1)" }}
        >
          <div
            className="grid gap-3.5 px-5 py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted border-b border-border-subtle"
            style={{
              gridTemplateColumns: "2.4fr 0.6fr 0.8fr 0.8fr 2fr",
              background: "var(--color-surface-2)",
            }}
          >
            <div>Setup</div>
            <div>N</div>
            <div>Win rate</div>
            <div>Avg P&L</div>
            <div>Distribution</div>
          </div>
          {rows.map((r, i) => (
            <div
              key={i}
              className="grid gap-3.5 items-center px-5 py-3 border-b border-border-subtle last:border-b-0 text-[13px]"
              style={{
                gridTemplateColumns: "2.4fr 0.6fr 0.8fr 0.8fr 2fr",
                background: r.best
                  ? "var(--color-bullish-muted)"
                  : r.worst
                  ? "var(--color-bearish-muted)"
                  : "transparent",
              }}
            >
              <div className="text-text-primary flex items-center gap-2.5">
                {r.label}
                {r.best && (
                  <span
                    className="font-mono text-[9px] px-1.5 py-px rounded tracking-[0.1em] font-semibold"
                    style={{
                      background: "var(--color-bullish)",
                      color: "var(--color-surface-0)",
                    }}
                  >
                    BEST
                  </span>
                )}
                {r.worst && (
                  <span
                    className="font-mono text-[9px] px-1.5 py-px rounded tracking-[0.1em] font-semibold"
                    style={{
                      background: "var(--color-bearish)",
                      color: "var(--color-surface-0)",
                    }}
                  >
                    AVOID
                  </span>
                )}
              </div>
              <div className="font-mono text-text-secondary">{r.trades}</div>
              <div
                className="font-mono"
                style={{
                  color:
                    r.win_rate >= 0.6
                      ? "var(--color-bullish-text)"
                      : r.win_rate < 0.45
                      ? "var(--color-bearish-text)"
                      : "var(--color-text-primary)",
                }}
              >
                {(r.win_rate * 100).toFixed(0)}%
              </div>
              <div
                className="font-mono"
                style={{
                  color:
                    r.avg_pnl >= 0
                      ? "var(--color-bullish-text)"
                      : "var(--color-bearish-text)",
                }}
              >
                {r.avg_pnl >= 0 ? "+" : "−"}${Math.abs(r.avg_pnl).toFixed(0)}
              </div>
              <div
                className="h-1.5 rounded overflow-hidden"
                style={{ background: "var(--color-surface-3)" }}
              >
                <div
                  className="h-full rounded"
                  style={{
                    width: `${Math.min(100, Math.max(0, r.win_rate * 100))}%`,
                    background:
                      r.win_rate >= 0.6
                        ? "var(--color-bullish)"
                        : r.win_rate < 0.45
                        ? "var(--color-bearish)"
                        : "var(--color-accent)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Chat
// ──────────────────────────────────────────────────────────────

const SUGGESTION_CHIPS = [
  "Should I add to my biggest winner?",
  "What am I doing wrong on shorts lately?",
  "Scan for continuation setups into close",
  "Review my 3 worst trades this week",
];

function CoachChat() {
  const { messages, streaming, sendMessage } = useCoachStream();
  const [text, setText] = useState("");

  const submit = () => {
    const value = text.trim();
    if (!value || streaming) return;
    sendMessage(value);
    setText("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-8 pt-6 pb-4 max-w-[780px] mx-auto w-full">
        {messages.length === 0 && (
          <div className="flex flex-wrap mb-5">
            {SUGGESTION_CHIPS.map((c) => (
              <button
                key={c}
                onClick={() => sendMessage(c)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border-default bg-surface-1 text-text-secondary mr-1.5 mb-2 transition-colors hover:border-accent hover:bg-surface-2"
                style={{
                  fontFamily: "var(--font-serif)",
                  fontStyle: "italic",
                  fontSize: "12.5px",
                }}
              >
                {c}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className="flex gap-3.5 mb-5">
            <div
              className="w-[30px] h-[30px] rounded-full flex items-center justify-center font-mono text-[11px] font-semibold shrink-0"
              style={
                m.role === "assistant"
                  ? {
                      background:
                        "linear-gradient(135deg, var(--color-accent), var(--color-purple))",
                      color: "var(--color-surface-0)",
                    }
                  : {
                      background: "var(--color-surface-2)",
                      border: "1px solid var(--color-border-default)",
                      color: "var(--color-text-secondary)",
                    }
              }
            >
              {m.role === "assistant" ? (
                <Sparkles className="h-3.5 w-3.5" />
              ) : (
                "You"
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted mb-1">
                {m.role === "assistant" ? "Co-Pilot" : "You"}
              </div>
              <div
                className="text-text-primary"
                style={{
                  fontFamily: "var(--font-serif)",
                  fontSize: "15px",
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  textWrap: "pretty" as never,
                }}
              >
                {m.content}
                {streaming && i === messages.length - 1 && m.role === "assistant" && (
                  <span className="ai-dot inline-block ml-1" />
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="sticky bottom-4 mx-8 mb-4 max-w-[780px] lg:mx-auto w-[calc(100%-4rem)] lg:w-auto">
        <div
          className="rounded-xl p-3 flex items-end gap-2.5 border border-border-default"
          style={{
            background: "var(--color-surface-1)",
            boxShadow: "var(--shadow-elevated)",
          }}
        >
          <textarea
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask about a setup, a trade, or today's plan…"
            className="flex-1 bg-transparent outline-none resize-none"
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: "15px",
              fontStyle: "italic",
              color: "var(--color-text-primary)",
              maxHeight: 140,
            }}
          />
          <button
            onClick={submit}
            disabled={!text.trim() || streaming}
            className="px-3 py-2 rounded font-medium text-[12px] disabled:opacity-50"
            style={{
              background: "var(--color-accent)",
              color: "var(--color-surface-0)",
            }}
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────

export default function AICoPilotPage() {
  const navigate = useNavigate();
  useActiveEntries(); // prefetch

  const [tab, setTab] = useState<TabId>(() => {
    const saved = (typeof localStorage !== "undefined" && localStorage.getItem(TAB_KEY)) as TabId | null;
    return saved && TABS.some((t) => t.id === saved) ? saved : "best";
  });

  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY, tab);
    } catch {
      /* ignore */
    }
  }, [tab]);

  const onOpenChart = (sym: string) => {
    navigate(`/trading?symbol=${encodeURIComponent(sym)}`);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Hero */}
      <div
        className="px-8 pt-6 border-b border-border-subtle"
        style={{ background: "var(--color-surface-1)" }}
      >
        <div className="max-w-[880px] mb-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted mb-3">
            AI Co-Pilot · Claude · always on
          </div>
          <h1
            className="serif-display text-text-primary italic"
            style={{ fontSize: 36, lineHeight: 1.05, marginBottom: 6 }}
          >
            Your edge, <em>surfaced.</em>
          </h1>
          <p
            className="font-serif italic text-text-secondary"
            style={{
              fontSize: 13,
              maxWidth: "62ch",
              textWrap: "pretty" as never,
            }}
          >
            Ranked setups, live AI-tagged signals, narrative updates, and your
            own performance data — in one place.
          </p>
        </div>
        <div className="flex gap-0 -mb-px">
          {TABS.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className="font-mono uppercase py-3 px-4 transition-colors"
                style={{
                  fontSize: 11,
                  letterSpacing: "0.12em",
                  color: active
                    ? "var(--color-text-primary)"
                    : "var(--color-text-muted)",
                  borderBottom: active
                    ? "2px solid var(--color-accent)"
                    : "2px solid transparent",
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab body */}
      <div className="flex-1 overflow-hidden bg-surface-0">
        {tab === "best" && <CoachBestSetup onOpenChart={onOpenChart} />}
        {tab === "signals" && <CoachSignals onOpenChart={onOpenChart} />}
        {tab === "updates" && <CoachUpdates onOpenChart={onOpenChart} />}
        {tab === "winrates" && <CoachWinRates />}
        {tab === "chat" && <CoachChat />}
      </div>
    </div>
  );
}
