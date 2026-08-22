/** Daily Target — self-reporting discipline page (gated to one account for now).
 *
 * Top: today's scoreboard (realized vs target) + close-the-day. Middle: log/edit a trade.
 * Bottom: full history grouped into weeks → collapsible day panes → trades you can expand
 * (note + chart), edit, or delete — even after a day is closed. */

import { useState, useMemo, useEffect, Fragment } from "react";
import { Plus, Trash2, Lock, Check, Pencil, Image as ImageIcon, X, ChevronRight } from "lucide-react";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import {
  useDailySummary,
  useDailyHistory,
  useSetDailyTarget,
  useAddDailyTrade,
  useUpdateDailyTrade,
  useDeleteDailyTrade,
  useCloseDay,
  useReopenDay,
  useMasterSymbols,
  useWatchlist,
  useTradeImage,
  type DailyTradeInput,
  type DailyTradeRow,
  type DailyDay,
} from "../api/hooks";

const OWNER_EMAIL = "vbolofinde@gmail.com";

const SETUPS = [
  "PDH break",
  "PDL held",
  "PDL reclaim",
  "8 SMA reclaim",
  "21 SMA reclaim",
  "50 SMA support",
  "100 SMA support",
  "200 SMA support",
  "Level reclaim",
  "Level reject",
  "Weekly breakout (PWH)",
  "Monthly breakout (PMH)",
  "Open bracket",
  "Gap and go",
  "Pivot breakout",
  "Other",
];

const EXIT_REASONS = [
  "Target hit",
  "Stop",
  "Into resistance",
  "Give-back / trailed out",
  "Time cutoff",
  "Changed mind",
  "Other",
];

const usd = (n: number) =>
  (n < 0 ? "-" : "") +
  Math.abs(n).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// Parse a YYYY-MM-DD string as a LOCAL date (avoids UTC off-by-one).
function parseDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function mondayOf(s: string): string {
  const dt = parseDate(s);
  const back = (dt.getDay() + 6) % 7; // days since Monday
  dt.setDate(dt.getDate() - back);
  const mm = String(dt.getMonth() + 1).padStart(2, "0");
  const dd = String(dt.getDate()).padStart(2, "0");
  return `${dt.getFullYear()}-${mm}-${dd}`;
}
const fmtDay = (s: string) =>
  parseDate(s).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
const fmtWeek = (s: string) =>
  "Week of " + parseDate(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });

// Downscale + compress a screenshot to a small JPEG data URL so it fits in a DB text column.
async function fileToCompressedDataUrl(file: File, maxDim = 1400, quality = 0.7): Promise<string> {
  const dataUrl: string = await new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result as string);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
  const img: HTMLImageElement = await new Promise((res, rej) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = rej;
    i.src = dataUrl;
  });
  let w = img.width;
  let h = img.height;
  if (Math.max(w, h) > maxDim) {
    const s = maxDim / Math.max(w, h);
    w = Math.round(w * s);
    h = Math.round(h * s);
  }
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return dataUrl;
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/jpeg", quality);
}

// Expandable review row — note + lazily-loaded chart screenshot.
function TradeDetailRow({ trade, colSpan }: { trade: DailyTradeRow; colSpan: number }) {
  const { data } = useTradeImage(trade.id, !!trade.has_image);
  return (
    <tr>
      <td colSpan={colSpan} className="bg-surface-2/40 px-4 py-3">
        {trade.note && (
          <div className="mb-2 whitespace-pre-wrap text-[13px] leading-relaxed text-text-secondary">{trade.note}</div>
        )}
        {trade.has_image &&
          (data?.chart_image ? (
            <a href={data.chart_image} target="_blank" rel="noreferrer">
              <img src={data.chart_image} alt="chart" className="max-h-96 rounded-lg border border-border-subtle" />
            </a>
          ) : (
            <div className="text-[12px] text-text-faint">Loading chart…</div>
          ))}
        {!trade.note && !trade.has_image && <div className="text-[12px] text-text-faint">No note or chart.</div>}
      </td>
    </tr>
  );
}

