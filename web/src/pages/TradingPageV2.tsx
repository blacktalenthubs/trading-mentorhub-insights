/** Trading — 3-column vault layout.
 *  Left: scanner list with grade pills.
 *  Center: chart with level overlays.
 *  Right: thesis / plan / confluence / actions inspector.
 */

import { useState, useMemo, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useScanner,
  useLivePrices,
  useOHLCV,
  useChartLevels,
  useActiveEntries,
  useOpenRealTrade,
} from "../api/hooks";
import CandlestickChart from "../components/CandlestickChart";
import type { SignalResult } from "../types";

type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h" | "D";
type ChipFilter = "all" | "long" | "short" | "a-grade" | "crypto";

const TIMEFRAME_MAP: Record<Timeframe, { period: string; interval: string }> = {
  "1m": { period: "1d", interval: "1m" },
  "5m": { period: "5d", interval: "5m" },
  "15m": { period: "5d", interval: "15m" },
  "1h": { period: "1mo", interval: "60m" },
  "4h": { period: "3mo", interval: "60m" },
  D: { period: "1y", interval: "1d" },
};

function gradeFromScore(score: number): "A" | "B" | "C" {
  if (score >= 80) return "A";
  if (score >= 60) return "B";
  return "C";
}

function isCrypto(sym: string): boolean {
  return /(-USD$|BTC|ETH)/.test(sym);
}

// ──────────────────────────────────────────────────────────────
// Left: Scanner
// ──────────────────────────────────────────────────────────────

