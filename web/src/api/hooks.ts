/** TanStack Query hooks for all API endpoints. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { toast } from "../components/Toast";
import type {
  AuthTokens, SignalResult, Alert, User,
  OptionsTrade, OptionsTradeStats, EquityPoint,
  SpyRegime, SwingCategory, SwingTrade,
  WinRateData, SetupAnalysis, MTFContext, NotificationPrefs,
  NotificationRouting,
  PerformanceBreakdown,
} from "../types";

// --- Auth ---

export function useLogin() {
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api.post<AuthTokens>("/auth/login", body),
  });
}

export function useRegister() {
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name?: string }) =>
      api.post<AuthTokens>("/auth/register", body),
  });
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User>("/auth/me"),
    retry: false,
    staleTime: 5 * 60_000,
  });
}

// --- Watchlist ---

export interface WatchlistItem {
  id: number;
  symbol: string;
}

export function useWatchlist() {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.get<WatchlistItem[]>("/watchlist"),
  });
}

/** Live prices — polls every 15 seconds during market hours. */
export function useLivePrices() {
  return useQuery({
    queryKey: ["live-prices"],
    queryFn: () => api.get<{ prices: Record<string, { price: number; change_pct: number }> }>("/market/prices"),
    refetchInterval: 15_000,  // 15 seconds
    staleTime: 10_000,
  });
}