// One day's trades as a table (used inside each day pane).
function DayTrades({
  trades,
  expandedId,
  setExpandedId,
  onEdit,
  onDelete,
}: {
  trades: DailyTradeRow[];
  expandedId: number | null;
  setExpandedId: (id: number | null) => void;
  onEdit: (t: DailyTradeRow) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wide text-text-faint">
            <th className="text-left font-medium px-4 py-2.5">Symbol</th>
            <th className="text-left font-medium px-3 py-2.5">Setup</th>
            <th className="text-left font-medium px-3 py-2.5">Dir</th>
            <th className="text-right font-medium px-3 py-2.5">Entry</th>
            <th className="text-right font-medium px-3 py-2.5">Exit</th>
            <th className="text-right font-medium px-3 py-2.5">Size</th>
            <th className="text-right font-medium px-3 py-2.5">P/L</th>
            <th className="text-left font-medium px-3 py-2.5">Exit</th>
            <th className="px-3 py-2.5"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle/40">
          {trades.map((t) => (
            <Fragment key={t.id}>
              <tr
                className="text-text-secondary cursor-pointer hover:bg-surface-2/30"
                onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
              >
                <td className="px-4 py-2.5">
                  <span className="font-mono font-semibold text-text-primary">{t.symbol}</span>
                  <span className="ml-1.5 text-[10px] uppercase text-text-faint">{t.instrument}</span>
                  {(t.note || t.has_image) && <span className="ml-1.5 text-[10px]">{t.has_image ? "🖼" : "📝"}</span>}
                </td>
                <td className="px-3 py-2.5">{t.setup || "—"}</td>
                <td className="px-3 py-2.5 uppercase text-[11px]">
                  {t.direction || "—"}
                  <span className="ml-1 lowercase text-text-faint">{t.trade_type === "swing" ? "· swing" : "· day"}</span>
                </td>
                <td className="px-3 py-2.5 text-right font-mono">{t.entry_price ?? "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono">{t.exit_price ?? "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono text-[12px] text-text-muted">
                  {t.quantity ?? "—"}
                  {t.position_size ? ` · ${usd(t.position_size)}` : ""}
                </td>
                <td
                  className={`px-3 py-2.5 text-right font-mono font-semibold ${
                    t.pnl < 0 ? "text-bearish-text" : "text-bullish-text"
                  }`}
                >
                  {usd(t.pnl)}
                </td>
                <td className="px-3 py-2.5 text-[12px]">{t.exit_reason || "—"}</td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onEdit(t);
                    }}
                    className="text-text-faint hover:text-accent"
                    aria-label="Edit trade"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(t.id);
                    }}
                    className="ml-3 text-text-faint hover:text-bearish-text"
                    aria-label="Delete trade"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
              {expandedId === t.id && <TradeDetailRow trade={t} colSpan={9} />}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DailyTargetPage() {
  const user = useAuthStore((s) => s.user);
  const isOwner = (user?.email || "").toLowerCase() === OWNER_EMAIL;

  const { data: summary } = useDailySummary();
  const { data: history } = useDailyHistory();
  const setTarget = useSetDailyTarget();
  const addTrade = useAddDailyTrade();
  const updateTrade = useUpdateDailyTrade();
  const delTrade = useDeleteDailyTrade();
  const closeDay = useCloseDay();
  const reopenDay = useReopenDay();

  const { data: master } = useMasterSymbols();
  const { data: myWl } = useWatchlist();
  const symbolOptions = useMemo(() => {
    const set = new Set<string>();
    (master?.symbols ?? []).forEach((s) => set.add(s));
    (myWl ?? []).forEach((w) => set.add(w.symbol));
    return Array.from(set).sort();
  }, [master, myWl]);

  // trade form
  const [editingId, setEditingId] = useState<number | null>(null);
  const [symbol, setSymbol] = useState("");
  const [instrument, setInstrument] = useState("stock");
  const [tradeType, setTradeType] = useState("day");
  const [setup, setSetup] = useState(SETUPS[0]);
  const [direction, setDirection] = useState("long");
  const [entry, setEntry] = useState("");
  const [exit, setExit] = useState("");
  const [qty, setQty] = useState("");
  const [size, setSize] = useState("");
  const [pnl, setPnl] = useState("");
  const [pnlEdited, setPnlEdited] = useState(false);
  const [sizeEdited, setSizeEdited] = useState(false);
  const [exitReason, setExitReason] = useState(EXIT_REASONS[0]);
  const [note, setNote] = useState("");
  const [chartImage, setChartImage] = useState("");

  // target editor + row expand + day panes
  const [editingTarget, setEditingTarget] = useState(false);
  const [targetDraft, setTargetDraft] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [openDays, setOpenDays] = useState<Record<string, boolean>>({});

  // Paste a screenshot anywhere on the page (⌘V / Ctrl+V) → attaches it to the form.
  useEffect(() => {
    const onPaste = async (e: ClipboardEvent) => {
      const item = e.clipboardData && Array.from(e.clipboardData.items).find((i) => i.type.startsWith("image/"));
      const f = item ? item.getAsFile() : null;
      if (f) setChartImage(await fileToCompressedDataUrl(f));
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, []);

  const _num = (s: string) => (s.trim() === "" ? null : Number(s));
  const computedPnl = useMemo(() => {
    const e = _num(entry);
    const x = _num(exit);
    const q = _num(qty);
    if (e === null || x === null || q === null || Number.isNaN(e) || Number.isNaN(x) || Number.isNaN(q)) return null;
    const mult = instrument === "option" ? 100 : 1;
    const dir = direction === "short" ? -1 : 1;
    return Math.round((x - e) * q * mult * dir * 100) / 100;
  }, [entry, exit, qty, instrument, direction]);
  const effectivePnl = pnlEdited ? pnl : computedPnl !== null ? String(computedPnl) : "";
  const computedSize = useMemo(() => {
    const e = _num(entry);
    const q = _num(qty);
    if (e === null || q === null || Number.isNaN(e) || Number.isNaN(q)) return null;
    const mult = instrument === "option" ? 100 : 1;
    return Math.round(Math.abs(e * q * mult) * 100) / 100;
  }, [entry, qty, instrument]);
  const effectiveSize = sizeEdited ? size : computedSize !== null ? String(computedSize) : "";

  if (!isOwner) {
    return (
      <div className="h-full overflow-y-auto overflow-x-hidden p-5">
        <div className="max-w-5xl mx-auto">
          <div className="bg-surface-1 border border-border-subtle rounded-xl p-6 text-center text-text-muted">
            This page isn't enabled for your account.
          </div>
        </div>
      </div>
    );
  }

  const target = summary?.target ?? 4000;
  const total = summary?.total_pnl ?? 0;
  const hit = summary?.hit ?? false;
  const closed = summary?.closed ?? false;
  const pct = target > 0 ? Math.max(0, Math.min(100, (total / target) * 100)) : 0;
  const todayStr = summary?.date;

  const resetForm = () => {
    setEditingId(null);
    setSymbol("");
    setInstrument("stock");
    setTradeType("day");
    setSetup(SETUPS[0]);
    setDirection("long");
    setEntry("");
    setExit("");
    setQty("");
    setSize("");
    setPnl("");
    setPnlEdited(false);
    setSizeEdited(false);
    setExitReason(EXIT_REASONS[0]);
    setNote("");
    setChartImage("");
  };

  const submitTrade = (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || effectivePnl.trim() === "") return;
    const body: DailyTradeInput = {
      symbol: symbol.trim().toUpperCase(),
      instrument,
      trade_type: tradeType,
      setup,
      direction,
      entry_price: entry.trim() === "" ? null : Number(entry),
      exit_price: exit.trim() === "" ? null : Number(exit),
      quantity: qty.trim() === "" ? null : Number(qty),
      position_size: effectiveSize.trim() === "" ? null : Number(effectiveSize),
      pnl: Number(effectivePnl),
      exit_reason: exitReason,
      note: note.trim() || null,
      chart_image: chartImage || null,
    };
    if (editingId) {
      updateTrade.mutate({ id: editingId, body }, { onSuccess: resetForm });
    } else {
      addTrade.mutate(body, { onSuccess: resetForm });
    }
  };

  const startEdit = async (t: DailyTradeRow) => {
    setEditingId(t.id);
    setSymbol(t.symbol);
    setInstrument(t.instrument || "stock");
    setTradeType(t.trade_type || "day");
    setSetup(t.setup || SETUPS[0]);
    setDirection(t.direction || "long");
    setEntry(t.entry_price != null ? String(t.entry_price) : "");
    setExit(t.exit_price != null ? String(t.exit_price) : "");
    setQty(t.quantity != null ? String(t.quantity) : "");
    setSize(t.position_size != null ? String(t.position_size) : "");
    setSizeEdited(true);
    setPnl(String(t.pnl));
    setPnlEdited(true);
    setExitReason(t.exit_reason || EXIT_REASONS[0]);
    setNote(t.note || "");
    setChartImage("");
    if (t.has_image) {
      try {
        const img = await api.get<{ chart_image: string | null }>(`/daily/trade/${t.id}/image`);
        setChartImage(img.chart_image || "");
      } catch {
        /* ignore */
      }
    }
  };

  const handleImageFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setChartImage(await fileToCompressedDataUrl(f));
    e.target.value = "";
  };

  const inputCls =
    "rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none disabled:opacity-50";

  // group history days into weeks (preserving the desc order the API returns)
  const weeks = useMemo(() => {
    const days = history?.days ?? [];
    const order: string[] = [];
    const map: Record<string, DailyDay[]> = {};
    for (const d of days) {
      const wk = mondayOf(d.date);
      if (!map[wk]) {
        map[wk] = [];
        order.push(wk);
      }
      map[wk].push(d);
    }
    return order.map((wk) => {
      const wdays = map[wk];
      return {
        week: wk,
        days: wdays,
        total: Math.round(wdays.reduce((a, d) => a + d.total_pnl, 0) * 100) / 100,
        hitDays: wdays.filter((d) => d.hit).length,
        wins: wdays.reduce((a, d) => a + d.wins, 0),
        losses: wdays.reduce((a, d) => a + d.losses, 0),
      };
    });
  }, [history]);

  const isDayOpen = (date: string) => openDays[date] ?? date === todayStr;

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-5">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div>
          <h1 className="font-display text-xl font-bold text-text-primary">Daily Target</h1>
          <p className="mt-1 text-[11px] text-text-faint">{todayStr ?? "today"} · make your number, then stop</p>
        </div>

        {/* Scoreboard (today) */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-5 space-y-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-text-faint">Realized today</div>
              <div className={`font-display text-4xl font-bold ${total < 0 ? "text-bearish-text" : "text-bullish-text"}`}>
                {usd(total)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-wide text-text-faint">Target</div>
              {editingTarget ? (
                <div className="flex items-center gap-1.5 mt-1">
                  <input
                    autoFocus
                    type="number"
                    value={targetDraft}
                    onChange={(e) => setTargetDraft(e.target.value)}
                    className={`${inputCls} w-28 text-right`}
                  />
                  <button
                    onClick={() => {
                      const v = Number(targetDraft);
                      if (!Number.isNaN(v) && v >= 0) setTarget.mutate(v);
                      setEditingTarget(false);
                    }}
                    className="inline-flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-2 text-[13px] font-semibold text-accent hover:bg-accent/20"
                  >
                    <Check className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setTargetDraft(String(target));
                    setEditingTarget(true);
                  }}
                  className="inline-flex items-center gap-1.5 font-display text-2xl font-bold text-text-primary hover:text-accent"
                >
                  {usd(target)}
                  <Pencil className="h-3.5 w-3.5 text-text-faint" />
                </button>
              )}
            </div>
          </div>

          <div>
            <div className="h-2.5 w-full rounded-full bg-surface-3 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${hit ? "bg-bullish" : total < 0 ? "bg-bearish" : "bg-accent"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-2 flex items-center gap-4 text-[11px] text-text-faint">
              <span>{summary?.trade_count ?? 0} trades</span>
              <span className="text-bullish-text">{summary?.wins ?? 0}W</span>
              <span className="text-bearish-text">{summary?.losses ?? 0}L</span>
              <span className="ml-auto">{Math.round(pct)}% of target</span>
            </div>
          </div>

          {closed ? (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
              <div className="flex items-center gap-2 text-text-primary font-semibold">
                <Lock className="h-4 w-4 text-text-muted" /> Day closed — done trading.
              </div>
              <button
                onClick={() => reopenDay.mutate()}
                className="rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary"
              >
                Reopen
              </button>
            </div>
          ) : (
            <div
              className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 ${
                hit ? "border-bullish/30 bg-bullish/10" : "border-border-subtle bg-surface-2"
              }`}
            >
              <div className={`font-semibold ${hit ? "text-bullish-text" : "text-text-secondary"}`}>
                {hit ? "🎯 Target hit — close the day. Don't give it back." : `${usd(Math.max(0, target - total))} to go`}
              </div>
              <button
                onClick={() => closeDay.mutate()}
                className={`rounded-lg px-3.5 py-2 text-[13px] font-semibold transition-colors ${
                  hit
                    ? "border border-bullish/40 bg-bullish/20 text-bullish-text hover:bg-bullish/30"
                    : "border border-border-subtle bg-surface-3 text-text-secondary hover:text-text-primary"
                }`}
              >
                Close the day
              </button>
            </div>
          )}
        </div>

        {/* Log / edit a trade — always available (edit even on a closed day) */}
        <form
          onSubmit={submitTrade}
          className={`rounded-xl border p-5 space-y-3 ${editingId ? "border-accent/50 bg-accent/5" : "border-border-subtle bg-surface-1"}`}
        >
          <div className="flex items-center justify-between">
            <div className="font-semibold text-text-primary">{editingId ? "Edit trade" : "Log a trade"}</div>
            {editingId && (
              <button type="button" onClick={resetForm} className="text-xs text-text-faint hover:text-text-primary">
                Cancel edit
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <input
              className={`${inputCls} font-mono uppercase`}
              placeholder="Symbol"
              list="daily-symbols"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
            <datalist id="daily-symbols">
              {symbolOptions.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
            <select className={inputCls} value={instrument} onChange={(e) => setInstrument(e.target.value)}>
              <option value="stock">Stock</option>
              <option value="option">Option</option>
            </select>
            <select className={inputCls} value={tradeType} onChange={(e) => setTradeType(e.target.value)}>
              <option value="day">Day</option>
              <option value="swing">Swing</option>
            </select>
            <select className={inputCls} value={setup} onChange={(e) => setSetup(e.target.value)}>
              {SETUPS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select className={inputCls} value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
            <input
              className={inputCls}
              type="number"
              step="any"
              placeholder="Entry"
              value={entry}
              onChange={(e) => setEntry(e.target.value)}
            />
            <input
              className={inputCls}
              type="number"
              step="any"
              placeholder="Exit"
              value={exit}
              onChange={(e) => setExit(e.target.value)}
            />
            <input
              className={inputCls}
              type="number"
              step="any"
              placeholder={instrument === "option" ? "Contracts" : "Shares"}
              value={qty}
              onChange={(e) => setQty(e.target.value)}
            />
            <input
              className={`${inputCls} ${!sizeEdited && computedSize !== null ? "text-text-secondary" : ""}`}
              type="number"
              step="any"
              placeholder="Size $ (auto)"
              value={effectiveSize}
              onChange={(e) => {
                setSize(e.target.value);
                setSizeEdited(true);
              }}
              title={!sizeEdited && computedSize !== null ? "Capital deployed = entry × qty (×100 for options) — type to override" : ""}
            />
            <input
              className={`${inputCls} font-semibold ${!pnlEdited && computedPnl !== null ? "text-bullish-text" : ""}`}
              type="number"
              step="any"
              placeholder="P/L $ (auto)"
              value={effectivePnl}
              onChange={(e) => {
                setPnl(e.target.value);
                setPnlEdited(true);
              }}
              title={!pnlEdited && computedPnl !== null ? "Auto from entry, exit & size — type to override" : ""}
            />
            <select className={inputCls} value={exitReason} onChange={(e) => setExitReason(e.target.value)}>
              {EXIT_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <textarea
            className={`${inputCls} w-full`}
            rows={2}
            placeholder="Note — your thought process (optional). Tip: take a screenshot and paste it (⌘V) anywhere on this page."
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-[13px] text-text-secondary hover:text-text-primary">
                <ImageIcon className="h-4 w-4" /> Attach chart (or paste ⌘V)
                <input type="file" accept="image/*" className="hidden" onChange={handleImageFile} />
              </label>
              {chartImage && (
                <div className="flex items-center gap-2">
                  <img src={chartImage} alt="chart preview" className="h-10 rounded border border-border-subtle" />
                  <button
                    type="button"
                    onClick={() => setChartImage("")}
                    className="text-text-faint hover:text-bearish-text"
                    aria-label="Remove chart"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
            <button
              type="submit"
              disabled={addTrade.isPending || updateTrade.isPending || !symbol.trim() || effectivePnl.trim() === ""}
              className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-[13px] font-semibold text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
            >
              {editingId ? (
                <>
                  <Check className="h-4 w-4" /> Save changes
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" /> Add trade
                </>
              )}
            </button>
          </div>
        </form>

        {/* History — weeks → collapsible day panes → trades */}
        {weeks.length === 0 ? (
          <div className="bg-surface-1 border border-border-subtle rounded-xl p-5 text-sm text-text-muted">
            No trades logged yet.
          </div>
        ) : (
          weeks.map((wk) => (
            <div key={wk.week} className="space-y-2">
              <div className="flex items-center justify-between px-1 pt-2">
                <div className="text-[12px] font-semibold uppercase tracking-wide text-text-muted">{fmtWeek(wk.week)}</div>
                <div className="flex items-center gap-3 text-[12px]">
                  <span className={`font-mono font-semibold ${wk.total < 0 ? "text-bearish-text" : "text-bullish-text"}`}>
                    {usd(wk.total)}
                  </span>
                  <span className="text-text-faint">
                    {wk.hitDays}/{wk.days.length} days hit · {wk.wins}W {wk.losses}L
                  </span>
                </div>
              </div>
              {wk.days.map((d) => {
                const open = isDayOpen(d.date);
                return (
                  <div key={d.date} className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
                    <button
                      onClick={() => setOpenDays((o) => ({ ...o, [d.date]: !open }))}
                      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-2/30"
                    >
                      <ChevronRight
                        className={`h-4 w-4 text-text-faint transition-transform ${open ? "rotate-90" : ""}`}
                      />
                      <span className="font-semibold text-text-primary">{fmtDay(d.date)}</span>
                      {d.closed && <Lock className="h-3 w-3 text-text-faint" />}
                      <span className={`ml-auto font-mono font-semibold ${d.total_pnl < 0 ? "text-bearish-text" : "text-bullish-text"}`}>
                        {usd(d.total_pnl)}
                      </span>
                      <span className="text-[11px] text-text-faint">
                        {d.trade_count} · {d.wins}W {d.losses}L
                      </span>
                    </button>
                    {open &&
                      (d.trades.length === 0 ? (
                        <div className="px-4 py-3 text-[12px] text-text-faint border-t border-border-subtle">No trades this day.</div>
                      ) : (
                        <div className="border-t border-border-subtle">
                          <DayTrades
                            trades={d.trades}
                            expandedId={expandedId}
                            setExpandedId={setExpandedId}
                            onEdit={startEdit}
                            onDelete={(id) => delTrade.mutate(id)}
                          />
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