function Scanner({
  selected,
  onSelect,
}: {
  selected: string;
  onSelect: (sym: string) => void;
}) {
  const { data, isLoading, refetch } = useScanner();
  const [filter, setFilter] = useState<ChipFilter>("all");

  const rows = useMemo(() => {
    if (!data) return [];
    return data.filter((s) => {
      if (filter === "long") return s.direction.toLowerCase() !== "short";
      if (filter === "short") return s.direction.toLowerCase() === "short";
      if (filter === "a-grade") return s.score >= 80;
      if (filter === "crypto") return isCrypto(s.symbol);
      return true;
    });
  }, [data, filter]);

  return (
    <div className="flex flex-col border-r border-border-subtle overflow-hidden bg-surface-0">
      <div
        className="flex items-center justify-between px-4 py-3.5 border-b border-border-subtle sticky top-0 z-20"
        style={{ background: "var(--color-surface-0)" }}
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text-muted">
          Scanner · {rows.length}
        </span>
        <button
          onClick={() => refetch()}
          className="font-mono text-[10px] px-2 py-1 rounded text-text-muted bg-surface-2 border border-border-subtle hover:text-text-primary hover:bg-surface-3 transition-colors"
        >
          Refresh
        </button>
      </div>

      <div className="flex gap-1.5 px-4 py-2.5 border-b border-border-subtle overflow-x-auto no-scrollbar">
        {(["all", "long", "short", "a-grade", "crypto"] as ChipFilter[]).map(
          (c) => {
            const active = filter === c;
            return (
              <button
                key={c}
                onClick={() => setFilter(c)}
                className="font-mono text-[10px] px-2.5 py-1 rounded-full whitespace-nowrap transition-colors"
                style={{
                  background: active
                    ? "var(--color-accent-muted)"
                    : "var(--color-surface-2)",
                  color: active
                    ? "var(--color-accent-ink)"
                    : "var(--color-text-muted)",
                  border: active ? "1px solid transparent" : "1px solid var(--color-border-subtle)",
                }}
              >
                {c}
              </button>
            );
          },
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="font-mono text-[11px] text-text-muted px-4 py-4">
            Loading…
          </div>
        )}
        {rows.length === 0 && !isLoading && (
          <div className="font-mono text-[11px] text-text-muted px-4 py-8 text-center uppercase tracking-[0.14em]">
            no results
          </div>
        )}
        {rows.map((s) => {
          const active = s.symbol === selected;
          const grade = gradeFromScore(s.score);
          const isLong = s.direction.toLowerCase() !== "short";
          const chg = 0; // SignalResult doesn't carry a precomputed %; live prices used elsewhere.
          return (
            <div
              key={s.symbol}
              onClick={() => onSelect(s.symbol)}
              className="px-4 py-3 border-b border-border-subtle cursor-pointer transition-colors"
              style={{
                background: active ? "var(--color-surface-2)" : "transparent",
                borderLeft: active
                  ? "2px solid var(--color-accent)"
                  : "2px solid transparent",
                paddingLeft: active ? 14 : 16,
              }}
            >
              <div className="flex items-center gap-2">
                <span
                  className="font-mono font-semibold text-[13px] text-text-primary"
                  style={{ letterSpacing: "-0.01em" }}
                >
                  {s.symbol}
                </span>
                <span className={`dir-pill ${isLong ? "long" : "short"}`}>
                  {isLong ? "L" : "S"}
                </span>
                <span
                  className="font-mono text-[10px] font-semibold px-1.5 py-px rounded ml-auto"
                  style={{
                    background:
                      grade === "A"
                        ? "var(--color-bullish-muted)"
                        : grade === "B"
                        ? "var(--color-warning-muted)"
                        : "var(--color-surface-3)",
                    color:
                      grade === "A"
                        ? "var(--color-bullish-text)"
                        : grade === "B"
                        ? "var(--color-warning-text)"
                        : "var(--color-text-secondary)",
                  }}
                >
                  {grade}
                </span>
              </div>
              <div
                className="flex justify-between items-center mt-1 font-mono text-[11px] text-text-muted"
              >
                <span>
                  ${(s.close ?? s.entry ?? 0).toFixed(2)}
                </span>
                <span
                  style={{
                    color:
                      chg >= 0
                        ? "var(--color-bullish-text)"
                        : "var(--color-bearish-text)",
                  }}
                >
                  {s.pattern || "—"}
                </span>
              </div>
              <div
                className="mt-1.5 font-serif italic text-text-secondary"
                style={{
                  fontSize: "11.5px",
                  lineHeight: 1.4,
                  textWrap: "pretty" as never,
                }}
              >
                {s.action_label || s.pattern || "Setup pending confirmation."}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Center: Chart
// ──────────────────────────────────────────────────────────────

function ChartPane({
  symbol,
  scan,
  tf,
  setTf,
}: {
  symbol: string;
  scan?: SignalResult;
  tf: Timeframe;
  setTf: (t: Timeframe) => void;
}) {
  const { period, interval } = TIMEFRAME_MAP[tf];
  const { data: ohlcv } = useOHLCV(symbol, period, interval);
  const { data: levels } = useChartLevels(symbol);
  const { data: prices } = useLivePrices();
  const last = prices?.prices?.[symbol]?.price ?? scan?.close ?? scan?.entry ?? 0;
  const chg = prices?.prices?.[symbol]?.change_pct ?? 0;

  return (
    <div className="flex flex-col min-w-0 overflow-hidden">
      {/* Head */}
      <div className="flex items-center gap-4 px-5 py-3.5 border-b border-border-subtle">
        <div className="flex items-baseline gap-2.5">
          <span
            className="font-display italic text-text-primary"
            style={{ fontSize: "28px", letterSpacing: "-0.01em" }}
          >
            {symbol}
          </span>
          <span
            className="font-serif italic text-text-muted"
            style={{ fontSize: "13px" }}
          >
            {scan?.pattern || ""}
          </span>
        </div>

        <div
          className="flex gap-0.5 rounded p-0.5 border border-border-subtle"
          style={{ background: "var(--color-surface-2)" }}
        >
          {(["1m", "5m", "15m", "1h", "4h", "D"] as Timeframe[]).map((t) => {
            const active = tf === t;
            return (
              <button
                key={t}
                onClick={() => setTf(t)}
                className="font-mono text-[10px] px-2.5 py-1 rounded transition-colors"
                style={{
                  background: active ? "var(--color-surface-3)" : "transparent",
                  color: active
                    ? "var(--color-text-primary)"
                    : "var(--color-text-muted)",
                }}
              >
                {t}
              </button>
            );
          })}
        </div>

        <div className="ml-auto text-right">
          <div
            className="font-mono text-text-primary"
            style={{ fontSize: "22px", fontWeight: 500 }}
          >
            ${last.toFixed(2)}
          </div>
          <div
            className="font-mono mt-0.5"
            style={{
              fontSize: "12px",
              color:
                chg >= 0
                  ? "var(--color-bullish-text)"
                  : "var(--color-bearish-text)",
            }}
          >
            {chg >= 0 ? "+" : ""}
            {chg.toFixed(2)}% · today
          </div>
        </div>
      </div>

      {/* Canvas */}
      <div
        className="flex-1 relative chart-grid-bg overflow-hidden"
        style={{ minHeight: 320 }}
      >
        {ohlcv && ohlcv.length > 0 ? (
          <CandlestickChart
            data={ohlcv}
            levels={levels ?? []}
            entry={scan?.entry ?? undefined}
            stop={scan?.stop ?? undefined}
            target={scan?.target_1 ?? undefined}
            height={0}
            indicators={[
              { key: "ema9", color: "#f4d08a" },
              { key: "sma20", color: "#8ab4d4" },
              { key: "vwap", color: "#b892c9" },
            ]}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.14em] text-text-muted">
            loading chart…
          </div>
        )}

        {/* Annotation callout */}
        {scan?.pattern && (
          <div
            className="absolute top-4 right-4 max-w-[200px] font-serif italic text-text-secondary px-2.5 py-1.5 rounded border border-border-subtle z-10"
            style={{
              background: "var(--color-surface-0)",
              fontSize: "11px",
              lineHeight: 1.3,
            }}
          >
            {scan.action_label || scan.pattern}
          </div>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Right: Inspector
// ──────────────────────────────────────────────────────────────

function Inspector({
  symbol,
  scan,
}: {
  symbol: string;
  scan?: SignalResult;
}) {
  const { mutate: openTrade, isPending } = useOpenRealTrade();

  const thesis = scan?.action_label
    ? scan.action_label
    : `${symbol} — ${scan?.pattern || "setup"} forming. Wait for confirmation before size.`;

  const conviction = scan ? (scan.score >= 80 ? 4 : scan.score >= 60 ? 3 : 2) : 2;
  const risk =
    scan?.entry && scan?.stop
      ? `${(((scan.entry - scan.stop) / scan.entry) * 100).toFixed(1)}%`
      : "—";
  const rr =
    scan?.entry && scan?.stop && scan?.target_1
      ? ((scan.target_1 - scan.entry) / Math.abs(scan.entry - scan.stop)).toFixed(1) +
        "R"
      : scan?.rr_ratio
      ? scan.rr_ratio.toFixed(1) + "R"
      : "—";

  const confluence = [
    { label: `${scan?.pattern || "Pattern"} forming`, ok: !!scan?.pattern },
    { label: "Above 20-EMA", ok: !!scan?.ma20 && !!scan?.close && scan.close > scan.ma20 },
    { label: "Above 50-EMA", ok: !!scan?.ma50 && !!scan?.close && scan.close > scan.ma50 },
    { label: "Near support", ok: !!scan?.near_support },
    { label: "R:R ≥ 2.0", ok: (scan?.rr_ratio ?? 0) >= 2 },
    { label: "Support/resistance context", ok: !!scan?.nearest_support },
    { label: "Macro calendar clear", ok: false },
  ];

  return (
    <div className="flex flex-col overflow-y-auto bg-surface-0 min-w-0">
      {/* Thesis */}
      <div className="px-5 py-4 border-b border-border-subtle">
        <div className="flex items-center justify-between mb-2.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted font-semibold">
            Thesis
          </div>
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
                className={`conv-dot ${i < conviction ? "filled" : "empty"}`}
              />
            ))}
            <span className="ml-1">{conviction}/4</span>
          </span>
        </div>
        <p
          className="font-serif italic text-text-primary"
          style={{
            fontSize: "13px",
            lineHeight: 1.55,
            textWrap: "pretty" as never,
          }}
        >
          {thesis}
        </p>
      </div>

      {/* Plan */}
      <div className="px-5 py-4 border-b border-border-subtle">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted font-semibold mb-2.5">
          Plan
        </div>
        <dl
          className="grid gap-y-1.5 gap-x-3 font-mono"
          style={{
            gridTemplateColumns: "1fr auto",
            fontSize: "11.5px",
          }}
        >
          <KvRow label="Entry" value={scan?.entry ? `$${scan.entry.toFixed(2)}` : "—"} />
          <KvRow
            label="Stop"
            value={scan?.stop ? `$${scan.stop.toFixed(2)}` : "—"}
            tone="down"
          />
          <KvRow
            label="Target 1"
            value={scan?.target_1 ? `$${scan.target_1.toFixed(2)}` : "—"}
            tone="up"
          />
          <KvRow
            label="Target 2"
            value={scan?.target_2 ? `$${scan.target_2.toFixed(2)}` : "—"}
            tone="up"
          />
          <KvRow label="Risk" value={risk} />
          <KvRow label="R : R" value={rr} />
          <KvRow label="Size" value="—" />
        </dl>
      </div>

      {/* Confluence */}
      <div className="px-5 py-4 border-b border-border-subtle">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted font-semibold mb-2.5">
          Confluence
        </div>
        <div className="flex flex-col gap-1.5">
          {confluence.map((c, i) => (
            <div
              key={i}
              className="flex items-center gap-2 text-[12px] text-text-secondary"
            >
              <span
                className="inline-flex items-center justify-center rounded"
                style={{
                  width: 14,
                  height: 14,
                  background: c.ok
                    ? "var(--color-bullish-muted)"
                    : "var(--color-surface-3)",
                  color: c.ok
                    ? "var(--color-bullish-text)"
                    : "var(--color-text-faint)",
                  fontSize: 10,
                }}
              >
                {c.ok ? "✓" : "—"}
              </span>
              {c.label}
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="px-5 py-4">
        <div className="flex gap-2">
          <button
            disabled={!scan?.entry || isPending}
            onClick={() =>
              scan?.entry &&
              openTrade({
                symbol,
                direction: scan.direction,
                entry_price: scan.entry,
                stop_price: scan.stop ?? undefined,
                target_price: scan.target_1 ?? undefined,
                shares: 10,
              })
            }
            className="flex-1 px-3.5 py-2 rounded-md font-medium text-[12px] transition-colors disabled:opacity-60"
            style={{
              background: "var(--color-accent)",
              color: "var(--color-surface-0)",
            }}
          >
            {isPending ? "Opening…" : "Execute"}
          </button>
          <button className="px-3.5 py-2 rounded-md font-medium text-[12px] text-text-secondary border border-border-subtle hover:bg-surface-2 hover:text-text-primary transition-colors">
            Paper
          </button>
        </div>
      </div>
    </div>
  );
}

function KvRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
}) {
  const color =
    tone === "up"
      ? "var(--color-bullish-text)"
      : tone === "down"
      ? "var(--color-bearish-text)"
      : "var(--color-text-primary)";
  return (
    <>
      <dt className="text-text-muted uppercase tracking-[0.1em] text-[10px]">
        {label}
      </dt>
      <dd
        className="text-right font-medium"
        style={{ color, fontSize: "11.5px" }}
      >
        {value}
      </dd>
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────

export default function TradingPageV2() {
  const [params, setParams] = useSearchParams();
  const { data: scan } = useScanner();
  const { data: activeEntries } = useActiveEntries();

  // Seed selected symbol from URL, or first scan result, or first active entry.
  const initialSym =
    params.get("symbol") ||
    scan?.[0]?.symbol ||
    activeEntries?.[0]?.symbol ||
    "SPY";
  const [selected, setSelected] = useState<string>(initialSym);
  const [tf, setTf] = useState<Timeframe>("5m");

  useEffect(() => {
    const fromUrl = params.get("symbol");
    if (fromUrl && fromUrl !== selected) setSelected(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const selectSymbol = (sym: string) => {
    setSelected(sym);
    const next = new URLSearchParams(params);
    next.set("symbol", sym);
    setParams(next, { replace: true });
  };

  const scanRow = scan?.find((s) => s.symbol === selected);

  return (
    <div
      className="h-full grid overflow-hidden"
      style={{
        gridTemplateColumns: "minmax(240px, 260px) 1fr minmax(280px, 300px)",
      }}
    >
      <Scanner selected={selected} onSelect={selectSymbol} />
      <ChartPane symbol={selected} scan={scanRow} tf={tf} setTf={setTf} />
      <Inspector symbol={selected} scan={scanRow} />
    </div>
  );
}
