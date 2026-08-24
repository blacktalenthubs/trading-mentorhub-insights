/** Daily Target — self-reporting discipline page (gated to one account for now).
 *
 * Top: today's scoreboard (realized vs target) + close-the-day. Middle: log/edit a trade.
 * Bottom: full history grouped into weeks → collapsible day panes → trades you can expand
 * (note + chart), edit, or delete — even after a day is closed. */

import { useState, useMemo, useEffect, useRef, Fragment } from "react";
import { Plus, Trash2, Lock, Check, Pencil, Image as ImageIcon, X, ChevronRight, ClipboardPaste } from "lucide-react";
import { useAuthStore } from "../stores/auth";
import { api } from "../api/client";
import { toast } from "../components/Toast";
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

const STRUCTURES = [
  "",
  "8 SMA",
  "21 SMA",
  "50 SMA",
  "100 SMA",
  "200 SMA",
  "PDH",
  "PDL",
  "PWH",
  "PWL",
  "PWC",
  "PMH",
  "PML",
  "PMC",
  "PQH",
  "PQL",
  "PQC",
  "All-time high",
  "All-time low",
  "Pivot",
  "Range high",
  "Range low",
  "Prior high",
  "Prior low",
  "VWAP",
  "Open",
  "Other",
];

// Exit reason = the OUTCOME. WHICH level you hit lives in the Target / Stop structure fields
// (so "Hit target" + Target=50 SMA is fully specified — no vague "into resistance").
const EXIT_REASONS = [
  "Hit target",
  "Hit stop",
  "Trailed / gave back",
  "Time cutoff",
  "Changed mind",
  "Other",
];

const usd = (n: number) =>
  (n < 0 ? "-" : "") +
  Math.abs(n).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

// Return on the capital that was actually deployed: P/L ÷ position size. That's the honest
// number across instruments — a $400 option win on $2k risked is +20%, the same $400 on a
// $60k stock position is +0.7%. Falls back to the raw price move (direction-aware) when no
// size was logged. Open trades have no realized return → null.
const pctReturn = (t: DailyTradeRow): number | null => {
  if (t.is_open) return null;
  const size = t.position_size ?? 0;
  if (size > 0) return Math.round((t.pnl / size) * 1000) / 10;
  const e = t.entry_price;
  const x = t.exit_price;
  if (e == null || x == null || e === 0) return null;
  const dir = t.direction === "short" ? -1 : 1;
  return Math.round(((x - e) / Math.abs(e)) * dir * 1000) / 10;
};
const pctStr = (p: number) => (p >= 0 ? "+" : "") + p.toFixed(1) + "%";

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
async function fileToCompressedDataUrl(file: File, maxDim = 2560, quality = 0.85): Promise<string> {
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
function TradeDetail({ trade, onView }: { trade: DailyTradeRow; onView: (src: string) => void }) {
  const { data } = useTradeImage(trade.id, !!trade.has_image);
  return (
    <div className="space-y-3 border-t border-border-subtle bg-surface-2/40 px-4 py-4">
      {trade.note && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Note</div>
          <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-text-secondary">{trade.note}</div>
        </div>
      )}
      {trade.has_image && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-text-faint">Chart · click to view full screen</div>
          {data?.chart_image ? (
            <button type="button" onClick={() => onView(data.chart_image!)} className="block w-full">
              <img
                src={data.chart_image}
                alt="chart"
                className="max-h-80 w-full cursor-zoom-in rounded-lg border border-border-subtle object-contain transition hover:ring-2 hover:ring-accent/40"
              />
            </button>
          ) : (
            <div className="text-[12px] text-text-faint">Loading chart…</div>
          )}
        </div>
      )}
      {!trade.note && !trade.has_image && (
        <div className="text-[12px] text-text-faint">No note or chart — click Edit to add one.</div>
      )}
    </div>
  );
}

