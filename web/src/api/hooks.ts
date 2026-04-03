/** TanStack Query hooks for all API endpoints. */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AuthTokens, SignalResult, Alert, User,
  OptionsTrade, OptionsTradeStats, EquityPoint,
  SpyRegime, SwingCategory, SwingTrade,
  WinRateData, SetupAnalysis, MTFContext, NotificationPrefs,
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

export function useAddSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.post<WatchlistItem>("/watchlist", { symbol }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.delete(`/watchlist/${symbol}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
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
    staleTime: 20_000, // 20s — fresh data every poll
    refetchInterval: 20_000, // auto-refresh every 20s
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

// --- Alerts ---

export function useAlertsToday() {
  return useQuery({
    queryKey: ["alerts-today"],
    queryFn: () => api.get<Alert[]>("/alerts/today"),
    refetchInterval: 20_000, // refresh every 20s to catch new alerts
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
  // Intraday intervals refresh every 20s; daily+ every 5 min
  const isIntraday = ["1m", "5m", "15m", "30m", "60m"].includes(interval);
  const refreshMs = isIntraday ? 20_000 : 5 * 60_000;
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
  });
}

export function useClosedTrades(limit = 50) {
  return useQuery({
    queryKey: ["real-trades-closed", limit],
    queryFn: () => api.get<RealTrade[]>(`/real-trades/closed?limit=${limit}`),
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts-today"] });
      qc.invalidateQueries({ queryKey: ["session-summary"] });
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