export function useAddSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.post<WatchlistItem>("/watchlist", { symbol }),
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<WatchlistItem[]>(["watchlist"]);
      qc.setQueryData<WatchlistItem[]>(["watchlist"], (old) => [
        ...(old ?? []),
        { id: Date.now(), symbol },
      ]);
      return { prev };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
      toast.error("Failed to add symbol");
    },
    onSuccess: (_data, symbol) => toast.success(`${symbol} added`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.delete(`/watchlist/${symbol}`),
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<WatchlistItem[]>(["watchlist"]);
      qc.setQueryData<WatchlistItem[]>(["watchlist"], (old) =>
        (old ?? []).filter((w) => w.symbol !== symbol),
      );
      return { prev };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
      toast.error("Failed to remove symbol");
    },
    onSuccess: (_data, symbol) => toast.success(`${symbol} removed`),
    onSettled: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useBulkSetWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbols: string[]) => api.put<WatchlistItem[]>("/watchlist", { symbols }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

// --- Scanner ---

export function useScanner() {
  return useQuery({
    queryKey: ["scanner"],
    queryFn: () => api.get<SignalResult[]>("/scanner/scan"),
    staleTime: 60_000, // 60s — prices come from live feed now
    refetchInterval: 60_000, // refresh grades/scores every 60s
  });
}

export function useWatchlistRank() {
  return useQuery({
    queryKey: ["watchlist-rank"],
    queryFn: () => api.get<import("../types").WatchlistRankItem[]>("/scanner/watchlist-rank"),
    staleTime: 3 * 60_000,  // 3 min — matches backend cache TTL
    refetchInterval: 3 * 60_000,
  });
}

export function useActiveEntries() {
  return useQuery({
    queryKey: ["active-entries"],
    queryFn: () =>
      api.get<
        {
          id: number;
          symbol: string;
          entry_price: number | null;
          stop_price: number | null;
          target_1: number | null;
          target_2: number | null;
          alert_type: string | null;
          status: string;
        }[]
      >("/scanner/active-entries"),
  });
}

// --- Market ---

export interface MarketStatus {
  is_open: boolean;
  is_premarket: boolean;
  session_phase: string;
}

export function useMarketStatus() {
  return useQuery({
    queryKey: ["market-status"],
    queryFn: () => api.get<MarketStatus>("/market/status"),
    refetchInterval: 60_000,
  });
}

export interface OHLCBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function useIntraday(symbol: string) {
  return useQuery({
    queryKey: ["intraday", symbol],
    queryFn: () => api.get<OHLCBar[]>(`/market/intraday/${symbol}`),
    enabled: !!symbol,
    staleTime: 3 * 60_000,
  });
}

export function usePriorDay(symbol: string) {
  return useQuery({
    queryKey: ["prior-day", symbol],
    queryFn: () => api.get<Record<string, unknown>>(`/market/prior-day/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export interface SectorRotationItem {
  symbol: string;
  name: string;
  price: number;
  change_1d: number;
  change_5d: number;
  change_20d: number;
  flow: "INFLOW" | "OUTFLOW" | "NEUTRAL";
}

export function useSectorRotation() {
  return useQuery({
    queryKey: ["sector-rotation"],
    queryFn: () => api.get<SectorRotationItem[]>("/market/sector-rotation"),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });
}

// --- Catalysts ---

export interface CatalystItem {
  symbol: string;
  event: string;  // "EARNINGS" | "EX_DIVIDEND" | "DIVIDEND"
  date: string;
  days_away: number;
  timing?: string;  // "After Close" | "Before Open" | "Unknown"
}

/** Upcoming catalysts (earnings, ex-dividend) — refreshes every 30 min. */
export function useCatalysts(symbols: string) {
  return useQuery({
    queryKey: ["catalysts", symbols],
    queryFn: () => api.get<CatalystItem[]>(`/market/catalysts?symbols=${encodeURIComponent(symbols)}`),
    enabled: !!symbols,
    staleTime: 30 * 60_000,  // 30 min — catalysts don't change often
    refetchInterval: 30 * 60_000,
  });
}

/** Options flow — unusual options activity scanner, refreshes every 3 min. */
export function useOptionsFlow(symbols: string) {
  return useQuery({
    queryKey: ["options-flow", symbols],
    queryFn: () => api.get<import("../types").OptionsFlowItem[]>(`/market/options-flow?symbols=${encodeURIComponent(symbols)}`),
    enabled: !!symbols,
    staleTime: 3 * 60_000,
    refetchInterval: 3 * 60_000,
  });
}

// --- Alerts ---

export function useAlertsToday() {
  return useQuery({
    queryKey: ["alerts-today"],
    queryFn: () => api.get<Alert[]>("/alerts/today"),
    refetchInterval: 20_000, // refresh every 20s to catch new alerts
  });
}

export interface UsageStatus {
  tier: string;
  trial_active: boolean;
  trial_days_left: number;
  limits: Record<string, unknown>;
  usage_today: Record<string, number>;
  ai_scan_alerts_today: number;
  ai_scan_alerts_max: number | null;
  ai_scan_limit_reached: boolean;
}

export function useUsageStatus() {
  return useQuery({
    queryKey: ["usage-status"],
    queryFn: () => api.get<UsageStatus>("/auth/usage"),
    refetchInterval: 60_000, // 1 min
  });
}

export function useAlertsHistory(days = 7) {
  return useQuery({
    queryKey: ["alerts-history", days],
    queryFn: () => api.get<Alert[]>(`/alerts/history?days=${days}`),
  });
}

export interface SessionSummary {
  total_alerts: number;
  buy_alerts: number;
  sell_alerts: number;
  target_1_hits: number;
  target_2_hits: number;
  stopped_out: number;
  active_entries: number;
}

export function useSessionSummary() {
  return useQuery({
    queryKey: ["session-summary"],
    queryFn: () => api.get<SessionSummary>("/alerts/session-summary"),
    refetchInterval: 60_000,
  });
}

// --- Trades ---

export interface TradeHistoryItem {
  symbol: string;
  trade_date: string;
  proceeds: number;
  cost_basis: number;
  realized_pnl: number;
  wash_sale_disallowed: number;
  asset_type: string | null;
  holding_days: number | null;
  account: string | null;
  source: string;
}

export function useTradeHistory() {
  return useQuery({
    queryKey: ["trade-history"],
    queryFn: () => api.get<TradeHistoryItem[]>("/trades/history"),
  });
}

export interface MonthlyStats {
  month: string;
  total_trades: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
}

export function useMonthlyStats() {
  return useQuery({
    queryKey: ["monthly-stats"],
    queryFn: () => api.get<MonthlyStats[]>("/trades/monthly-stats"),
  });
}

// --- Charts ---

export interface ChartLevel {
  id: number;
  symbol: string;
  price: number;
  label: string;
  color: string;
}

export function useChartLevels(symbol: string) {
  return useQuery({
    queryKey: ["chart-levels", symbol],
    queryFn: () => api.get<ChartLevel[]>(`/charts/levels?symbol=${symbol}`),
    enabled: !!symbol,
  });
}

export function useAddChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbol: string; price: number; label?: string; color?: string }) =>
      api.post<ChartLevel>("/charts/levels", body),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useDeleteChartLevel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; symbol: string }) =>
      api.delete(`/charts/levels/${vars.id}`),
    onSuccess: (_, vars) => qc.invalidateQueries({ queryKey: ["chart-levels", vars.symbol] }),
  });
}

export function useOHLCV(symbol: string, period = "1y", interval = "1d") {
  // Chart data: refresh every 10s for intraday, 60s for daily
  const isIntraday = ["1m", "5m", "15m", "30m", "60m"].includes(interval);
  const refreshMs = isIntraday ? 10_000 : 60_000;
  return useQuery({
    queryKey: ["ohlcv", symbol, period, interval],
    queryFn: () => api.get<OHLCBar[]>(`/charts/ohlcv/${symbol}?period=${period}&interval=${interval}`),
    enabled: !!symbol,
    staleTime: refreshMs,
    refetchInterval: refreshMs,
    gcTime: 30 * 60_000,
  });
}

// --- Real Trades ---

export interface RealTrade {
  id: number;
  symbol: string;
  direction: string;
  shares: number;
  entry_price: number;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  pnl: number | null;
  status: string;
  notes: string | null;
  session_date: string;
  opened_at: string;
  closed_at: string | null;
}

export function useOpenTrades() {
  return useQuery({
    queryKey: ["real-trades-open"],
    queryFn: () => api.get<RealTrade[]>("/real-trades/open"),
    staleTime: 15_000, // refetch every 15s to catch new positions
  });
}

export function useClosedTrades(limit = 50) {
  return useQuery({
    queryKey: ["real-trades-closed", limit],
    queryFn: () => api.get<RealTrade[]>(`/real-trades/closed?limit=${limit}`),
  });
}

export function useCloseTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_price, notes }: { id: number; exit_price: number; notes?: string }) =>
      api.post<RealTrade>(`/real-trades/${id}/close`, { exit_price, notes: notes || "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
      qc.invalidateQueries({ queryKey: ["real-trade-stats"] });
      toast.success("Position closed");
    },
    onError: () => toast.error("Failed to close position"),
  });
}

export interface RealTradeStats {
  total_pnl: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
}

export function useRealTradeStats() {
  return useQuery({
    queryKey: ["real-trade-stats"],
    queryFn: () => api.get<RealTradeStats>("/real-trades/stats"),
  });
}

export function useOpenRealTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      symbol: string;
      direction?: string;
      entry_price: number;
      stop_price?: number;
      target_price?: number;
      shares?: number;
    }) => api.post<RealTrade>("/real-trades/open", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["real-trades-open"] }),
  });
}

export function useCloseRealTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_price, notes }: { id: number; exit_price: number; notes?: string }) =>
      api.post<RealTrade>(`/real-trades/${id}/close`, { exit_price, notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
      qc.invalidateQueries({ queryKey: ["real-trade-stats"] });
    },
  });
}

// --- Paper Trading ---

export interface PaperTrade {
  id: number;
  symbol: string;
  direction: string;
  shares: number;
  entry_price: number | null;
  exit_price: number | null;
  pnl: number | null;
  status: string;
  session_date: string;
}

export function usePaperPositions() {
  return useQuery({
    queryKey: ["paper-positions"],
    queryFn: () => api.get<PaperTrade[]>("/paper-trading/positions"),
  });
}

export function usePaperHistory() {
  return useQuery({
    queryKey: ["paper-history"],
    queryFn: () => api.get<PaperTrade[]>("/paper-trading/history"),
  });
}

export interface PaperAccount {
  open_positions: number;
  total_closed: number;
  total_pnl: number;
  win_rate: number;
}

export function usePaperAccount() {
  return useQuery({
    queryKey: ["paper-account"],
    queryFn: () => api.get<PaperAccount>("/paper-trading/account"),
  });
}

// --- Backtest ---

export interface BacktestResult {
  symbol: string;
  total_signals: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  total_pnl: number;
  avg_rr: number;
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (body: { symbols: string[]; start_date: string; end_date: string }) =>
      api.post<BacktestResult[]>("/backtest/run", body),
  });
}

// --- Alert ACK ---

export function useAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: "took" | "skipped" }) =>
      api.post(`/alerts/${id}/ack?action=${action}`),
    onMutate: async ({ id, action }) => {
      await qc.cancelQueries({ queryKey: ["alerts-today"] });
      const prev = qc.getQueryData<Alert[]>(["alerts-today"]);
      qc.setQueryData<Alert[]>(["alerts-today"], (old) =>
        (old ?? []).map((a) => a.id === id ? { ...a, user_action: action } : a),
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["alerts-today"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["alerts-today"] });
      qc.invalidateQueries({ queryKey: ["session-summary"] });
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
    },
  });
}

export function useAlertSessionDates() {
  return useQuery({
    queryKey: ["alert-session-dates"],
    queryFn: () => api.get<string[]>("/alerts/session-dates"),
  });
}

export function useAlertSession(date: string) {
  return useQuery({
    queryKey: ["alert-session", date],
    queryFn: () => api.get<SessionSummary>(`/alerts/session/${date}`),
    enabled: !!date,
  });
}

export function useAlertsForDate(date: string) {
  return useQuery({
    queryKey: ["alerts-date", date],
    queryFn: () => api.get<Alert[]>(`/alerts/history?days=90`),
    enabled: !!date,
    select: (data) => data.filter((a) => a.session_date === date),
  });
}

export function useAIUpdatesForDate(date: string, symbols?: string[]) {
  const symbolsParam = symbols && symbols.length > 0 ? symbols.join(",") : "";
  return useQuery({
    queryKey: ["ai-updates", date, symbolsParam],
    queryFn: () => {
      const qs = new URLSearchParams({ session_date: date });
      if (symbolsParam) qs.set("symbols", symbolsParam);
      return api.get<Alert[]>(`/diagnostics/ai-updates?${qs.toString()}`);
    },
    enabled: !!date,
  });
}

// --- Performance Breakdown ---

export function usePerformanceBreakdown() {
  return useQuery({
    queryKey: ["performance-breakdown"],
    queryFn: () => api.get<PerformanceBreakdown>("/real-trades/performance-breakdown"),
    staleTime: 5 * 60_000,
  });
}

// --- Real Trade Notes ---

export function useUpdateTradeNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) =>
      api.put(`/real-trades/${id}/notes`, { notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real-trades-open"] });
      qc.invalidateQueries({ queryKey: ["real-trades-closed"] });
    },
  });
}

// --- Equity Curves ---

export function useRealTradeEquityCurve() {
  return useQuery({
    queryKey: ["real-trades-equity"],
    queryFn: () => api.get<EquityPoint[]>("/real-trades/equity-curve"),
  });
}

export function usePaperEquityCurve() {
  return useQuery({
    queryKey: ["paper-equity"],
    queryFn: () => api.get<EquityPoint[]>("/paper-trading/equity-curve"),
  });
}

export function useImportedEquityCurve() {
  return useQuery({
    queryKey: ["imported-equity"],
    queryFn: () => api.get<EquityPoint[]>("/trades/equity-curve"),
  });
}

// --- Options Trades ---

export function useOpenOptionsTrades() {
  return useQuery({
    queryKey: ["options-open"],
    queryFn: () => api.get<OptionsTrade[]>("/real-trades/options/open"),
  });
}

export function useClosedOptionsTrades(limit = 200) {
  return useQuery({
    queryKey: ["options-closed", limit],
    queryFn: () => api.get<OptionsTrade[]>(`/real-trades/options/closed?limit=${limit}`),
  });
}

export function useOptionsTradeStats() {
  return useQuery({
    queryKey: ["options-stats"],
    queryFn: () => api.get<OptionsTradeStats>("/real-trades/options/stats"),
  });
}

export function useOpenOptionsTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      symbol: string;
      option_type: string;
      strike: number;
      expiration: string;
      contracts?: number;
      premium_per_contract: number;
    }) => api.post("/real-trades/options/open", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["options-open"] }),
  });
}

export function useCloseOptionsTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, exit_premium, notes }: { id: number; exit_premium: number; notes?: string }) =>
      api.post(`/real-trades/options/${id}/close`, { exit_premium, notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["options-open"] });
      qc.invalidateQueries({ queryKey: ["options-closed"] });
      qc.invalidateQueries({ queryKey: ["options-stats"] });
    },
  });
}

// --- Settings ---

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { display_name: string }) =>
      api.put("/settings/profile", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.put("/settings/password", body),
  });
}

export function useNotificationPrefs() {
  return useQuery({
    queryKey: ["notification-prefs"],
    queryFn: () => api.get<NotificationPrefs>("/settings/notifications"),
  });
}

export function useUpdateNotificationPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NotificationPrefs) =>
      api.put<NotificationPrefs>("/settings/notifications", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notification-prefs"] }),
  });
}

// --- Per-Alert-Type Channel Routing ---

export function useNotificationRouting() {
  return useQuery({
    queryKey: ["notification-routing"],
    queryFn: () => api.get<NotificationRouting>("/settings/notification-routing"),
  });
}

export function useUpdateNotificationRouting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationRouting) => {
      const { telegram_update_symbols, ...routing } = data;
      return api.put<NotificationRouting>("/settings/notification-routing", {
        routing,
        telegram_update_symbols,
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notification-routing"] }),
  });
}

// --- Alert Preferences ---

export function useAlertPrefs() {
  return useQuery({
    queryKey: ["alert-prefs"],
    queryFn: () => api.get<import("../types").AlertPrefs>("/settings/alert-preferences"),
  });
}

export function useUpdateAlertPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { categories: Record<string, boolean>; min_score: number }) =>
      api.put<import("../types").AlertPrefs>("/settings/alert-preferences", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-prefs"] }),
  });
}

// --- Telegram ---

export function useTelegramStatus() {
  return useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.get<{ linked: boolean; telegram_enabled: boolean }>("/settings/telegram-status"),
  });
}

export function useTelegramLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ deep_link: string; token: string }>("/settings/telegram-link"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-status"] }),
  });
}

export function useTelegramUnlink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete("/settings/telegram-link"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-status"] }),
  });
}

// --- Swing Trades ---

export function useSpyRegime() {
  return useQuery({
    queryKey: ["spy-regime"],
    queryFn: () => api.get<SpyRegime>("/swing/regime"),
    staleTime: 5 * 60_000,
  });
}

export function useSwingCategories(date = "") {
  return useQuery({
    queryKey: ["swing-categories", date],
    queryFn: () => api.get<SwingCategory[]>(`/swing/categories?session_date=${date}`),
  });
}

export function useActiveSwingTrades() {
  return useQuery({
    queryKey: ["swing-active"],
    queryFn: () => api.get<SwingTrade[]>("/swing/trades/active"),
  });
}

export function useSwingTradesHistory(limit = 50) {
  return useQuery({
    queryKey: ["swing-history", limit],
    queryFn: () => api.get<SwingTrade[]>(`/swing/trades/history?limit=${limit}`),
  });
}

export function useTriggerSwingScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ alerts_fired: number }>("/swing/scan"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["swing-active"] });
      qc.invalidateQueries({ queryKey: ["swing-categories"] });
    },
  });
}

// --- Intel Hub ---

export function useAlertWinRates(days = 90) {
  return useQuery({
    queryKey: ["alert-win-rates", days],
    queryFn: () => api.get<WinRateData>(`/intel/win-rates?days=${days}`),
    staleTime: 10 * 60_000,
  });
}

export function useAckedWinRates(days = 90) {
  return useQuery({
    queryKey: ["acked-win-rates", days],
    queryFn: () => api.get<WinRateData>(`/intel/acked-win-rates?days=${days}`),
    staleTime: 10 * 60_000,
  });
}

export function useFundamentals(symbol: string) {
  return useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => api.get<{ symbol: string; data: Record<string, unknown> }>(`/intel/fundamentals/${symbol}`),
    enabled: !!symbol,
    staleTime: 30 * 60_000,
  });
}

export function useDailyAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["daily-analysis", symbol],
    queryFn: () => api.get<SetupAnalysis>(`/intel/daily/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export function useWeeklyAnalysis(symbol: string) {
  return useQuery({
    queryKey: ["weekly-analysis", symbol],
    queryFn: () => api.get<SetupAnalysis>(`/intel/weekly/${symbol}`),
    enabled: !!symbol,
    staleTime: 30 * 60_000,
  });
}

export function useMTFContext(symbol: string) {
  return useQuery({
    queryKey: ["mtf-context", symbol],
    queryFn: () => api.get<MTFContext>(`/intel/mtf/${symbol}`),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

// --- Performance Analytics ---

export interface StrategyPerformance {
  alert_type: string;
  total: number;
  wins: number;
  losses: number;
  no_outcome: number;
  t2_wins: number;
  win_rate: number;
  avg_score: number;
  avg_confluence: number;
}

export function usePerformanceByStrategy() {
  return useQuery({
    queryKey: ["performance-by-strategy"],
    queryFn: () => api.get<StrategyPerformance[]>("/performance/by-strategy"),
    staleTime: 10 * 60_000,
  });
}

export function usePerformanceSummary() {
  return useQuery({
    queryKey: ["performance-summary"],
    queryFn: () => api.get<Record<string, number>>("/performance/summary"),
    staleTime: 10 * 60_000,
  });
}

// --- Game Plan ---

export interface GamePlanSetup {
  symbol: string;
  direction: string;
  action_label: string;
  score: number;
  confluence_score: number;
  confluence_label: string;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  rr_ratio: number | null;
  risk_per_share: number | null;
  support_status: string;
  pattern: string;
  bias: string;
  composite_score: number;
}

export function useGamePlan() {
  return useQuery({
    queryKey: ["game-plan"],
    queryFn: () => api.get<GamePlanSetup[]>("/intel/game-plan"),
    staleTime: 5 * 60_000,
  });
}

// --- Trade Journal ---

export interface JournalEntry {
  id: number;
  symbol: string;
  alert_type: string;
  direction: string;
  entry_price: number | null;
  exit_price: number | null;
  stop_price: number | null;
  target_1: number | null;
  target_2: number | null;
  outcome: string;
  pnl_r: number | null;
  replay_text: string | null;
  session_date: string;
  created_at: string;
}

export function useTradeJournal(date?: string) {
  return useQuery({
    queryKey: ["trade-journal", date],
    queryFn: () => api.get<JournalEntry[]>(`/intel/trade-journal${date ? `?date=${date}` : ""}`),
    staleTime: 5 * 60_000,
  });
}

// --- AI Coach: Best Setups ---

export interface EntryCandidate {
  symbol: string;
  timeframe: "day" | "swing";
  direction: "LONG" | "SHORT";
  setup_type: string;
  entry: number;
  stop: number | null;
  t1: number | null;
  t2: number | null;
  conviction: "HIGH" | "MEDIUM" | "LOW";
  confluence: string[];
  why_now: string;
  current_price: number;
  distance_to_entry_pct: number;
}

export interface BestSetupsResponse {
  generated_at: string;
  watchlist_size: number;
  day_trade_picks: EntryCandidate[];
  swing_trade_picks: EntryCandidate[];
  skipped: { symbol: string; reason: string }[];
  error: string | null;
}

export function useBestSetups(enabled = false) {
  return useQuery({
    queryKey: ["best-setups"],
    queryFn: () => api.get<BestSetupsResponse>("/ai/best-setups"),
    enabled,
    staleTime: 14 * 60_000,  // match server cache of 15 min
    retry: false,
  });
}

export interface PinAlertPayload {
  symbol: string;
  timeframe: "day" | "swing";
  direction: "LONG" | "SHORT";
  setup_type: string;
  entry: number;
  stop: number | null;
  t1: number | null;
  t2: number | null;
  conviction: string;
  why_now: string;
  current_price: number;
}

export function usePinBestSetupAlert() {
  return useMutation({
    mutationFn: (payload: PinAlertPayload) =>
      api.post<{ ok: boolean; alert_id: number; telegram_sent: boolean }>(
        "/ai/best-setups/alert",
        payload,
      ),
    onSuccess: (data) => {
      if (data.telegram_sent) {
        toast.success("Alert sent to Telegram");
      } else {
        toast.info("Alert recorded (Telegram not enabled)");
      }
    },
    onError: (err: { message?: string; detail?: { message?: string } }) => {
      toast.error(err.detail?.message || err.message || "Failed to send alert");
    },
  });
}