// Sortable column header for the desktop trade table.
function Th({
  label,
  k,
  sortKey,
  sortDir,
  onSort,
  align = "left",
}: {
  label: string;
  k: string;
  sortKey: string | null;
  sortDir: "asc" | "desc";
  onSort: (k: string) => void;
  align?: "left" | "right";
}) {
  const active = sortKey === k;
  return (
    <th className={`px-3 py-2.5 font-medium ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        onClick={() => onSort(k)}
        className={`inline-flex items-center gap-1 ${align === "right" ? "flex-row-reverse" : ""} ${active ? "text-accent" : "hover:text-text-secondary"}`}
      >
        {label}
        <span className="text-[9px]">{active ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span>
      </button>
    </th>
  );
}

// One day's / one setup's trades: a SORTABLE table on desktop, cards on mobile. Row expands to note + chart.
function DayTrades({
  trades,
  expandedId,
  setExpandedId,
  onEdit,
  onDelete,
  onView,
}: {
  trades: DailyTradeRow[];
  expandedId: number | null;
  setExpandedId: (id: number | null) => void;
  onEdit: (t: DailyTradeRow) => void;
  onDelete: (id: number) => void;
  onView: (src: string) => void;
}) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const onSort = (k: string) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "symbol" || k === "setup" || k === "dir" || k === "reason" ? "asc" : "desc");
    }
  };
  const sorted = useMemo(() => {
    if (!sortKey) return trades;
    const val = (t: DailyTradeRow): string | number => {
      switch (sortKey) {
        case "when": return t.created_at ?? "";
        case "symbol": return t.symbol ?? "";
        case "instrument": return t.instrument ?? "";
        case "setup": return t.setup ?? "";
        case "dir": return t.direction ?? "";
        case "entry": return t.entry_price ?? -Infinity;
        case "exit": return t.exit_price ?? -Infinity;
        case "size": return t.position_size ?? -Infinity;
        case "pnl": return t.pnl;
        case "reason": return t.exit_reason ?? "";
        case "target": return t.target ?? "";
        case "stop": return t.stop ?? "";
        default: return 0;
      }
    };
    return [...trades].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
      return sortDir === "asc" ? c : -c;
    });
  }, [trades, sortKey, sortDir]);
  const fmtWhen = (s: string | null) =>
    s ? new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";
  const COLS = 14;
  return (
    <div>
      {/* Desktop — sortable table (click a header to sort; click a row to expand note + chart) */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wide text-text-faint">
              <Th label="When" k="when" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Symbol" k="symbol" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Type" k="instrument" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Setup" k="setup" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Dir" k="dir" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Entry" k="entry" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
              <Th label="Exit" k="exit" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
              <Th label="Size" k="size" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
              <Th label="P/L" k="pnl" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
              <Th label="Exit" k="reason" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Target" k="target" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <Th label="Stop" k="stop" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
              <th className="px-3 py-2.5 text-center font-medium">Chart</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle/40">
            {sorted.map((t) => {
              const open = expandedId === t.id;
              const ret = pctReturn(t);
              return (
                <Fragment key={t.id}>
                  <tr
                    className="cursor-pointer text-text-secondary hover:bg-surface-2/30"
                    onClick={() => setExpandedId(open ? null : t.id)}
                  >
                    <td className="whitespace-nowrap px-3 py-2.5 text-[12px] text-text-faint">{fmtWhen(t.created_at)}</td>
                    <td className="px-3 py-2.5">
                      <span className="font-mono font-semibold text-text-primary">{t.symbol}</span>
                      {t.is_open && (
                        <span className="ml-1 rounded bg-accent/15 px-1 text-[9px] font-semibold uppercase text-accent">
                          open
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] uppercase text-text-muted">{t.instrument}</td>
                    <td className="px-3 py-2.5 text-[12px]">{t.setup || "—"}</td>
                    <td
                      className={`px-3 py-2.5 text-[11px] font-semibold uppercase ${
                        t.direction === "short" ? "text-bearish-text" : "text-bullish-text"
                      }`}
                    >
                      {t.direction || "—"}
                      <span className="ml-1 lowercase text-text-faint">{t.trade_type === "swing" ? "swing" : "day"}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono">{t.entry_price ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right font-mono">{t.exit_price ?? "—"}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-[12px] text-text-muted">
                      {t.position_size ? usd(t.position_size) : "—"}
                    </td>
                    <td
                      className={`px-3 py-2.5 text-right font-mono font-semibold ${
                        t.is_open ? "text-text-faint" : t.pnl < 0 ? "text-bearish-text" : "text-bullish-text"
                      }`}
                    >
                      {t.is_open ? "open" : usd(t.pnl)}
                      {ret !== null && (
                        <span className="block text-[10px] font-normal text-text-faint">{pctStr(ret)}</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-[12px]">{t.is_open ? "—" : t.exit_reason || "—"}</td>
                    <td className="px-3 py-2.5 text-[12px] text-text-muted">{t.target || "—"}</td>
                    <td className="px-3 py-2.5 text-[12px] text-text-muted">{t.stop || "—"}</td>
                    <td className="px-3 py-2.5 text-center">
                      {t.has_image ? "🖼" : t.note ? "📝" : <span className="text-text-faint/40">—</span>}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right">
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
                  {open && (
                    <tr>
                      <td colSpan={COLS} className="p-0">
                        <TradeDetail trade={t} onView={onView} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile — cards */}
      <ul className="divide-y divide-border-subtle/40 md:hidden">
        {sorted.map((t) => {
          const open = expandedId === t.id;
          const ret = pctReturn(t);
          return (
            <li key={t.id}>
              <button
                onClick={() => setExpandedId(open ? null : t.id)}
                className="w-full text-left px-4 py-3 hover:bg-surface-2/30"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="font-mono font-semibold text-text-primary">{t.symbol}</span>
                    <span className="text-[10px] uppercase text-text-faint">{t.instrument}</span>
                    <span
                      className={`text-[10px] font-semibold uppercase ${
                        t.direction === "short" ? "text-bearish-text" : "text-bullish-text"
                      }`}
                    >
                      {t.direction || ""}
                    </span>
                    {(t.note || t.has_image) && <span className="text-[10px]">{t.has_image ? "🖼" : "📝"}</span>}
                    {t.is_open && (<span className="rounded bg-accent/15 px-1 text-[9px] font-semibold uppercase text-accent">open</span>)}
                  </div>
                  <span className="shrink-0 text-right">
                    <span
                      className={`font-mono font-semibold ${t.is_open ? "text-text-faint" : t.pnl < 0 ? "text-bearish-text" : "text-bullish-text"}`}
                    >
                      {t.is_open ? "open" : usd(t.pnl)}
                    </span>
                    {ret !== null && (
                      <span className="block font-mono text-[10px] text-text-faint">{pctStr(ret)}</span>
                    )}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-text-faint">
                  <span>{t.setup || "—"}</span>
                  <span className="text-text-faint/50">·</span>
                  <span className="lowercase">{t.trade_type === "swing" ? "swing" : "day"}</span>
                  {(t.entry_price != null || t.exit_price != null) && (
                    <>
                      <span className="text-text-faint/50">·</span>
                      <span className="font-mono">
                        {t.entry_price ?? "—"} → {t.exit_price ?? "—"}
                      </span>
                    </>
                  )}
                  {t.position_size ? (
                    <>
                      <span className="text-text-faint/50">·</span>
                      <span className="font-mono">{usd(t.position_size)}</span>
                    </>
                  ) : null}
                  {!t.is_open && t.exit_reason ? (
                    <>
                      <span className="text-text-faint/50">·</span>
                      <span>{t.exit_reason}</span>
                    </>
                  ) : null}
                  {t.target ? (
                    <>
                      <span className="text-text-faint/50">·</span>
                      <span>🎯 {t.target}</span>
                    </>
                  ) : null}
                  {t.stop ? (
                    <>
                      <span className="text-text-faint/50">·</span>
                      <span>🛑 {t.stop}</span>
                    </>
                  ) : null}
                </div>
              </button>
              {open && (
                <div>
                  <TradeDetail trade={t} onView={onView} />
                  <div className="flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-2/40 px-4 py-2">
                    <button
                      onClick={() => onEdit(t)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-[12px] text-text-secondary hover:text-accent"
                    >
                      <Pencil className="h-3.5 w-3.5" /> Edit
                    </button>
                    <button
                      onClick={() => onDelete(t.id)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-[12px] text-text-secondary hover:text-bearish-text"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </button>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
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
  const [targetLevel, setTargetLevel] = useState(""); // structural target (level)
  const [stopLevel, setStopLevel] = useState(""); // structural stop (level)
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
  const [isOpen, setIsOpen] = useState(false); // still holding — open position (no exit / P/L yet)

  // target editor + row expand + day panes
  const [editingTarget, setEditingTarget] = useState(false);
  const [targetDraft, setTargetDraft] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [openDays, setOpenDays] = useState<Record<string, boolean>>({});
  const [dragOver, setDragOver] = useState(false);
  const [logOpen, setLogOpen] = useState(false); // the "Log a trade" form is collapsed by default (mobile-first)
  const [view, setView] = useState<"journal" | "patterns">("journal");
  const [patternSort, setPatternSort] = useState<"total" | "winrate" | "avg" | "count">("total");
  const [groupBy, setGroupBy] = useState<"setup" | "target" | "stop" | "instrument">("setup");
  const [instFilter, setInstFilter] = useState<"all" | "stock" | "option">("all"); // scope patterns to stocks / options
  const [openSetup, setOpenSetup] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null); // full-screen chart image src
  const [openBookOpen, setOpenBookOpen] = useState(false); // expand the open-positions allocation breakdown
  const formRef = useRef<HTMLFormElement>(null); // "Close" in the open book scrolls you here

  // Editing a trade opens the form (and scrolls it into view via the auto-expand).
  useEffect(() => {
    if (editingId) setLogOpen(true);
  }, [editingId]);

  // Esc closes the full-screen chart.
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  // Paste a screenshot anywhere on the page (⌘V / Ctrl+V) → attaches it to the form.
  useEffect(() => {
    const onPaste = async (e: ClipboardEvent) => {
      const dt = e.clipboardData;
      if (!dt) return;
      let file: File | null = null;
      for (const it of Array.from(dt.items || [])) {
        if (it.kind === "file" && it.type.startsWith("image/")) {
          file = it.getAsFile();
          break;
        }
      }
      if (!file && dt.files && dt.files.length) {
        for (const f of Array.from(dt.files)) {
          if (f.type.startsWith("image/")) {
            file = f;
            break;
          }
        }
      }
      if (file) {
        e.preventDefault();
        setChartImage(await fileToCompressedDataUrl(file));
        toast.success("Chart attached");
      }
    };
    window.addEventListener("paste", onPaste, true);
    return () => window.removeEventListener("paste", onPaste, true);
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
    setTargetLevel("");
    setStopLevel("");
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
    setIsOpen(false);
  };

  const submitTrade = (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || (!isOpen && effectivePnl.trim() === "")) return;
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
      pnl: isOpen ? 0 : Number(effectivePnl),
      note: note.trim() || null,
      chart_image: chartImage || null,
      is_open: isOpen,
      exit_reason: isOpen ? null : exitReason,
      target: targetLevel || null,
      stop: stopLevel || null,
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
    setTargetLevel(t.target || "");
    setStopLevel(t.stop || "");
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
    setIsOpen(!!t.is_open);
    if (t.has_image) {
      try {
        const img = await api.get<{ chart_image: string | null }>(`/daily/trade/${t.id}/image`);
        setChartImage(img.chart_image || "");
      } catch {
        /* ignore */
      }
    }
  };

  // Close a position from the open book: load it into the form, flip it out of "still holding",
  // and clear the placeholder 0 P/L so the auto-calc fills in once you type the exit. You still
  // confirm the exit price + reason and hit save — this just removes the hunt for the trade.
  const startClose = async (t: DailyTradeRow) => {
    await startEdit(t);
    setIsOpen(false);
    setExit("");
    setPnl("");
    setPnlEdited(false);
    setExitReason(EXIT_REASONS[0]);
    setLogOpen(true);
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const handleImageFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setChartImage(await fileToCompressedDataUrl(f));
    e.target.value = "";
  };
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = Array.from(e.dataTransfer.files).find((x) => x.type.startsWith("image/"));
    if (f) {
      setChartImage(await fileToCompressedDataUrl(f));
      toast.success("Chart attached");
    }
  };
  const pasteFromClipboard = async () => {
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          const file = new File([blob], "chart.png", { type });
          setChartImage(await fileToCompressedDataUrl(file));
          toast.success("Chart attached");
          return;
        }
      }
      toast.error("No image on the clipboard — copy the chart first");
    } catch {
      toast.error("Clipboard read blocked — use Attach chart or drag the file instead");
    }
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

  // All-time realized across every logged day (running P/L + record).
  const allTime = useMemo(() => {
    const days = history?.days ?? [];
    return {
      total: Math.round(days.reduce((a, d) => a + d.total_pnl, 0) * 100) / 100,
      wins: days.reduce((a, d) => a + d.wins, 0),
      losses: days.reduce((a, d) => a + d.losses, 0),
      trades: days.reduce((a, d) => a + d.trade_count, 0),
      daysHit: days.filter((d) => d.hit).length,
      dayCount: days.length,
    };
  }, [history]);

  // Open book — capital deployed in positions still held (risk exposure: are you within your limits + stops?).
  const openBook = useMemo(() => {
    const opens = (history?.days ?? []).flatMap((d) => d.trades).filter((t) => t.is_open);
    return {
      count: opens.length,
      invested: Math.round(opens.reduce((a, t) => a + (t.position_size ?? 0), 0) * 100) / 100,
      trades: opens,
    };
  }, [history]);

  // Pattern leaderboard — group every logged trade by its setup, rank by realized edge.
  const patterns = useMemo(() => {
    const allTrades = (history?.days ?? [])
      .flatMap((d) => d.trades)
      .filter((t) => !t.is_open && (instFilter === "all" || t.instrument === instFilter));
    const map = new Map<string, DailyTradeRow[]>();
    for (const t of allTrades) {
      const k =
        groupBy === "instrument"
          ? t.instrument === "option"
            ? "Options"
            : "Stocks"
          : (groupBy === "target" ? t.target : groupBy === "stop" ? t.stop : t.setup) || "—";
      const arr = map.get(k);
      if (arr) arr.push(t);
      else map.set(k, [t]);
    }
    const rows = Array.from(map.entries()).map(([key, ts]) => {
      const total = Math.round(ts.reduce((a, t) => a + t.pnl, 0) * 100) / 100;
      const wins = ts.filter((t) => t.pnl > 0).length;
      const losses = ts.filter((t) => t.pnl < 0).length;
      const decided = wins + losses;
      const best = ts.reduce<DailyTradeRow | null>((b, t) => (t.pnl > (b?.pnl ?? -Infinity) ? t : b), null);
      const worst = ts.reduce<DailyTradeRow | null>((b, t) => (t.pnl < (b?.pnl ?? Infinity) ? t : b), null);
      return {
        key,
        trades: ts,
        count: ts.length,
        wins,
        losses,
        winRate: decided > 0 ? wins / decided : 0,
        total,
        avg: ts.length > 0 ? Math.round((total / ts.length) * 100) / 100 : 0,
        best,
        worst,
      };
    });
    const by = {
      total: (a: (typeof rows)[0], b: (typeof rows)[0]) => b.total - a.total,
      winrate: (a: (typeof rows)[0], b: (typeof rows)[0]) => b.winRate - a.winRate,
      avg: (a: (typeof rows)[0], b: (typeof rows)[0]) => b.avg - a.avg,
      count: (a: (typeof rows)[0], b: (typeof rows)[0]) => b.count - a.count,
    };
    return rows.sort(by[patternSort]);
  }, [history, patternSort, groupBy, instFilter]);

  const isDayOpen = (date: string) => openDays[date] ?? date === todayStr;

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-5">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div>
          <h1 className="font-display text-xl font-bold text-text-primary">Daily Target</h1>
          <p className="mt-1 text-[11px] text-text-faint">{todayStr ?? "today"} · make your number, then stop</p>
        </div>

        {/* View switcher — Journal (log + history) vs Patterns (setup leaderboard) */}
        <div className="flex w-fit gap-1 rounded-lg border border-border-subtle bg-surface-1 p-1">
          {(["journal", "patterns"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-md px-4 py-1.5 text-[13px] font-semibold transition-colors ${
                view === v ? "bg-surface-3 text-accent" : "text-text-faint hover:text-text-secondary"
              }`}
            >
              {v === "journal" ? "Journal" : "Patterns"}
            </button>
          ))}
        </div>

        {view === "journal" && (
          <>
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

        {/* All-time realized — the running total across every logged day */}
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border-subtle bg-surface-1 px-5 py-3">
          <div className="text-[11px] uppercase tracking-wide text-text-faint">Total realized · all time</div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
            <span
              className={`font-display text-lg font-bold ${allTime.total < 0 ? "text-bearish-text" : "text-bullish-text"}`}
            >
              {usd(allTime.total)}
            </span>
            <span className="text-text-faint">
              {allTime.trades} trades · <span className="text-bullish-text">{allTime.wins}W</span>{" "}
              <span className="text-bearish-text">{allTime.losses}L</span> · {allTime.daysHit}/{allTime.dayCount} days hit
            </span>
          </div>
        </div>

        {/* Open book — capital deployed in positions still held (tap to expand per-position allocation) */}
        {openBook.count > 0 && (
          <div className="overflow-hidden rounded-xl border border-accent/30 bg-accent/5">
            <button
              onClick={() => setOpenBookOpen((o) => !o)}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-5 py-3 text-left"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-text-faint">
                <ChevronRight className={`h-3.5 w-3.5 transition-transform ${openBookOpen ? "rotate-90" : ""}`} />
                Open positions · capital deployed
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
                <span className="font-display text-lg font-bold text-text-primary">{usd(openBook.invested)}</span>
                <span className="text-text-faint">{openBook.count} open · mind your stops</span>
              </div>
            </button>
            {openBookOpen && (
              <div className="divide-y divide-border-subtle/40 border-t border-accent/20">
                {[...openBook.trades]
                  .sort((a, b) => (b.position_size ?? 0) - (a.position_size ?? 0))
                  .map((t) => {
                    const size = t.position_size ?? 0;
                    const pct = openBook.invested > 0 ? Math.round((size / openBook.invested) * 100) : 0;
                    return (
                      <div key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2 text-[12px]">
                        <div className="flex min-w-0 flex-1 items-center gap-2">
                          <span className="font-mono font-semibold text-text-primary">{t.symbol}</span>
                          <span className="text-[10px] uppercase text-text-faint">{t.instrument}</span>
                          <span className="text-text-faint">{t.setup || "—"}</span>
                          {t.stop ? <span className="text-text-faint">· 🛑 {t.stop}</span> : null}
                        </div>
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-3">
                          <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="w-24 text-right font-mono text-text-secondary">{usd(size)}</span>
                        <span className="w-10 text-right text-text-faint">{pct}%</span>
                        <button
                          onClick={() => startClose(t)}
                          className="shrink-0 rounded-md border border-border-subtle px-2 py-1 text-[11px] font-semibold text-text-secondary hover:border-accent hover:text-accent"
                          title="Log the exit and close this position"
                        >
                          Close
                        </button>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        )}

        {/* Log / edit a trade — collapsed by default (tap to open); auto-opens when editing */}
        <form
          ref={formRef}
          onSubmit={submitTrade}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`rounded-xl border p-5 space-y-3 ${dragOver ? "border-accent bg-accent/10" : editingId ? "border-accent/50 bg-accent/5" : "border-border-subtle bg-surface-1"}`}
        >
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setLogOpen((o) => !o)}
              className="flex items-center gap-2 font-semibold text-text-primary"
            >
              <ChevronRight className={`h-4 w-4 text-text-faint transition-transform ${logOpen ? "rotate-90" : ""}`} />
              {editingId ? "Edit trade" : "Log a trade"}
            </button>
            {editingId && logOpen ? (
              <button type="button" onClick={resetForm} className="text-xs text-text-faint hover:text-text-primary">
                Cancel edit
              </button>
            ) : !logOpen ? (
              <button
                type="button"
                onClick={() => setLogOpen(true)}
                className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:opacity-80"
              >
                <Plus className="h-3.5 w-3.5" /> Add
              </button>
            ) : null}
          </div>
          {logOpen && (
            <>
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
              placeholder={isOpen ? "Exit — n/a (open)" : "Exit"}
              value={isOpen ? "" : exit}
              disabled={isOpen}
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
              placeholder={isOpen ? "P/L — n/a (open)" : "P/L $ (auto)"}
              value={isOpen ? "" : effectivePnl}
              disabled={isOpen}
              onChange={(e) => {
                setPnl(e.target.value);
                setPnlEdited(true);
              }}
              title={!pnlEdited && computedPnl !== null ? "Auto from entry, exit & size — type to override" : ""}
            />
            <select
              className={inputCls}
              value={isOpen ? "" : exitReason}
              disabled={isOpen}
              onChange={(e) => setExitReason(e.target.value)}
              title={isOpen ? "No exit reason yet — you're still holding" : "How the trade ended"}
            >
              {isOpen && <option value="">Exit reason — n/a (open)</option>}
              {EXIT_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <select
              className={inputCls}
              value={targetLevel}
              onChange={(e) => setTargetLevel(e.target.value)}
              title="Target — the structure you aim for (e.g. entered at 200 SMA, target the 50 SMA)"
            >
              <option value="">Target level…</option>
              {STRUCTURES.filter(Boolean).map((x) => (
                <option key={x} value={x}>
                  🎯 {x}
                </option>
              ))}
            </select>
            <select
              className={inputCls}
              value={stopLevel}
              onChange={(e) => setStopLevel(e.target.value)}
              title="Stop — the structure that invalidates the trade (e.g. below the 200 SMA / PDL)"
            >
              <option value="">Stop level…</option>
              {STRUCTURES.filter(Boolean).map((x) => (
                <option key={x} value={x}>
                  🛑 {x}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-[13px] text-text-secondary">
            <input
              type="checkbox"
              checked={isOpen}
              onChange={(e) => setIsOpen(e.target.checked)}
              className="h-4 w-4 accent-accent"
            />
            Still holding — open position (log the entry now, add the exit &amp; P/L when you close it)
          </label>
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
                <ImageIcon className="h-4 w-4" /> Attach chart — click, drag a file here, or paste
                <input type="file" accept="image/*" className="hidden" onChange={handleImageFile} />
              </label>
              <button
                type="button"
                onClick={pasteFromClipboard}
                className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-[13px] text-text-secondary hover:text-text-primary"
              >
                <ClipboardPaste className="h-4 w-4" /> Paste from clipboard
              </button>
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
              disabled={addTrade.isPending || updateTrade.isPending || !symbol.trim() || (!isOpen && effectivePnl.trim() === "")}
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
            </>
          )}
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
                            onView={setLightbox}
                          />
                        </div>
                      ))}
                  </div>
                );
              })}
            </div>
          ))
        )}
          </>
        )}

        {view === "patterns" &&
          (patterns.length === 0 ? (
            <div className="bg-surface-1 border border-border-subtle rounded-xl p-5 text-sm text-text-muted">
              Log some trades and they'll rank here by realized edge.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 px-1">
                <div className="text-[12px] text-text-faint">
                  {groupBy === "setup"
                    ? "Entry setups"
                    : groupBy === "target"
                      ? "Targets"
                      : groupBy === "stop"
                        ? "Stops"
                        : "Instruments"}
                  {instFilter !== "all" ? ` · ${instFilter === "option" ? "options" : "stocks"} only` : ""} ranked by{" "}
                  {patternSort === "total"
                    ? "total P/L"
                    : patternSort === "winrate"
                      ? "win rate"
                      : patternSort === "avg"
                        ? "avg P/L"
                        : "trade count"}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={instFilter}
                    onChange={(e) => {
                      setInstFilter(e.target.value as "all" | "stock" | "option");
                      setOpenSetup(null);
                    }}
                    className={`${inputCls} py-1 text-[12px]`}
                    title="Scope the leaderboard to stocks or options"
                  >
                    <option value="all">Stocks + options</option>
                    <option value="stock">Stocks only</option>
                    <option value="option">Options only</option>
                  </select>
                  <select
                    value={groupBy}
                    onChange={(e) => {
                      setGroupBy(e.target.value as "setup" | "target" | "stop" | "instrument");
                      setOpenSetup(null);
                    }}
                    className={`${inputCls} py-1 text-[12px]`}
                    title="Group the leaderboard by entry setup, target, stop, or instrument"
                  >
                    <option value="setup">By setup</option>
                    <option value="target">By target</option>
                    <option value="stop">By stop</option>
                    <option value="instrument">By instrument</option>
                  </select>
                  <select
                    value={patternSort}
                    onChange={(e) => setPatternSort(e.target.value as "total" | "winrate" | "avg" | "count")}
                    className={`${inputCls} py-1 text-[12px]`}
                  >
                    <option value="total">Total P/L</option>
                    <option value="winrate">Win rate</option>
                    <option value="avg">Avg P/L</option>
                    <option value="count">Trade count</option>
                  </select>
                </div>
              </div>
              {patterns.map((p) => {
                const open = openSetup === p.key;
                return (
                  <div key={p.key} className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
                    <button
                      onClick={() => setOpenSetup(open ? null : p.key)}
                      className="w-full text-left px-4 py-3 hover:bg-surface-2/30"
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="flex items-center gap-2 font-semibold text-text-primary">
                          <ChevronRight className={`h-4 w-4 text-text-faint transition-transform ${open ? "rotate-90" : ""}`} />
                          {p.key}
                        </span>
                        <span className={`font-mono font-semibold ${p.total < 0 ? "text-bearish-text" : "text-bullish-text"}`}>
                          {usd(p.total)}
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
                        <div className="h-full rounded-full bg-bullish" style={{ width: `${Math.round(p.winRate * 100)}%` }} />
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-text-faint">
                        <span>{p.count} trades</span>
                        <span className="text-text-faint/50">·</span>
                        <span>
                          {Math.round(p.winRate * 100)}% win ({p.wins}W {p.losses}L)
                        </span>
                        <span className="text-text-faint/50">·</span>
                        <span>
                          avg <span className={p.avg < 0 ? "text-bearish-text" : "text-bullish-text"}>{usd(p.avg)}</span>
                        </span>
                        {p.best && p.best.pnl > 0 && (
                          <>
                            <span className="text-text-faint/50">·</span>
                            <span>
                              best <span className="text-bullish-text">{usd(p.best.pnl)}</span> {p.best.symbol}
                            </span>
                          </>
                        )}
                      </div>
                    </button>
                    {open && (
                      <div className="border-t border-border-subtle">
                        <DayTrades
                          trades={p.trades}
                          expandedId={expandedId}
                          setExpandedId={setExpandedId}
                          onEdit={(t) => {
                            startEdit(t);
                            setView("journal");
                          }}
                          onDelete={(id) => delTrade.mutate(id)}
                          onView={setLightbox}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
      </div>

      {/* Full-screen chart lightbox — click anywhere or Esc to close */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-4"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox} alt="chart full screen" className="max-h-full max-w-full rounded-lg object-contain" />
          <button
            onClick={() => setLightbox(null)}
            className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      )}
    </div>
  );
}
